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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=["all", "preflight", "prepare", "deliver", "train-local", "verify-local"]
    )
    parser.add_argument("directory", nargs="?", type=Path)
    args = parser.parse_args()
    if args.mode in ("all", "preflight"):
        if args.directory:
            parser.error("coordinator owns its temporary directory")
        with tempfile.TemporaryDirectory(prefix="ddb-training-stages-") as temp:
            root = Path(temp)
            if args.mode == "preflight":
                preflight(root)
            else:
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "XDG_CACHE_HOME": temp + "/cache",
                    "CUDA_CACHE_PATH": temp + "/cuda",
                }
                for script, mode in [
                    ("run.py", "capture"),
                    ("run.py", "train"),
                    ("pipeline.py", "prepare"),
                    ("pipeline.py", "deliver"),
                    ("pipeline.py", "verify-local"),
                ]:
                    if mode == "verify-local":
                        (root / "backend").rename(root / "offline-source")
                    with subprocess.Popen(
                        [
                            sys.executable,
                            "-B",
                            "-u",
                            str(Path(__file__).with_name(script)),
                            mode,
                            temp,
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
        elif args.mode == "deliver":
            from stages import deliver

            deliver(root / "ready", root / "delivered")
        else:
            from local_train import train_local

            train_local(root, verify=args.mode == "verify-local")


if __name__ == "__main__":
    main()
