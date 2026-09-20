"""Bounded retrieval-only semantic vector pressure against one pinned pilot."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing as mp
from pathlib import Path
import resource
import time

import dreamdb as db
import numpy as np

ENDPOINT = "https://dreamdb-ego100k-bench-747143892217-20260917.s3.us-east-1.amazonaws.com"


def query(ds, vector):
    return [int(a) for b in ds.iter_vector("frame_siglip", vector, top_k=10,
            nprobe=32, fields=[], as_numpy=True) for a in b["_time_anchors"]]


def worker(ref, tip, vectors, expected, count, start, barrier):
    ds = db.Dataset.open(ref, backend=ENDPOINT)
    if ds.current_manifest() != tip:
        raise RuntimeError("snapshot changed")
    barrier.wait(timeout=120)
    begin = time.perf_counter()
    cpu = time.process_time()
    latencies = []
    for i in range(count):
        index = (start + i) % len(vectors)
        t = time.perf_counter()
        anchors = query(ds, vectors[index])
        latencies.append(time.perf_counter() - t)
        if anchors != expected[index]:
            raise RuntimeError("query anchors/order differ from serial baseline")
    return {"latency_s": latencies, "start": begin, "end": time.perf_counter(),
            "cpu_s": time.process_time() - cpu,
            "max_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit("new output required")
    prior = json.loads((a.pilot / "semantic-queries.json").read_text())
    if prior.get("status") != "PASS":
        raise SystemExit("successful semantic pilot required")
    with np.load(a.pilot / "vecs/0000/0.npz", allow_pickle=False) as z:
        all_vectors = z["frame_siglip__vecs"]
        ids = np.linspace(0, len(all_vectors) - 1, 4, dtype=int)
        vectors = np.asarray(all_vectors[ids], dtype="<f4")
    # Real image vectors probe the same semantic index; these are NOT text-query
    # relevance labels. Encoding is outside the workload entirely.
    ds = db.Dataset.open(prior["ref"], backend=ENDPOINT)
    if ds.current_manifest() != prior["manifest"]:
        raise RuntimeError("pilot snapshot changed")
    expected = [query(ds, v) for v in vectors]
    if any(len(x) != 10 for x in expected):
        raise RuntimeError("serial query incomplete")
    report = {"ref": prior["ref"], "manifest": prior["manifest"],
              "query_vector_rows": ids.tolist(), "top_k": 10, "nprobe": 32,
              "projection": [], "queries_per_level": 64, "levels": [],
              "status": "RUNNING", "http_counts": "not measured",
              "scope": "closed-loop repeated real image vectors; no cold-cache or relevance claim"}
    a.out.write_text(json.dumps(report, indent=2))
    ctx = mp.get_context("spawn")
    for writers in (1, 2, 4, 8, 16):
        print(f"START readers={writers}", flush=True)
        begin = time.perf_counter()
        with ctx.Manager() as manager:
            barrier = manager.Barrier(writers)
            with ProcessPoolExecutor(writers, mp_context=ctx) as pool:
                jobs = [pool.submit(worker, prior["ref"], prior["manifest"],
                        vectors, expected, 64 // writers, i * (64 // writers), barrier)
                        for i in range(writers)]
                results = [j.result() for j in jobs]
        wall = time.perf_counter() - begin
        active = max(r["end"] for r in results) - min(r["start"] for r in results)
        latencies = [v for r in results for v in r["latency_s"]]
        report["levels"].append({"readers": writers, "completed": len(latencies),
            "wall_s_including_startup": wall, "query_window_s": active,
            "qps_query_window": len(latencies) / active,
            "p50_p95_p99_ms": (np.percentile(latencies, [50, 95, 99]) * 1000).tolist(),
            "cpu_s_sum": sum(r["cpu_s"] for r in results),
            "max_worker_rss_kib_linux": max(r["max_rss_kib_linux"] for r in results)})
        a.out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report["levels"][-1]), flush=True)
    report["status"] = "PASS"
    a.out.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
