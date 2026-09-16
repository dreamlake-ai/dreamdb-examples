"""Materialize upstream; deliver bytes; train locally from a fixed input profile."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


def preflight(root):
    from data import Reader
    from run import preflight as storage_preflight
    from run import same
    from stages import LocalBatches, deliver, materialize, ready

    storage_preflight(root)
    import dreamdb

    ds = dreamdb.Dataset.open("capture", backend=(root / "backend").as_uri())
    receipt = {"manifest": ds.current_manifest(), "end_anchor": 5}
    (root / "receipt.json").write_text(json.dumps(receipt))
    reader = Reader((root / "backend").as_uri(), receipt)
    expected, _ = reader.batch(reader.samples)
    materialize(root, root / "ready")
    deliver(root / "ready", root / "delivered")
    local = LocalBatches(root / "delivered")
    same(local.numpy_batch([0]), ready(expected))
    print("STAGES_PREFLIGHT PASS: ready tensor bytes survive materialize/deliver/mmap", flush=True)


def frame_preflight(root):
    import dreamdb
    import numpy as np
    from data import png
    from framebank import FrameBatches, repack
    from run import preflight as storage_preflight
    from run import same
    from stages import LocalBatches, deliver, materialize

    storage_preflight(root)
    ds = dreamdb.Dataset.open("capture", backend=(root / "backend").as_uri())
    # A second, six-step episode creates three genuinely overlapping windows.
    rows = [
        {
            "_anchor": 5 + step,
            "env_id": 1,
            "episode_id": 0,
            "step_id": step,
            "sim_time": step * 0.05,
            "terminated": False,
            "truncated": step == 5,
            "image": png(np.full((64, 64, 3), 17 * step, dtype=np.uint8)),
            "sensor": np.arange(4, dtype="<f4") + step,
            "action": np.asarray([step / 8], dtype="<f4"),
        }
        for step in range(6)
    ]
    assert ds.append_many(rows, commit=True) == 6
    (root / "receipt.json").write_text(
        json.dumps({"manifest": ds.current_manifest(), "end_anchor": 11})
    )
    materialize(root, root / "ready")
    repack(root / "ready", root / "ready-frames")
    deliver(root / "ready-frames", root / "delivered-frames")
    old, bank = LocalBatches(root / "ready"), FrameBatches(root / "delivered-frames")
    # Actual requested reordering and repetition, not a mapping-validator control.
    indices = [3, 0, 2, 1, 3]
    same(old.numpy_batch(indices), bank.numpy_batch(indices))
    print("FRAMEBANK_PREFLIGHT PASS: overlapping/reordered/duplicate windows match", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=[
            "all",
            "compare-frames",
            "preflight",
            "preflight-frames",
            "prepare",
            "prepare-frames",
            "deliver",
            "train-local",
            "verify-local",
        ],
    )
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--layout", choices=["windows", "frames"], default="windows")
    args = parser.parse_args()
    if args.mode in ("all", "compare-frames", "preflight", "preflight-frames"):
        if args.directory:
            parser.error("coordinator owns its temporary directory")
        with tempfile.TemporaryDirectory(prefix="ddb-training-stages-") as temp:
            root = Path(temp)
            if args.mode in ("preflight", "preflight-frames"):
                (frame_preflight if args.mode == "preflight-frames" else preflight)(root)
            else:
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "XDG_CACHE_HOME": temp + "/cache",
                    "CUDA_CACHE_PATH": temp + "/cuda",
                }
                phases = [
                    ("run.py", "capture"),
                    ("run.py", "train"),
                    ("pipeline.py", "prepare"),
                    ("pipeline.py", "deliver"),
                    ("pipeline.py", "verify-local"),
                ]
                if args.mode == "compare-frames":
                    phases = [
                        ("run.py", "capture"),
                        ("pipeline.py", "prepare"),
                        ("pipeline.py", "deliver"),
                        ("pipeline.py", "prepare-frames"),
                        ("pipeline.py", "verify-local"),
                        ("pipeline.py", "verify-local"),
                    ]
                for phase, (script, mode) in enumerate(phases):
                    if mode == "verify-local" and (root / "backend").exists():
                        (root / "backend").rename(root / "offline-source")
                    extra = (
                        ["--layout", "frames"]
                        if args.mode == "compare-frames" and phase == len(phases) - 1
                        else []
                    )
                    with subprocess.Popen(
                        [
                            sys.executable,
                            "-B",
                            "-u",
                            str(Path(__file__).with_name(script)),
                            mode,
                            temp,
                            *extra,
                        ],
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
                            raise subprocess.CalledProcessError(code, [script, mode])
        print("STAGES_CLEANED: capture/artifacts/delivery/witnesses/caches", flush=True)
    else:
        if args.directory is None:
            parser.error("phase needs an explicit directory")
        root = args.directory.resolve()
        if args.mode == "prepare":
            from stages import materialize

            materialize(root, root / "ready")
        elif args.mode == "prepare-frames":
            from framebank import repack
            from stages import deliver

            repack(root / "ready", root / "ready-frames")
            deliver(root / "ready-frames", root / "delivered-frames")
        elif args.mode == "deliver":
            from stages import deliver

            deliver(root / "ready", root / "delivered")
        else:
            from local_train import train_local

            train_local(root, verify=args.mode == "verify-local", layout=args.layout)


if __name__ == "__main__":
    main()
