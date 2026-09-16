"""Bounded real PPO integration and three warm fixed-action off/on pairs.

No convergence claim. No network backend or cluster-scale performance claim.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

STEPS = 16
ENVS = 32


class MemorySample:
    """Linux current RSS sampled every 50 ms; not an exact allocation peak."""

    def __init__(self, child=None):
        self.child = child
        self.peaks = {"producer_rss_bytes": 0, "writer_rss_bytes": 0}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            for key, pid in [("producer_rss_bytes", os.getpid()), ("writer_rss_bytes", self.child)]:
                if pid is None:
                    continue
                try:
                    lines = Path(f"/proc/{pid}/status").read_text().splitlines()
                except FileNotFoundError:
                    continue
                rss = next(
                    (int(line.split()[1]) * 1024 for line in lines if line.startswith("VmRSS:")), 0
                )
                self.peaks[key] = max(self.peaks[key], rss)
            self.stop.wait(0.05)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()


def disk_usage(root):
    files = [p for p in root.rglob("*") if p.is_file()]
    return {"backend_files": len(files), "backend_bytes": sum(p.stat().st_size for p in files)}


def fixed_run(root, recording, batch_rows):
    import torch
    from check_capture import SEED, action_for, make_env
    from training import attach_writer

    started = time.perf_counter()
    env = make_env(auto_reset=True, record=recording)
    writer = recorder = None
    try:
        if recording:
            writer, recorder = attach_writer(env, root, batch_rows=batch_rows)
        torch.cuda.synchronize()
        setup = time.perf_counter() - started
        torch.cuda.reset_peak_memory_stats()
        with MemorySample(writer.pid if writer else None) as memory, torch.inference_mode():
            started = time.perf_counter()
            obs, _ = env.reset(seed=SEED)
            for step in range(STEPS):
                action = action_for(step, env)
                if recorder:
                    recorder.begin_step(obs["actor"], action)
                obs, *_ = env.step(action)
            torch.cuda.synchronize()
            loop = time.perf_counter() - started
            if writer:
                recorder.flush()
                writer.finish()
            total = time.perf_counter() - started
        result = {
            "recording": recording,
            "batch_rows": batch_rows,
            "setup_seconds": setup,
            "loop_seconds": loop,
            "with_drain_seconds": total,
            "env_steps_per_second": ENVS * STEPS / total,
            "simulated_env_seconds": ENVS * STEPS * env.step_dt,
            **memory.peaks,
            "torch_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "torch_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        }
        if writer:
            result.update(writer.stats)
            result.update(disk_usage(root))
            result.update(
                capture_seconds=recorder.capture_seconds, copy_seconds=recorder.copy_seconds
            )
            result["writer_rows_per_append_second"] = (
                writer.stats["submitted_rows"] / writer.stats["append_seconds"]
            )
            result["backend_bytes_per_wall_second"] = result["backend_bytes"] / total
        return result
    finally:
        if writer:
            writer.abort()
        env.close()


def performance(root, batch_rows):
    # Same process/runtime: one full unrecorded workload warms JIT before pairs.
    fixed_run(root / "warmup", False, batch_rows)
    results = []
    for pair, order in enumerate(((False, True), (True, False), (False, True))):
        for recording in order:
            with tempfile.TemporaryDirectory(dir=root, prefix="pair-") as temp:
                result = fixed_run(Path(temp) / "backend", recording, batch_rows)
                result["pair"] = pair
                results.append(result)
                print("PERF_RUN " + json.dumps(result), flush=True)
    (root / f"performance-{batch_rows}.json").write_text(json.dumps(results))


def ppo(root, batch_rows=64):
    from dataclasses import asdict

    import torch
    from check_capture import make_env
    from mjlab.rl.runner import MjlabOnPolicyRunner
    from mjlab.tasks.cartpole.cartpole_env_cfg import cartpole_ppo_runner_cfg
    from training import RecordingVecEnv, attach_writer

    env = make_env(auto_reset=True)
    writer = None
    try:
        writer, recorder = attach_writer(env, root / "backend", batch_rows=batch_rows)
        wrapped = RecordingVecEnv(env)
        cfg = asdict(cartpole_ppo_runner_cfg())
        cfg["num_steps_per_env"] = STEPS // 2
        cfg["actor"].update(hidden_dims=(32, 32), obs_normalization=False)
        cfg["critic"].update(hidden_dims=(32, 32), obs_normalization=False)
        cfg["algorithm"].update(num_learning_epochs=2, num_mini_batches=2)
        cfg["logger"] = "tensorboard"
        runner = MjlabOnPolicyRunner(wrapped, cfg, log_dir=None, device="cuda:0")
        initial = [p.detach().clone() for p in runner.alg.actor.parameters()]
        observations, actions, dones = [], [], []
        learn_seconds = 0.0
        with MemorySample(writer.pid) as memory:
            torch.cuda.reset_peak_memory_stats()
            for _ in range(2):
                torch.cuda.synchronize()
                started = time.perf_counter()
                runner.learn(1, init_at_random_ep_len=False)
                torch.cuda.synchronize()
                learn_seconds += time.perf_counter() - started
                # Read, never modify, the actual rollout arrays. clear() resets
                # only its cursor in the pinned RSL-RL; values remain available.
                storage = runner.alg.storage
                observations.append(storage.observations["actor"].detach().cpu().numpy().copy())
                actions.append(storage.actions.detach().cpu().numpy().copy())
                dones.append(storage.dones.detach().cpu().numpy().copy())
            changed = any(
                not torch.equal(a, b)
                for a, b in zip(initial, runner.alg.actor.parameters(), strict=True)
            )
            assert changed, "PPO returned without changing actor parameters"
            assert all(torch.isfinite(p).all() for p in runner.alg.actor.parameters())
            started = time.perf_counter()
            recorder.flush()
            tip = writer.finish()
            drain_seconds = time.perf_counter() - started
        np.savez(
            root / "rollout.npz",
            obs=np.concatenate(observations),
            actions=np.concatenate(actions),
            dones=np.concatenate(dones),
        )
        receipt = {
            "batch_rows": batch_rows,
            "manifest": tip,
            "updates": 2,
            "actor_changed": changed,
            "learn_seconds": learn_seconds,
            "drain_seconds": drain_seconds,
            "capture_seconds": recorder.capture_seconds,
            "copy_seconds": recorder.copy_seconds,
            **writer.stats,
            **memory.peaks,
            **disk_usage(root / "backend"),
            "torch_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "torch_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        }
        (root / "ppo.json").write_text(json.dumps(receipt))
        print("PPO_RUN " + json.dumps(receipt), flush=True)
    finally:
        if writer:
            writer.abort()
        env.close()


def verify_ppo(root):
    import dreamdb
    from store import episode_status, read_window

    receipt = json.loads((root / "ppo.json").read_text())
    dataset = dreamdb.Dataset.open_by_manifest(
        receipt["manifest"], backend=(root / "backend").as_uri()
    )
    rows = read_window(
        dataset,
        [
            "kind",
            "env_id",
            "episode_id",
            "step_id",
            "sim_step",
            "obs_t",
            "action",
            "terminated",
            "truncated",
        ],
        1,
        receipt["submitted_rows"] + 1,
    )
    transitions = sorted(
        (r for r in rows if r["kind"] == "transition"), key=lambda r: (r["sim_step"], r["env_id"])
    )
    assert len(transitions) == ENVS * STEPS
    assert [(r["sim_step"], r["env_id"]) for r in transitions] == [
        (s, e) for s in range(1, STEPS + 1) for e in range(ENVS)
    ]
    with np.load(root / "rollout.npz") as rollout:
        np.testing.assert_array_equal(
            np.stack([r["obs_t"] for r in transitions]), rollout["obs"].reshape(-1, 5)
        )
        np.testing.assert_array_equal(
            np.stack([r["action"] for r in transitions]), rollout["actions"].reshape(-1, 1)
        )
        np.testing.assert_array_equal(
            [r["terminated"] or r["truncated"] for r in transitions],
            rollout["dones"].reshape(-1).astype(bool),
        )
    identities = {(r["env_id"], r["episode_id"]) for r in rows}
    statuses = [
        episode_status([r for r in rows if (r["env_id"], r["episode_id"]) == identity])
        for identity in identities
    ]
    assert statuses.count("incomplete") == ENVS
    assert sum(r["terminated"] for r in transitions) > 0
    assert sum(r["truncated"] for r in transitions) > 0
    end = read_window(dataset, ["kind"], len(rows) + 1, len(rows) + 2)
    assert end[0]["kind"] == "run_end"
    print(
        "PPO_ACCEPTANCE "
        + json.dumps(
            {
                "result": "PASS",
                "rollout_transitions_exact": len(transitions),
                "complete_episodes": statuses.count("complete"),
                "incomplete_episodes": statuses.count("incomplete"),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", nargs="?", default="all", choices=["all", "performance", "ppo", "verify"]
    )
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--batch-rows", type=int, default=64)
    args = parser.parse_args()
    if args.mode == "all":
        if args.directory:
            parser.error("all creates and cleans its own directory")
        with tempfile.TemporaryDirectory(prefix="ddb-mjlab-training-") as temp:
            environment = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "MJLAB_REFERENCE_CACHE": temp + "/cache",
                "XDG_CACHE_HOME": temp + "/cache",
                "CUDA_CACHE_PATH": temp + "/cuda",
            }
            for mode in ("performance", "ppo", "verify"):
                command = [
                    sys.executable,
                    "-B",
                    "-u",
                    __file__,
                    mode,
                    temp,
                    "--batch-rows",
                    str(args.batch_rows),
                ]
                with subprocess.Popen(command, env=environment, start_new_session=True) as child:
                    try:
                        code = child.wait(timeout=300)
                    except BaseException:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                        raise
                    if code:
                        raise subprocess.CalledProcessError(code, command)
        print("TRAINING_CLEANED: temporary data/reference/cache removed", flush=True)
    else:
        if args.directory is None:
            parser.error("individual modes require a directory")
        args.directory.mkdir(exist_ok=True)
        if args.mode == "performance":
            performance(args.directory.resolve(), args.batch_rows)
        elif args.mode == "ppo":
            ppo(args.directory.resolve(), args.batch_rows)
        else:
            verify_ppo(args.directory.resolve())
