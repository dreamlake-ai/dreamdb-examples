"""One explicit concurrency level; real precomputed vectors, public SDK only.

Run on Slurm after the pilot. No automatic staircase, merge, or forced overwrite.
Unknown outcomes stop the workload; they are not retried as if known conflicts.
"""
import argparse
import concurrent.futures
import hashlib
import json
import multiprocessing as mp
import os
import re
import random
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

import dreamdb as db
import numpy as np

ENDPOINT = "https://dreamdb-ego100k-bench-747143892217-20260917.s3.us-east-1.amazonaws.com"
FIELD = "frame_siglip"


def safe_error(value):
    text = str(value)
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "HF_TOKEN"):
        if os.environ.get(key):
            text = text.replace(os.environ[key], "<redacted>")
    return re.sub(r"https?://\S+", "<url>", text)[:1500]


def rows_for(vectors, start):
    return [{"_anchor": start + i, FIELD: v,
             "payload_sha256": hashlib.sha256(v.tobytes()).hexdigest()}
            for i, v in enumerate(vectors)]


def worker(backend, ref, vectors, start, batch_size, barrier, backoff):
    result = {"ref": ref, "acknowledged": [], "attempts": [], "conflicts": 0}
    rng = random.Random(400 + start)
    ds = db.Dataset.open(ref, backend=backend)
    barrier.wait(timeout=120)
    begin = time.perf_counter()
    for offset in range(0, len(vectors), batch_size):
        rows = rows_for(vectors[offset:offset + batch_size], start + offset)
        for attempt in range(5):
            if attempt or offset:
                ds = db.Dataset.open(ref, backend=backend)
            t = time.perf_counter()
            try:
                ds.append_many(rows, commit=True)
            except Exception as exc:
                elapsed = time.perf_counter() - t
                # This is the released SDK's explicit PublishConflict text,
                # not a match on generic HTTP failures or the word "conflict".
                known = str(exc).startswith(f"publish conflict on ref `{ref}`:")
                result["attempts"].append({"s": elapsed, "outcome":
                                           "publish_conflict" if known else "unknown"})
                if not known:
                    result["stop"] = "unknown publication outcome; reconcile before retry"
                    result["error_type"] = type(exc).__name__
                    result["error"] = safe_error(exc)
                    result["uncertain_anchors"] = [r["_anchor"] for r in rows]
                    result["elapsed_s"] = time.perf_counter() - begin
                    return result
                result["conflicts"] += 1
                if attempt == 4:
                    result["stop"] = "explicit conflict retry budget exhausted"
                    result["elapsed_s"] = time.perf_counter() - begin
                    return result
                # Bounded backoff, no changes to logical records or anchors.
                delay = (0.025 * 2**attempt if backoff == "short" else
                         rng.uniform(0.5, 1.0) * min(8.0, 2.0**attempt))
                time.sleep(delay)
            else:
                result["attempts"].append({"s": time.perf_counter() - t,
                                           "outcome": "acknowledged"})
                result["acknowledged"].extend(r["_anchor"] for r in rows)
                break
    result["elapsed_s"] = time.perf_counter() - begin
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vectors", type=Path, required=True, help="real pilot .npz shard")
    ap.add_argument("--calibration", type=Path, required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--mode", choices=["independent", "same-ref"], required=True)
    ap.add_argument("--writers", type=int, choices=[1, 2, 4, 8, 16], required=True)
    ap.add_argument("--rows", type=int, default=512, help="fixed total, not per writer")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--backoff", choices=["short", "jitter"], default="short")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--verify-report", type=Path, help="read-only reconciliation; no new writes")
    a = ap.parse_args()
    exact_reader = os.environ.get("DDB_EXACT_READER")
    if not exact_reader or not Path(exact_reader).is_file():
        raise SystemExit("pinned dump_exact_subset is required BEFORE any writes")
    if a.backend != ENDPOINT and not a.backend.startswith("file://"):
        raise SystemExit("isolated benchmark endpoint required")
    if not 0 < a.rows <= 4096 or a.rows % a.writers or not 0 < a.batch <= 512:
        raise SystemExit("invalid bounded workload")
    with np.load(a.vectors, allow_pickle=False) as z:
        vectors = np.asarray(z[f"{FIELD}__vecs"], dtype="<f4")[:a.rows].copy()
    if len(vectors) != a.rows or vectors.shape[1:] != (768,) or not np.isfinite(vectors).all():
        raise SystemExit("insufficient real vectors or invalid shape; never tile the corpus")
    cal = json.loads(a.calibration.read_text())
    # Calibration JSON is field keyed in the shared ingest implementation.
    if FIELD in cal:
        cal = cal[FIELD]
    si, compressor = bytes.fromhex(cal["spatial_index"]), bytes.fromhex(cal["compressor"])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.out.exists():
        raise SystemExit("refusing to overwrite an existing result")
    payload_hash = hashlib.sha256(a.vectors.read_bytes()).hexdigest()
    if a.verify_report:
        report = json.loads(a.verify_report.read_text())
        if (report["payload_file_sha256"] != payload_hash or report["mode"] != a.mode
                or report["writers"] != a.writers or report["logical_vector_bytes"] != vectors.nbytes):
            raise SystemExit("reconciliation input mismatch")
        refs = report["refs"]
        report["reconciles"] = str(a.verify_report)
    else:
        tag = "ego100k-write-" + uuid.uuid4().hex[:12]
        refs = [f"{tag}-{i}" for i in range(a.writers if a.mode == "independent" else 1)]
        for ref in refs:
            schema = (db.Schema().add_embedding(FIELD, 768, algorithm="dreamdb.ivf-cosine",
                       spatial_index=si, compressor=compressor, rerank=True)
                      .add_scalar_string("payload_sha256"))
            db.Dataset.create(ref, schema, backend=a.backend)
        report = {"tag": tag, "mode": a.mode, "writers": a.writers, "refs": refs,
                  "batch_size": a.batch, "backoff": a.backoff, "attempt_limit": 5,
                  "payload_file_sha256": payload_hash,
                  "logical_vector_bytes": vectors.nbytes, "http_counts": "not measured"}
        a.out.write_text(json.dumps(report, indent=2))
        ctx = mp.get_context("spawn")
        begin = time.perf_counter()
        with ctx.Manager() as manager:
            barrier = manager.Barrier(a.writers)
            with concurrent.futures.ProcessPoolExecutor(a.writers, mp_context=ctx) as pool:
                size = a.rows // a.writers
                jobs = [pool.submit(worker, a.backend, refs[i if a.mode == "independent" else 0],
                                    vectors[i * size:(i + 1) * size], i * size,
                                    a.batch, barrier, a.backoff) for i in range(a.writers)]
                report["workers"] = [job.result() for job in jobs]
        report["wall_s_including_startup"] = time.perf_counter() - begin
    report["exact_reader_source"] = "python-v0.0.14:f0d6ac5efd0db17618df24d64e22b1156fb45cac"
    # Persist outcomes before validation so a failing read never erases acks.
    a.out.write_text(json.dumps(report, indent=2))
    issues = []
    for ref in refs:
        expected = {anchor for w in report["workers"] if w["ref"] == ref
                    for anchor in w["acknowledged"]}
        ds = db.Dataset.open(ref, backend=a.backend)
        actual = {}
        # Public ordinary scans reconstruct lossy vectors when compressed.
        # Read scalar identity here, then use the existing exact-sidecar reader.
        for b in ds.iter_all_batches(fields=["payload_sha256"],
                                     start_ns=0, end_ns=a.rows):
            for anchor, digest in zip(b["_time_anchors"], b["payload_sha256"]):
                anchor = int(anchor)
                if anchor in actual:
                    issues.append("duplicate anchor")
                if not 0 <= anchor < a.rows or digest != hashlib.sha256(vectors[anchor].tobytes()).hexdigest():
                    issues.append("metadata content mismatch")
                actual[anchor] = digest
        if set(actual) != expected:
            issues.append(f"{ref}: missing={sorted(expected-set(actual))}, unacknowledged={sorted(set(actual)-expected)}")
        with tempfile.TemporaryDirectory(prefix="ego100k-exact-") as tmp:
            anchors_file = Path(tmp) / "anchors.txt"
            # Include any actually visible, unacknowledged IDs as well.
            anchors_file.write_text("".join(f"{i}\n" for i in sorted(actual)))
            prefix = Path(tmp) / "readback"
            p = subprocess.run([exact_reader, "--backend", a.backend, "--src-ref", ref,
                                "--field", FIELD, "--dim", "768", "--anchors",
                                str(anchors_file), "--out", str(prefix)], capture_output=True)
            # The existing CLI permits small missing subsets; ignore neither
            # its failure nor omissions. Independent Refs intentionally hold
            # only a partition, so pass that Ref's exact observed anchor set.
            if p.returncode:
                issues.append(f"{ref}: exact reader failed (code {p.returncode})")
                report.setdefault("exact_reader_errors", []).append(safe_error(p.stderr.decode(errors="replace")))
            elif prefix.with_suffix(".anchor.u64").exists():
                ids = np.fromfile(str(prefix) + ".anchor.u64", dtype="<u8")
                raw = np.fromfile(str(prefix) + ".vec.f32", dtype="<f4")
                if len(raw) != len(ids) * 768 or set(map(int, ids)) != expected or len(ids) != len(expected):
                    issues.append(f"{ref}: exact anchor/shape mismatch")
                elif raw.tobytes() != vectors[ids.astype(np.int64)].tobytes():
                    issues.append(f"{ref}: exact vector bytes mismatch")
            else:
                issues.append(f"{ref}: exact reader produced no output")
    report["readback_issues"] = issues
    report["status"] = "PASS" if not issues and not any("stop" in w for w in report["workers"]) else "STOP"
    a.out.write_text(json.dumps(report, indent=2))
    print(report["status"], a.out)
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
