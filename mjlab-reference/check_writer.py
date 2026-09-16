"""One-slot real backpressure and actual child death, without a mock database."""

from __future__ import annotations

import json
import os
import signal
import tempfile
from pathlib import Path

import dreamdb
from check_storage import equal_rows, events
from store import EVENT_FIELDS, read_window
from writer import BoundedWriter


def main():
    metadata = {
        "run_id": "writer-check",
        "dimensions": {"qpos": 2, "qvel": 2, "obs_t": 5, "obs_after": 5, "action": 1},
    }
    # Asset loading is checked separately; this test needs only opaque u8 bytes.
    with tempfile.TemporaryDirectory(prefix="ddb-writer-check-") as temp:
        root = Path(temp)
        writer = BoundedWriter(root / "backpressure", metadata, b"fixture", slots=1)
        try:
            for row in events():
                writer.submit([row])
            tip = writer.finish()
        finally:
            writer.abort()
        ds = dreamdb.Dataset.open_by_manifest(tip, backend=(root / "backpressure").as_uri())
        expected = [dict(row, _anchor=i + 1) for i, row in enumerate(events())]
        equal_rows(read_window(ds, EVENT_FIELDS, 1, 1 + len(expected)), expected)
        if writer.stats["backpressure_count"] == 0:
            raise AssertionError("workload did not reach backpressure")
        print(json.dumps({"backpressure": "PASS", **writer.stats}), flush=True)

        writer = BoundedWriter(root / "killed", metadata, b"fixture", slots=1)
        try:
            writer.submit(events()[:2])
            writer.drain()  # Known durable prefix before killing our own child.
            os.kill(writer.pid, signal.SIGKILL)
            try:
                writer.finish()
            except (RuntimeError, BrokenPipeError, EOFError, ConnectionResetError):
                pass
            else:
                raise AssertionError("killed writer appeared to finish successfully")
        finally:
            writer.abort()
        ds = dreamdb.Dataset.open("run", backend=(root / "killed").as_uri())
        if ds.query_scalar("kind", "==", "run_end"):
            raise AssertionError("failed writer published a clean run_end")
        equal_rows(read_window(ds, EVENT_FIELDS, 1, 3), expected[:2])
        print("PASS: writer death propagated; durable prefix retained; no run_end", flush=True)


if __name__ == "__main__":
    main()
