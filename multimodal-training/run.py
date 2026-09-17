"""Small real image/sensor → DreamDB → training application, not a framework."""

from __future__ import annotations

import argparse
import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from data import SIZE, Reader, Stats, Writer, png

ENVS, STEPS, EPISODES = 8, 16, 2


def capture(root):
    import importlib.metadata

    import mujoco
    import torch
    import warp as wp
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.cartpole.cartpole_env_cfg import cartpole_balance_env_cfg

    wp.config.kernel_cache_dir = str(root / "cache" / "warp")
    cfg = cartpole_balance_env_cfg()
    cfg.scene.num_envs = ENVS
    cfg.auto_reset = False
    cfg.seed = 71
    cfg.episode_length_s = STEPS * cfg.decimation * cfg.sim.mujoco.timestep
    for group in cfg.observations.values():
        group.enable_corruption = False
    env = ManagerBasedRlEnv(cfg, device="cuda:0")
    renderer = None
    try:
        model = env.sim.mj_model
        if model.na or env.sim.expanded_fields or model.nq != 2 or model.nv != 2:
            raise ValueError("fixed Cartpole model required")
        joints = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(model.njnt)]
        slider = next(i for i, name in enumerate(joints) if name.split("/")[-1] == "slider")
        hinge = next(i for i, name in enumerate(joints) if name.split("/")[-1] == "hinge_1")
        x, theta = int(model.jnt_qposadr[slider]), int(model.jnt_qposadr[hinge])
        dx, dtheta = int(model.jnt_dofadr[slider]), int(model.jnt_dofadr[hinge])
        camera = next(
            i
            for i in range(model.ncam)
            if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_CAMERA, i).split("/")[-1] == "fixed"
        )
        metadata = {
            "image_shape": [SIZE, SIZE, 3],
            "sensor_dim": model.nq + model.nv,
            "sensor_layout": "pre-action qpos followed by qvel; model joint order",
            "anchor_encoding": "logical-record-ordinal-v1",
            "clock": "pre-action sim_time",
            "policy": "clip(-0.5*x + 2*theta - 0.25*dx + 0.5*dtheta, -1, 1)",
            "task": "Mjlab-Cartpole-Balance",
            "control_dt": env.step_dt,
            "seed": 71,
            "camera": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_CAMERA, camera),
            "versions": {
                k: importlib.metadata.version(k)
                for k in ("dreamdb", "mjlab", "mujoco", "torch", "numpy", "pillow")
            },
        }
        writer = Writer(root / "backend", metadata)
        renderer = mujoco.Renderer(model, height=SIZE, width=SIZE)
        render_state = mujoco.MjData(model)
        images, sensors, actions, identities = [], [], [], []
        pending = []
        started = time.perf_counter()

        def cpu(tensor):
            return tensor.detach().cpu().numpy().copy()

        with torch.inference_mode():
            for episode in range(EPISODES):
                env.reset(seed=71 + episode)
                for step in range(STEPS):
                    qpos, qvel, times = (
                        cpu(env.sim.data.qpos),
                        cpu(env.sim.data.qvel),
                        cpu(env.sim.data.time),
                    )
                    sensor = np.concatenate([qpos, qvel], axis=1).astype("<f4")
                    action = np.clip(
                        -0.5 * qpos[:, x]
                        + 2 * qpos[:, theta]
                        - 0.25 * qvel[:, dx]
                        + 0.5 * qvel[:, dtheta],
                        -1,
                        1,
                    ).astype("<f4")[:, None]
                    mocap_pos, mocap_quat = (
                        cpu(env.sim.data.mocap_pos),
                        cpu(env.sim.data.mocap_quat),
                    )
                    frames = []
                    for i in range(ENVS):
                        mujoco.mj_resetData(model, render_state)
                        render_state.qpos[:] = qpos[i]
                        render_state.qvel[:] = qvel[i]
                        render_state.time = float(times[i])
                        render_state.mocap_pos[:] = mocap_pos[i]
                        render_state.mocap_quat[:] = mocap_quat[i]
                        mujoco.mj_forward(model, render_state)
                        renderer.update_scene(render_state, camera=camera)
                        frames.append(renderer.render().copy())
                    _, _, terminated, truncated, _ = env.step(
                        torch.from_numpy(action).to(env.device)
                    )
                    term, trunc = cpu(terminated), cpu(truncated)
                    if step < STEPS - 1 and (term | trunc).any():
                        raise ValueError(
                            "unexpected early terminal; refuse to fabricate full episodes"
                        )
                    if step == STEPS - 1 and not (term | trunc).all():
                        raise ValueError("capture prefix not complete")
                    for i in range(ENVS):
                        pending.append(
                            {
                                "env_id": i,
                                "episode_id": episode,
                                "step_id": step,
                                "sim_time": float(times[i]),
                                "terminated": bool(term[i]),
                                "truncated": bool(trunc[i]),
                                "image": png(frames[i]),
                                "sensor": sensor[i],
                                "action": action[i],
                            }
                        )
                        images.append(frames[i])
                        sensors.append(sensor[i])
                        actions.append(action[i])
                        identities.append([i, episode, step])
                    if len(pending) >= 64:
                        writer.append(pending)
                        pending = []
        writer.append(pending)
        np.savez(
            root / "witness.npz",
            images=np.stack(images),
            sensors=np.stack(sensors),
            actions=np.stack(actions),
            identities=np.asarray(identities),
        )
        receipt = writer.receipt()
        (root / "receipt.json").write_text(json.dumps(receipt))
        print(
            "CAPTURE "
            + json.dumps(
                {
                    **receipt,
                    "rows": len(images),
                    "seconds": time.perf_counter() - started,
                    "versions": metadata["versions"],
                }
            ),
            flush=True,
        )
    finally:
        if renderer is not None:
            renderer.close()
        env.close()


def same(actual, expected):
    for key in actual:
        a, b = actual[key], expected[key]
        assert a.dtype == b.dtype and a.shape == b.shape, key
        assert a.tobytes() == b.tobytes(), key


def observe_reads(reader, root):
    """Compare the same samples; counters are SDK payload, not physical IO."""
    reports = {
        name: {**asdict(Stats()), "seconds": 0.0, "first_batch_seconds": None}
        for name in ("single", "batch")
    }
    with np.load(root / "witness.npz") as witness:
        for offset in range(0, len(reader.samples), 16):
            requests = reader.samples[offset : offset + 16]
            results = {}
            for mode in ("single", "batch") if offset // 16 % 2 == 0 else ("batch", "single"):
                started = time.perf_counter()
                pieces = []
                for group in [requests] if mode == "batch" else [[r] for r in requests]:
                    output, stats = reader.batch(group)
                    pieces.append(output)
                    for key, value in asdict(stats).items():
                        reports[mode][key] += value
                results[mode] = {
                    key: np.concatenate([piece[key] for piece in pieces]) for key in pieces[0]
                }
                elapsed = time.perf_counter() - started
                reports[mode]["seconds"] += elapsed
                if reports[mode]["first_batch_seconds"] is None:
                    reports[mode]["first_batch_seconds"] = elapsed
            same(results["single"], results["batch"])
            result = results["batch"]
            indices = result["anchors"] - 1
            same(
                result,
                {
                    "anchors": result["anchors"],
                    "images": witness["images"][indices],
                    "sensors": witness["sensors"][indices],
                    "targets": witness["actions"][indices[:, -1]],
                },
            )
            for selection, (key, start) in zip(indices, requests, strict=True):
                np.testing.assert_array_equal(
                    witness["identities"][selection],
                    [[*key, step] for step in range(start, start + 4)],
                )
    return reports


def train(root):
    import torch
    from network import make_model
    from torch import nn

    torch.manual_seed(71)
    torch.set_num_threads(4)
    receipt = json.loads((root / "receipt.json").read_text())
    reader = Reader((root / "backend").as_uri(), receipt)
    reports = observe_reads(reader, root)
    training = [r for r in reader.samples if r[0][0] < 6]
    validation = [r for r in reader.samples if r[0][0] >= 6]
    assert training and validation
    assert not ({r[0] for r in training} & {r[0] for r in validation})

    device = "cuda:0"
    model = make_model(reader.metadata["sensor_dim"]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    initial = [p.detach().clone() for p in model.parameters()]
    load_seconds = compute_seconds = 0.0
    updates = 0
    losses = []
    first_input_seconds = None
    rng = np.random.default_rng(71)
    for _ in range(2):
        order = rng.permutation(len(training))
        for offset in range(0, len(order), 16):
            requests = [training[i] for i in order[offset : offset + 16]]
            start = time.perf_counter()
            batch, _ = reader.batch(requests)
            images = (
                torch.from_numpy(batch["images"])
                .permute(0, 1, 4, 2, 3)
                .reshape(-1, 12, SIZE, SIZE)
                .to(device=device, dtype=torch.float32)
                / 255
            )
            sensors = torch.from_numpy(batch["sensors"]).to(device)
            target = torch.from_numpy(batch["targets"]).to(device)
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            load_seconds += elapsed
            if first_input_seconds is None:
                first_input_seconds = elapsed
            start = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.mse_loss(model(images, sensors), target)
            assert torch.isfinite(loss)
            loss.backward()
            optimizer.step()
            torch.cuda.synchronize()
            compute_seconds += time.perf_counter() - start
            losses.append(float(loss.detach()))
            updates += 1
    assert all(torch.isfinite(p).all() for p in model.parameters())
    assert any(not torch.equal(a, p) for a, p in zip(initial, model.parameters(), strict=True))
    model.eval()
    squared_error = count = 0
    with torch.inference_mode():
        for offset in range(0, len(validation), 16):
            batch, _ = reader.batch(validation[offset : offset + 16])
            images = (
                torch.from_numpy(batch["images"])
                .permute(0, 1, 4, 2, 3)
                .reshape(-1, 12, SIZE, SIZE)
                .to(device=device, dtype=torch.float32)
                / 255
            )
            pred = model(images, torch.from_numpy(batch["sensors"]).to(device))
            error = (pred - torch.from_numpy(batch["targets"]).to(device)).square()
            assert torch.isfinite(error).all()
            squared_error += float(error.sum())
            count += error.numel()
    report = {
        "result": "PASS",
        "manifest": reader.manifest,
        "samples": len(reader.samples),
        "train_samples": len(training),
        "validation_samples": len(validation),
        "exact_capture_comparison": True,
        "index_seconds": reader.index_seconds,
        "read_comparison": reports,
        "optimizer_updates": updates,
        "train_first_loss": losses[0],
        "train_last_loss": losses[-1],
        "validation_mse": squared_error / count,
        "loader_and_transfer_seconds": load_seconds,
        "compute_seconds": compute_seconds,
        "first_training_input_seconds": first_input_seconds,
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "boundary": "single local run; returned bytes not physical IO; no cold-cache or scale claim",
    }
    print("MULTIMODAL_ACCEPTANCE " + json.dumps(report), flush=True)


def preflight(root):
    writer = Writer(root / "backend", {"image_shape": [SIZE, SIZE, 3], "sensor_dim": 4})
    rows = []
    pixels = []
    for step in range(4):
        frame = np.full((SIZE, SIZE, 3), 31 * step, dtype=np.uint8)
        pixels.append(frame)
        rows.append(
            {
                "env_id": 0,
                "episode_id": 0,
                "step_id": step,
                "sim_time": step * 0.05,
                "terminated": False,
                "truncated": step == 3,
                "image": png(frame),
                "sensor": np.arange(4, dtype="<f4") + step,
                "action": np.asarray([step / 8], dtype="<f4"),
            }
        )
    writer.append(rows)
    reader = Reader((root / "backend").as_uri(), writer.receipt())
    batch, _ = reader.batch(reader.samples)
    same(
        batch,
        {
            "anchors": np.asarray([[1, 2, 3, 4]], dtype=np.int64),
            "images": np.asarray([pixels]),
            "sensors": np.asarray([[r["sensor"] for r in rows]]),
            "targets": np.asarray([rows[-1]["action"]]),
        },
    )
    print("PREFLIGHT PASS: public image/array/scalar write and pinned projected read", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["all", "capture", "train", "preflight"])
    parser.add_argument("directory", nargs="?", type=Path)
    args = parser.parse_args()
    if args.mode in ("all", "preflight"):
        if args.directory:
            parser.error("coordinator owns temporary directory")
        with tempfile.TemporaryDirectory(prefix="ddb-multimodal-") as temp:
            if args.mode == "preflight":
                preflight(Path(temp))
            else:
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "XDG_CACHE_HOME": temp + "/cache",
                    "CUDA_CACHE_PATH": temp + "/cuda",
                }
                for mode in ("capture", "train"):
                    with subprocess.Popen(
                        [sys.executable, "-B", "-u", __file__, mode, temp],
                        env=environment,
                        start_new_session=True,
                    ) as child:
                        try:
                            code = child.wait(timeout=240)
                        except BaseException:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                            raise
                        if code:
                            raise subprocess.CalledProcessError(code, mode)
        print("CLEANED: task dataset, witnesses and caches", flush=True)
    else:
        if args.directory is None:
            parser.error("individual phase requires directory")
        {"capture": capture, "train": train}[args.mode](args.directory.resolve())


if __name__ == "__main__":
    main()
