"""Larger real capture and bounded public projection probes."""
import argparse
import json
import sys
from pathlib import Path

import dreamdb
import numpy as np


def probe(root, mode):
    receipt = json.loads((root / "receipt.json").read_text())
    ds = dreamdb.Dataset.open_by_manifest(receipt["manifest"], backend=(root / "backend").as_uri())
    fields = ["sensor", "action"] if mode == "arrays" else ["image", "sensor", "action"]
    start, stop = (97, 101) if mode in ("narrow", "narrow-repeat") else (97, 129)
    if mode == "narrow-repeat":
        ds.iter_all_batches(fields=fields, start_ns=start, end_ns=stop, batch_size=32)
    # stderr markers delimit query IO within the strace stream; opening a
    # snapshot and loading Python modules are intentionally outside this interval.
    print("DDB_TRACE_START", file=sys.stderr, flush=True)
    batches = ds.iter_all_batches(fields=fields, start_ns=start, end_ns=stop, batch_size=32)
    print("DDB_TRACE_END", file=sys.stderr, flush=True)
    anchors = [a for b in batches for a in b["_time_anchors"]]
    assert anchors == list(range(start, stop))
    assert all(set(b) == set(fields) | {"_time_anchors"} for b in batches)
    returned = sum(len(v) if isinstance(v, bytes) else v.nbytes if isinstance(v, np.ndarray) else 0
                   for b in batches for f in fields for v in b[f])
    print("SELECTIVITY " + json.dumps(dict(mode=mode, rows=len(anchors), returned_bytes=returned)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["capture", "arrays", "combined", "narrow", "narrow-repeat"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory.resolve()
    if args.mode == "capture":
        from run import capture
        capture(root, envs=8, episodes=4, steps=32)
    else:
        probe(root, args.mode)
