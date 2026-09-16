"""Bounded Slurm acceptance: actual auto-reset recorder vs manual-reset execution.

Not training, not a performance benchmark. Modes run as separate processes:
capture -> reference -> verify. Only the verifier reads DreamDB. No private
database reader or object-format access; the reference uses public env.step/reset.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ENVS = 32
STEPS = 11
SEED = 71


def acceptance_termination(env):
    """Explicit test variation, NOT native Cartpole fall termination."""
    import torch

    return (torch.arange(env.num_envs, device=env.device) % 2 == 0) & (env.episode_length_buf >= 3)


def make_env(auto_reset):
    import warp as wp

    if cache := os.environ.get("MJLAB_REFERENCE_CACHE"):
        wp.config.kernel_cache_dir = str(Path(cache) / "warp")
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.managers import TerminationTermCfg
    from mjlab.tasks.cartpole.cartpole_env_cfg import cartpole_balance_env_cfg

    cfg = cartpole_balance_env_cfg()
    cfg.scene.num_envs = ENVS
    cfg.seed = SEED
    cfg.auto_reset = auto_reset
    cfg.episode_length_s = 0.2  # Four control steps.
    for group in cfg.observations.values():
        group.enable_corruption = False
    cfg.terminations["acceptance_even_env_length3"] = TerminationTermCfg(
        func=acceptance_termination
    )
    if auto_reset:
        from capture import DreamDBRecorder
        from mjlab.managers.recorder_manager import RecorderTermCfg

        cfg.recorders = {"dreamdb": RecorderTermCfg(func=DreamDBRecorder)}
    env = ManagerBasedRlEnv(cfg, device="cuda:0")
    capability = {
        "na": env.sim.mj_model.na,
        "nmocap": env.sim.mj_model.nmocap,
        "expanded_fields": sorted(env.sim.expanded_fields),
    }
    print("MODEL_CAPABILITY " + json.dumps(capability), flush=True)
    if env.sim.mj_model.na or env.sim.expanded_fields:
        env.close()
        raise RuntimeError(f"unsupported fixed-model envelope: {capability}")
    return env


def action_for(step, env):
    import torch

    return (((torch.arange(ENVS, device=env.device) + step) % 7 - 3) / 8).float()[:, None]


def capture_run(root):
    import mujoco
    import torch
    from writer import BoundedWriter

    env = make_env(auto_reset=True)
    writer = None
    try:
        model_path = root / "model.mjb"
        mujoco.mj_saveModel(env.sim.mj_model, str(model_path))
        model_bytes = model_path.read_bytes()
        model_path.unlink()
        metadata = {
            "run_id": "capture-acceptance",
            "task": "Mjlab-Cartpole-Balance",
            "variation": "even-env termination at 3 steps; all-env timeout at 4; noise disabled",
            "dimensions": {
                "qpos": env.sim.mj_model.nq,
                "qvel": env.sim.mj_model.nv,
                "obs_t": 5,
                "obs_after": 5,
                "action": 1,
            },
            "mujoco_version": mujoco.__version__,
            "platform": platform.platform(),
            "model_platform": {"system": platform.system(), "machine": platform.machine()},
            "mjlab_version": importlib.metadata.version("mjlab"),
            "torch_version": torch.__version__,
            "seed": SEED,
            "envs": ENVS,
            "control_dt": env.step_dt,
            "decimation": env.cfg.decimation,
            "mocap_count": env.sim.mj_model.nmocap,
        }
        if metadata["mocap_count"]:
            metadata["dimensions"].update(
                {
                    "mocap_pos": 3 * metadata["mocap_count"],
                    "mocap_quat": 4 * metadata["mocap_count"],
                }
            )
        writer = BoundedWriter(root / "backend", metadata, model_bytes, slots=1)
        recorder = env.recorder_manager.get_term("dreamdb")
        recorder.attach(writer)
        with torch.inference_mode():
            obs, _ = env.reset(seed=SEED)
            for step in range(STEPS):
                action = action_for(step, env)
                recorder.begin_step(obs["actor"], action)
                obs, *_ = env.step(action)
            recorder.flush()
        tip = writer.finish()
        receipt = {"manifest": tip, "stats": writer.stats}
        (root / "receipt.json").write_text(json.dumps(receipt))
        print("CAPTURE_DONE " + json.dumps(receipt), flush=True)
    finally:
        if writer is not None:
            writer.abort()
        env.close()


def reference_run(root):
    """Observe terminal state outside hooks by disabling auto reset."""
    import mujoco
    import torch

    env = make_env(auto_reset=False)
    rows = []
    poses = []
    pose_data = mujoco.MjData(env.sim.mj_model)
    episodes = np.zeros(ENVS, dtype=np.int64)
    steps = np.zeros(ENVS, dtype=np.int64)

    def cpu(t):
        return t.detach().cpu().numpy().copy()

    def mocap_at(i):
        if not env.sim.mj_model.nmocap:
            return {}
        return {
            name: cpu(getattr(env.sim.data, name)[i]).reshape(-1).tolist()
            for name in ["mocap_pos", "mocap_quat"]
        }

    def pose_at(i, kind, step):
        # Small public-simulation witnesses, including terminal and next reset.
        if i < 2 and episodes[i] < 2 and (kind == "reset" or episodes[i] == 0):
            # GPU-derived xpos can lag integration. Recompute geometry from the
            # live primary state in the original model, without stepping or
            # mutating the simulation. Playback has neither this model nor env.
            pose_data.qpos[:] = cpu(env.sim.data.qpos[i])
            pose_data.mocap_pos[:] = cpu(env.sim.data.mocap_pos[i])
            pose_data.mocap_quat[:] = cpu(env.sim.data.mocap_quat[i])
            mujoco.mj_kinematics(env.sim.mj_model, pose_data)
            poses.append(
                {
                    "env_id": int(i),
                    "episode_id": int(episodes[i]),
                    "step": -1 if kind == "reset" else int(step),
                    "xpos": pose_data.xpos.tolist(),
                    "xmat": pose_data.xmat.tolist(),
                }
            )

    def resets(ids, observation, sim_step):
        pos, vel, times = cpu(env.sim.data.qpos), cpu(env.sim.data.qvel), cpu(env.sim.data.time)
        obs = cpu(observation["actor"])
        for i in ids:
            pose_at(i, "reset", 0)
            rows.append(
                {
                    "kind": "reset",
                    "env_id": int(i),
                    "episode_id": int(episodes[i]),
                    "step_id": 0,
                    "sim_step": sim_step,
                    "sim_time": float(times[i]),
                    "qpos": pos[i].tolist(),
                    "qvel": vel[i].tolist(),
                    "obs_after": obs[i].tolist(),
                    **mocap_at(i),
                }
            )

    try:
        with torch.inference_mode():
            obs, _ = env.reset(seed=SEED)
            resets(range(ENVS), obs, 0)
            for step in range(STEPS):
                before = cpu(obs["actor"])
                action = action_for(step, env)
                act = cpu(action)
                after, reward, terminated, truncated, _ = env.step(action)
                pos, vel, times = (
                    cpu(env.sim.data.qpos),
                    cpu(env.sim.data.qvel),
                    cpu(env.sim.data.time),
                )
                rew, term, trunc, after_obs = (
                    cpu(reward),
                    cpu(terminated),
                    cpu(truncated),
                    cpu(after["actor"]),
                )
                for i in range(ENVS):
                    pose_at(i, "transition", steps[i])
                    done = bool(term[i] or trunc[i])
                    row = {
                        "kind": "transition",
                        "env_id": i,
                        "episode_id": int(episodes[i]),
                        "step_id": int(steps[i]),
                        "sim_step": step + 1,
                        "sim_time": float(times[i]),
                        "qpos": pos[i].tolist(),
                        "qvel": vel[i].tolist(),
                        "obs_t": before[i].tolist(),
                        "action": act[i].tolist(),
                        "reward": float(rew[i]),
                        "terminated": bool(term[i]),
                        "truncated": bool(trunc[i]),
                        "next_observation_valid": not done,
                        **mocap_at(i),
                    }
                    if not done:
                        row["obs_after"] = after_obs[i].tolist()
                    rows.append(row)
                    steps[i] += 1
                ids = torch.nonzero(terminated | truncated, as_tuple=False).flatten()
                obs = after
                if len(ids):
                    selected = cpu(ids)
                    episodes[selected] += 1
                    steps[selected] = 0
                    obs, _ = env.reset(env_ids=ids)
                    resets(selected, obs, step + 1)
        (root / "reference.json").write_text(json.dumps(rows, allow_nan=False))
        (root / "poses.json").write_text(json.dumps(poses, allow_nan=False))
        print(f"REFERENCE_DONE {len(rows)} events", flush=True)
    finally:
        env.close()


def verify(root):
    import dreamdb
    from store import episode_status, event_fields, read_header, read_window

    receipt = json.loads((root / "receipt.json").read_text())
    expected = json.loads((root / "reference.json").read_text())
    ds = dreamdb.Dataset.open_by_manifest(receipt["manifest"], backend=(root / "backend").as_uri())
    metadata, _ = read_header(ds)
    actual = read_window(ds, event_fields(metadata), 1, 1 + len(expected))

    def key(r):
        return r["env_id"], r["episode_id"], r["kind"], r["step_id"]

    want_by_key = {key(r): r for r in expected}
    got_by_key = {key(r): r for r in actual}
    if len(got_by_key) != len(actual) or len(want_by_key) != len(expected):
        raise AssertionError("duplicate episode event")
    if got_by_key.keys() != want_by_key.keys():
        raise AssertionError("missing/extra episode event")
    max_error = 0.0
    for identity, want in want_by_key.items():
        got = dict(got_by_key[identity])
        del got["_anchor"]
        if got.keys() != want.keys():
            raise AssertionError(f"field mismatch {identity}")
        for field, value in want.items():
            if isinstance(value, list):
                a = np.asarray(value, dtype="<f4")
                b = got[field]
                if b.dtype != a.dtype or b.shape != a.shape:
                    raise AssertionError(f"array type mismatch {identity}/{field}")
                # Independent GPU executions can differ numerically; this is a
                # state-capture comparison, not a byte-reproducibility promise.
                np.testing.assert_allclose(
                    b, a, rtol=1e-5, atol=1e-6, err_msg=f"{identity}/{field}"
                )
                max_error = max(max_error, float(np.max(np.abs(b - a))))
            elif isinstance(value, float):
                np.testing.assert_allclose(got[field], value, rtol=1e-5, atol=1e-6)
            elif got[field] != value:
                raise AssertionError(f"value mismatch {identity}/{field}")
    identities = {(r["env_id"], r["episode_id"]) for r in actual}
    states = [
        episode_status([r for r in actual if (r["env_id"], r["episode_id"]) == identity])
        for identity in sorted(identities)
    ]
    terminal = sum(r.get("terminated", False) for r in actual)
    timeout = sum(r.get("truncated", False) for r in actual)
    if terminal != 48 or timeout != 32 or states.count("incomplete") != ENVS:
        raise AssertionError("expected independent reset/truncation paths were not reached")
    if receipt["stats"]["submitted_rows"] != len(expected):
        raise AssertionError("capture/write event count differs")
    end = read_window(ds, ["kind", "metadata"], len(expected) + 1, len(expected) + 2)
    if len(end) != 1 or end[0]["kind"] != "run_end":
        raise AssertionError("missing successful drain marker")
    print(
        "CAPTURE_ACCEPTANCE "
        + json.dumps(
            {
                "result": "PASS",
                "events": len(actual),
                "transitions": ENVS * STEPS,
                "terminations": terminal,
                "truncations": timeout,
                "episodes": len(states),
                "complete": states.count("complete"),
                "incomplete": states.count("incomplete"),
                "max_array_difference": max_error,
                "mjlab": metadata["mjlab_version"],
                "writer": receipt["stats"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        choices=["all", "capture", "reference", "verify", "playback"],
    )
    parser.add_argument("directory", nargs="?", type=Path)
    args = parser.parse_args()
    if args.mode == "all":
        if args.directory is not None:
            parser.error("all creates and cleans its own temporary directory")
        with tempfile.TemporaryDirectory(prefix="ddb-mjlab-capture-") as temp:
            environment = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "MJLAB_REFERENCE_CACHE": str(Path(temp) / "cache"),
                "XDG_CACHE_HOME": str(Path(temp) / "cache"),
                "CUDA_CACHE_PATH": str(Path(temp) / "cuda"),
            }
            for mode in ["capture", "reference", "verify", "playback"]:
                command = [sys.executable, "-B", "-u", __file__, mode, temp]
                with subprocess.Popen(command, env=environment, start_new_session=True) as child:
                    try:
                        code = child.wait(timeout=240)
                    except BaseException:
                        # Kill this phase's process group, including its spawned
                        # writer, before removing its temporary backend/cache.
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                        raise
                    if code:
                        raise subprocess.CalledProcessError(code, command)
        print("CAPTURE_CLEANED: temporary dataset/reference/cache removed", flush=True)
    else:
        if args.directory is None:
            parser.error("individual modes require a directory")
        args.directory.mkdir(exist_ok=True)
        from check_playback import check as check_playback

        {
            "capture": capture_run,
            "reference": reference_run,
            "verify": verify,
            "playback": check_playback,
        }[args.mode](args.directory.resolve())
