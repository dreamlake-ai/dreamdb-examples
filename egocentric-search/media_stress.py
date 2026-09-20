"""Independent-Ref write staircase using 16 real original/preview clip pairs.

No encoding, consolidation, automatic retry, or source mutation. The same
bounded payload is written at every level; reopened media must be byte-exact.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import tempfile
import time
import uuid

import dreamdb as db

ENDPOINT = "https://dreamdb-ego100k-bench-747143892217-20260917.s3.us-east-1.amazonaws.com"
STRIDE = 3_600_000_000_000
FIELDS = ("video_raw", "video_preview")


def worker(ref, clips, directory, barrier):
    # Preload before release; startup-inclusive time includes this local load.
    rows = [{"_anchor": c["anchor"], **{f: (Path(directory) / f"{c['anchor']}-{f}").read_bytes()
             for f in FIELDS}} for c in clips]
    ds = db.Dataset.open(ref, backend=ENDPOINT)
    barrier.wait(timeout=120)
    begin = time.perf_counter()
    report = {"ref": ref, "acknowledged": [], "commit_s": [], "start": begin}
    for row in rows:
        t = time.perf_counter()
        try:
            ds.append_many([row], commit=True)
        except Exception as exc:
            report.update(stop="unacknowledged outcome; no retries", error_type=type(exc).__name__)
            break
        report["commit_s"].append(time.perf_counter() - t)
        report["acknowledged"].append(row["_anchor"])
    report["end"] = time.perf_counter()
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit("new output required")
    prior = json.loads((a.pilot / "semantic-queries.json").read_text())
    if prior.get("status") != "PASS":
        raise RuntimeError("pilot incomplete")
    source = db.Dataset.open(prior["ref"], backend=ENDPOINT)
    if source.current_manifest() != prior["manifest"]:
        raise RuntimeError("source snapshot changed")
    clips = []
    for b in source.iter_all_batches(fields=["raw_sha256", "preview_sha256"],
                                     start_ns=0, end_ns=512 * STRIDE):
        for anchor, raw, preview in zip(b["_time_anchors"], b["raw_sha256"], b["preview_sha256"]):
            if raw is not None:
                clips.append({"anchor": int(anchor), "sha256": dict(zip(FIELDS, [raw, preview]))})
    clips = sorted(clips, key=lambda x: x["anchor"])[:16]
    if len(clips) != 16:
        raise RuntimeError("16 distinct real clip pairs required")
    report = {"status": "STAGING", "source_ref": prior["ref"], "source_tip": prior["manifest"],
              "clips": clips, "levels": [], "http_counts": "not measured",
              "scope": "independent Refs, fixed 16 clips/level, one clip/commit; no consolidation"}
    a.out.write_text(json.dumps(report, indent=2))
    with tempfile.TemporaryDirectory(prefix="ego100k-media-") as directory:
        total = 0
        for c in clips:
            rows = []
            for b in source.iter_all_batches(fields=list(FIELDS), start_ns=c["anchor"], end_ns=c["anchor"] + 1):
                rows.extend((int(anchor), {f: bytes(b[f][i]) for f in FIELDS})
                            for i, anchor in enumerate(b["_time_anchors"]))
            if len(rows) != 1 or rows[0][0] != c["anchor"]:
                raise RuntimeError("source media missing")
            for f, payload in rows[0][1].items():
                if hashlib.sha256(payload).hexdigest() != c["sha256"][f]:
                    raise RuntimeError("source digest mismatch")
                total += len(payload)
                if total > 1024**3:
                    raise RuntimeError("staging exceeds 1 GiB; no benchmark writes performed")
                (Path(directory) / f"{c['anchor']}-{f}").write_bytes(payload)
        report["logical_media_bytes_per_level"] = total
        report["status"] = "RUNNING"
        a.out.write_text(json.dumps(report, indent=2))
        ctx = mp.get_context("spawn")
        for width in (1, 2, 4, 8, 16):
            tag = "ego100k-media-" + uuid.uuid4().hex[:12]
            refs = [f"{tag}-{i}" for i in range(width)]
            for ref in refs:
                schema = db.Schema().add_video("video_raw", mime="mp4").add_video("video_preview", mime="mp4")
                db.Dataset.create(ref, schema, backend=ENDPOINT)
            level = {"writers": width, "refs": refs}
            report["levels"].append(level)
            a.out.write_text(json.dumps(report, indent=2))
            begin = time.perf_counter()
            with ctx.Manager() as manager:
                barrier = manager.Barrier(width)
                with ProcessPoolExecutor(width, mp_context=ctx) as pool:
                    jobs = [pool.submit(worker, refs[i], clips[i::width], directory, barrier) for i in range(width)]
                    results = [j.result() for j in jobs]
            level["wall_s_including_startup_and_local_load"] = time.perf_counter() - begin
            level["workers"] = results
            a.out.write_text(json.dumps(report, indent=2))
            for i, ref in enumerate(refs):
                fresh = db.Dataset.open(ref, backend=ENDPOINT)
                seen = []
                for c in clips[i::width]:
                    for b in fresh.iter_all_batches(fields=list(FIELDS), start_ns=c["anchor"], end_ns=c["anchor"] + 1):
                        for j, anchor in enumerate(b["_time_anchors"]):
                            if int(anchor) != c["anchor"] or any(hashlib.sha256(bytes(b[f][j])).hexdigest() != c["sha256"][f] for f in FIELDS):
                                raise RuntimeError("media changed on readback")
                            seen.append(int(anchor))
                if sorted(seen) != sorted(results[i]["acknowledged"]) or "stop" in results[i]:
                    raise RuntimeError("missing/unacknowledged media or stopped writer")
            level["status"] = "PASS"
            active = max(r["end"] for r in results) - min(r["start"] for r in results)
            level["write_window_s"] = active
            level["logical_media_MiB_s"] = total / 1024**2 / active
            a.out.write_text(json.dumps(report, indent=2))
            print(f"PASS writers={width} window={active:.3f}s logical_MiB_s={level['logical_media_MiB_s']:.3f}", flush=True)
        report["status"] = "PASS"
        a.out.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
