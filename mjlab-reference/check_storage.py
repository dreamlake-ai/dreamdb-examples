"""Milestone S: a real SDK round trip, not an mjlab/training acceptance test.

Run without arguments. Writer exits before reader starts. All generated data is
temporary and removed by the coordinator. Children share source code, not a live
Dataset or process memory. Expected event values are deterministic fixture input.
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import dreamdb
import mujoco
import numpy as np
from store import (
    EVENT_FIELDS,
    LocalRunWriter,
    episode_status,
    read_episode,
    read_header,
    read_window,
)

# Minimal, asset-free two-DOF model. It is NOT claimed to be mjlab's Cartpole task.
MODEL = """<mujoco><worldbody><body name="cart"><joint name="slide" type="slide"/>
<geom type="sphere" size=".1" mass="1"/><body name="pole" pos="0 0 .1">
<joint name="hinge" type="hinge"/><geom type="capsule" size=".03 .3" mass=".1"/>
</body></body></worldbody></mujoco>"""


def events() -> list[dict]:
    def f32(values):
        return np.array(values, dtype="<f4")

    def reset(env, ep, sim_step):
        return {
            "kind": "reset",
            "env_id": env,
            "episode_id": ep,
            "step_id": 0,
            "sim_step": sim_step,
            "sim_time": 0.0,
            "qpos": f32([env / 8, ep / 16]),
            "qvel": f32([-0.0, 0.0]),
            "obs_after": f32([env, ep, 0.0, -0.0, 1.0]),
        }

    def transition(env, ep, step, sim_step, terminated=False, truncated=False):
        # Nontrivial float32 values, including negative zero; byte equality is checked.
        row = {
            "kind": "transition",
            "env_id": env,
            "episode_id": ep,
            "step_id": step,
            "sim_step": sim_step,
            "sim_time": (step + 1) / 20,
            "qpos": f32([env + step / 7, -0.0]),
            "qvel": f32([1e-7, -2.5]),
            "obs_t": f32([env, ep, step, 1 / 3, -0.0]),
            "action": f32([-0.125]),
            "reward": 0.125,
            "terminated": terminated,
            "truncated": truncated,
            "next_observation_valid": not (terminated or truncated),
        }
        if row["next_observation_valid"]:
            row["obs_after"] = f32([env, ep, step + 1, 1 / 3, -0.0])
        return row

    return [
        reset(0, 0, 0),
        reset(1, 0, 0),
        transition(0, 0, 0, 1),
        transition(1, 0, 0, 1),
        transition(0, 0, 1, 2, terminated=True),
        reset(0, 1, 2),
        transition(1, 0, 1, 2, truncated=True),
        reset(1, 1, 2),
        transition(0, 1, 0, 3, terminated=True, truncated=True),
        reset(0, 2, 3),
        transition(1, 1, 0, 3),  # Incomplete even after clean run_end.
    ]


def write(root: Path):
    model = mujoco.MjModel.from_xml_string(MODEL)
    model_file = root / "producer-model.mjb"
    mujoco.mj_saveModel(model, str(model_file))
    model_bytes = model_file.read_bytes()
    model_file.unlink()  # Reader must obtain the asset from DreamDB.
    writer = LocalRunWriter(
        root / "backend",
        {
            "run_id": "synthetic-storage-slice",
            "task": "synthetic-not-mjlab",
            "dimensions": {"qpos": 2, "qvel": 2, "obs_t": 5, "obs_after": 5, "action": 1},
            "mujoco_version": mujoco.__version__,
            "platform": platform.platform(),
            "control_dt": 0.05,
            "producer": "check_storage.py",
        },
        model_bytes,
    )
    rows = events()
    interrupted = writer.append(rows[:4])
    writer.append(rows[4:8])
    writer.append(rows[8:])
    final = writer.finish()
    # Receipt holds only snapshot identifiers, not model/state data.
    (root / "receipt.json").write_text(
        json.dumps(
            {
                "interrupted": interrupted,
                "final": final,
            }
        )
    )
    print(json.dumps({"writer": "PASS", "events": len(rows), "manifest": final}), flush=True)


def equal_rows(actual, expected):
    if len(actual) != len(expected):
        raise AssertionError(f"row count {len(actual)} != {len(expected)}")
    for got, want in zip(actual, expected, strict=True):
        if set(got) != set(want):
            raise AssertionError(f"fields differ at {want['_anchor']}: {set(got) ^ set(want)}")
        for name, value in want.items():
            observed = got[name]
            if isinstance(value, np.ndarray):
                if (
                    observed.dtype != value.dtype
                    or observed.shape != value.shape
                    or observed.tobytes() != value.tobytes()
                ):
                    raise AssertionError(f"array differs at {want['_anchor']}/{name}")
            elif isinstance(value, float):
                if struct.pack("<d", observed) != struct.pack("<d", value):
                    raise AssertionError(f"float bits differ at {want['_anchor']}/{name}")
            elif type(observed) is not type(value) or observed != value:
                raise AssertionError(f"value differs at {want['_anchor']}/{name}")


def read(root: Path):
    receipt = json.loads((root / "receipt.json").read_text())
    backend = (root / "backend").as_uri()
    dataset = dreamdb.Dataset.open_by_manifest(receipt["final"], backend=backend)
    if dataset.current_manifest() != receipt["final"]:
        raise AssertionError("reopened a different snapshot")
    metadata, model_bytes = read_header(dataset)
    if metadata["mujoco_version"] != mujoco.__version__:
        raise AssertionError("MJB runtime version mismatch")
    model_file = root / "reader-model.mjb"
    model_file.write_bytes(model_bytes)
    model = mujoco.MjModel.from_binary_path(str(model_file))
    model_file.unlink()
    if (model.nq, model.nv, model.na, model.nmocap) != (2, 2, 0, 0):
        raise AssertionError("saved model dimensions differ")
    expected = [dict(row, _anchor=i + 1) for i, row in enumerate(events())]
    start = time.perf_counter()
    actual = read_window(dataset, EVENT_FIELDS, 1, 1 + len(expected))
    equal_rows(actual, expected)
    read_ms = (time.perf_counter() - start) * 1000
    statuses = {}
    for env, ep in [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2)]:
        selected = read_episode(dataset, env, ep)
        want = [r for r in expected if r["env_id"] == env and r["episode_id"] == ep]
        equal_rows(selected, want)
        statuses[f"{env}:{ep}"] = episode_status(selected)
    if statuses != {
        "0:0": "complete",
        "1:0": "complete",
        "0:1": "complete",
        "1:1": "incomplete",
        "0:2": "incomplete",
    }:
        raise AssertionError(f"episode classification: {statuses}")
    projected = read_episode(dataset, 0, 0, fields=["qpos"])
    equal_rows(
        projected,
        [
            {"_anchor": r["_anchor"], "qpos": r["qpos"]}
            for r in expected
            if r["env_id"] == 0 and r["episode_id"] == 0
        ],
    )
    end = read_window(dataset, ["kind", "metadata"], len(expected) + 1, len(expected) + 2)
    if len(end) != 1 or end[0]["kind"] != "run_end":
        raise AssertionError("missing clean run-end marker")
    if json.loads(end[0]["metadata"])["event_rows"] != len(expected):
        raise AssertionError("run-end count differs")

    # A real older published prefix remains interrupted after Ref advancement.
    prefix = dreamdb.Dataset.open_by_manifest(receipt["interrupted"], backend=backend)
    prefix_rows = read_window(prefix, EVENT_FIELDS + ["metadata"], 1, len(expected) + 2)
    equal_rows(prefix_rows, expected[:4])
    if episode_status(read_episode(prefix, 0, 0)) != "incomplete":
        raise AssertionError("incomplete snapshot treated as complete")
    print(
        json.dumps(
            {
                "reader": "PASS",
                "events_exact": len(actual),
                "episodes": statuses,
                "model_bytes": len(model_bytes),
                "projected_read": "PASS",
                "pinned_prefix": "PASS",
                "read_ms": round(read_ms, 3),
                "dreamdb": importlib.metadata.version("dreamdb"),
            }
        ),
        flush=True,
    )


def main():
    if len(sys.argv) == 3:
        {"write": write, "read": read}[sys.argv[1]](Path(sys.argv[2]).resolve())
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: python check_storage.py")
    with tempfile.TemporaryDirectory(prefix="ddb-mjlab-storage-check-") as temp:
        for mode in ["write", "read"]:
            subprocess.run([sys.executable, "-B", __file__, mode, temp], check=True, timeout=120)
    print("PASS: independent storage round trip; temporary data removed", flush=True)


if __name__ == "__main__":
    main()
