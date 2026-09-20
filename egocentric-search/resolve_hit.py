"""Resolve a real frame hit to this application's whole-clip media. Read only."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import dreamdb as db

STRIDE_NS = 3_600_000_000_000
ENDPOINT = "https://dreamdb-ego100k-bench-747143892217-20260917.s3.us-east-1.amazonaws.com"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=Path, required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.backend != ENDPOINT or a.out.exists():
        raise SystemExit("isolated endpoint and new output required")
    prior = json.loads(a.queries.read_text())
    if prior.get("status") != "PASS":
        raise SystemExit("completed semantic query required")
    hit = next(int(anchor) for query in prior["results"]
               for anchor in query["anchors"] if int(anchor) % STRIDE_NS)
    # This is an application timestamp convention, NOT a generic DB temporal join.
    base = hit // STRIDE_NS * STRIDE_NS
    ds = db.Dataset.open(prior["ref"], backend=a.backend)
    if ds.current_manifest() != prior["manifest"]:
        raise RuntimeError("query snapshot changed")
    fields = ["clip_key", "duration_s", "raw_sha256", "preview_sha256",
              "video_raw", "video_preview"]
    t = time.perf_counter()
    rows = []
    for batch in ds.iter_all_batches(fields=fields, start_ns=base, end_ns=base + 1):
        for i, anchor in enumerate(batch["_time_anchors"]):
            rows.append((int(anchor), {f: batch[f][i] for f in fields}))
    if len(rows) != 1 or rows[0][0] != base:
        raise RuntimeError("hit's clip is not uniquely readable")
    row = rows[0][1]
    offset_s = (hit - base) / 1e9
    if not row["clip_key"] or not 0 < offset_s < float(row["duration_s"]):
        raise RuntimeError("frame hit falls outside the resolved clip")
    sizes = {}
    for field, digest_field in (("video_raw", "raw_sha256"),
                                ("video_preview", "preview_sha256")):
        value = bytes(row[field])
        if not value or hashlib.sha256(value).hexdigest() != row[digest_field]:
            raise RuntimeError(f"media digest mismatch: {field}")
        sizes[field] = len(value)
    report = {"status": "PASS", "ref": prior["ref"], "manifest": prior["manifest"],
              "hit_anchor": hit, "clip_anchor": base, "offset_s": offset_s,
              "duration_s": row["duration_s"], "media_bytes": sizes,
              "resolve_read_verify_s": time.perf_counter() - t,
              "scope": "one non-base semantic hit; whole-clip bytes, not range playback or recall"}
    a.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
