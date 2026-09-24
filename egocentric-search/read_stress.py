"""Bounded retrieval-only semantic vector pressure against one pinned pilot.

Extends the original repeated-image-vector closed-loop probe with:
  - diverse real text-query vectors (SigLIP text tower, same spec as the
    corpus's image tower — see EMBED_SPEC), encoded once, outside every timed
    window, per SPEC.md's "Real diverse text queries are encoded outside DB
    timings";
  - per-worker connector `http_stats()` deltas, summed across workers (each
    worker opens its own Dataset via `Dataset.open`, never `branch()`, so per
    dreamdb's own http_stats() docs each gets an independent connector —
    summing deltas across workers is therefore not double counting);
  - explicit offered/completed/error accounting, and a fixed-arrival-rate
    open-loop mode alongside the original closed-loop one.
"""
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

# Matches spaces/ego100k/embedding-original.json, the spec the real corpus was
# ingested with. Confirmed by source inspection: SiglipEmbedder's text and
# image towers are both instantiated from this same "hard" dict, so a text
# query encoded with this spec lands in the identical embedding space as the
# ingested `frame_siglip` image vectors.
EMBED_SPEC = {
    "hard": {
        "model_repo": "google/siglip-base-patch16-224",
        "model_revision": "7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed",
        "dim": 768,
        "text_max_length": 64,
        "text_template": "{}",
    }
}

# Fixed, checked-in prompt set so a run is reproducible and comparable across
# levels/dates. Diverse on purpose (scene, action, object) — not a relevance
# claim, only a saturation/latency probe over distinct index regions instead
# of one repeated vector.
DEFAULT_TEXT_PROMPTS = [
    "a person walking down a hallway",
    "hands assembling a piece of furniture",
    "someone cooking in a kitchen",
    "a close-up of a laptop screen",
    "riding a bicycle outdoors",
    "two people having a conversation",
    "washing dishes at a sink",
    "packing a bag before leaving",
]

HTTP_STATS_KEYS = (
    "attempts_started", "attempts_completed", "retries_internal",
    "put_redirect_hops", "status_2xx", "status_3xx", "status_4xx",
    "status_5xx", "status_412", "transport_errors", "body_errors",
    "cancelled", "request_body_bytes", "response_body_bytes",
    "attempt_nanos_total", "requests_get", "requests_head", "requests_put",
    "requests_post", "requests_delete", "requests_other",
)


def query(ds, vector):
    return [int(a) for b in ds.iter_vector("frame_siglip", vector, top_k=10,
            nprobe=32, fields=[], as_numpy=True) for a in b["_time_anchors"]]


def http_stats_delta(before, after):
    if before is None or after is None:
        return None
    return {k: after[k] - before[k] for k in HTTP_STATS_KEYS}


def sum_http_stats(deltas):
    present = [d for d in deltas if d is not None]
    if not present:
        return None
    return {k: sum(d[k] for d in present) for k in HTTP_STATS_KEYS}


def encode_text_prompts(prompts, spec=None):
    """Encode outside any timed window. Requires the ingest venv (dlingest)."""
    from dlingest.embed import make_embedder
    embedder = make_embedder("siglip", spec=spec or EMBED_SPEC)
    vecs = embedder.embed_texts(prompts)
    return np.asarray(vecs, dtype="<f4")


def _run_query(ds, vector, expected, timeout_s):
    """One query attempt. Returns (elapsed_s, ok, error) — error is an infra
    failure (caught), not a correctness mismatch (stays fatal to the caller,
    since a wrong answer against a pinned snapshot is a potential Core bug,
    not a load-test error to count and move past)."""
    t = time.perf_counter()
    try:
        anchors = query(ds, vector)
    except Exception as exc:                                    # noqa: BLE001
        return time.perf_counter() - t, False, str(exc)[:300]
    elapsed = time.perf_counter() - t
    if anchors != expected:
        raise RuntimeError("query anchors/order differ from serial baseline")
    return elapsed, elapsed <= timeout_s, None


def worker_closed(ref, tip, vectors, expected, count, start, barrier, timeout_s):
    ds = db.Dataset.open(ref, backend=ENDPOINT)
    if ds.current_manifest() != tip:
        raise RuntimeError("snapshot changed")
    barrier.wait(timeout=120)
    before = ds.http_stats()
    begin = time.perf_counter()
    cpu = time.process_time()
    latencies, errors, timeouts = [], 0, 0
    for i in range(count):
        index = (start + i) % len(vectors)
        elapsed, ok, err = _run_query(ds, vectors[index], expected[index], timeout_s)
        latencies.append(elapsed)
        if err is not None:
            errors += 1
        elif not ok:
            timeouts += 1
    end = time.perf_counter()
    after = ds.http_stats()
    return {"latency_s": latencies, "start": begin, "end": end,
            "offered": count, "completed": len(latencies) - errors,
            "errors": errors, "timeouts": timeouts,
            "cpu_s": time.process_time() - cpu,
            "max_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "http_stats_delta": http_stats_delta(before, after)}


def worker_open(ref, tip, vectors, expected, count, start, barrier,
                 rate_qps, timeout_s):
    """Fixed-arrival-rate open loop. Each query is offered on a fixed
    schedule (queries/sec) rather than back-to-back after the previous one
    completes; latency is measured from the SCHEDULED offer time, so a
    worker that falls behind schedule shows it as rising latency rather than
    silently absorbing it, per SPEC.md's "closed-loop throughput is not an
    open-loop latency guarantee."

    This does not preempt or cancel an in-flight call — the installed SDK's
    `iter_vector` has no cancellation/deadline argument — so a query already
    running is not abandoned at its scheduled deadline; it is instead flagged
    as a timeout once it finishes late. `offered` therefore counts scheduled
    ticks reached during the phase, not admitted-into-flight requests.
    """
    ds = db.Dataset.open(ref, backend=ENDPOINT)
    if ds.current_manifest() != tip:
        raise RuntimeError("snapshot changed")
    barrier.wait(timeout=120)
    before = ds.http_stats()
    begin = time.perf_counter()
    cpu = time.process_time()
    latencies, errors, timeouts, offered = [], 0, 0, 0
    interval = 1.0 / rate_qps
    for i in range(count):
        scheduled = begin + i * interval
        now = time.perf_counter()
        if now < scheduled:
            time.sleep(scheduled - now)
        offered += 1
        index = (start + i) % len(vectors)
        try:
            anchors = query(ds, vectors[index])
        except Exception as exc:                                # noqa: BLE001
            errors += 1
            continue
        finished = time.perf_counter()
        if anchors != expected[index]:
            raise RuntimeError("query anchors/order differ from serial baseline")
        elapsed_from_schedule = finished - scheduled
        latencies.append(elapsed_from_schedule)
        if elapsed_from_schedule > timeout_s:
            timeouts += 1
    end = time.perf_counter()
    after = ds.http_stats()
    return {"latency_s": latencies, "start": begin, "end": end,
            "offered": offered, "completed": len(latencies),
            "errors": errors, "timeouts": timeouts,
            "cpu_s": time.process_time() - cpu,
            "max_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "http_stats_delta": http_stats_delta(before, after)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--vector-source", choices=("image", "text"), default="image",
                     help="image: repeated real pilot image vectors (original "
                          "behavior). text: diverse real text-query vectors, "
                          "encoded once before any timed window.")
    ap.add_argument("--text-prompts", type=Path, default=None,
                     help="JSON file with a list of prompt strings. Defaults "
                          "to a fixed built-in prompt set if --vector-source "
                          "text is chosen without this.")
    ap.add_argument("--mode", choices=("closed", "open"), default="closed",
                     help="closed: next query issued as soon as the previous "
                          "completes (original behavior). open: queries "
                          "offered on a fixed schedule (--arrival-rate).")
    ap.add_argument("--arrival-rate", type=float, default=None,
                     help="queries/sec per worker, required for --mode open")
    ap.add_argument("--timeout-s", type=float, default=5.0,
                     help="a query slower than this (closed: call latency; "
                          "open: latency from its scheduled offer time) is "
                          "counted as a timeout, not discarded")
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit("new output required")
    if a.mode == "open" and not a.arrival_rate:
        raise SystemExit("--arrival-rate is required for --mode open")

    prior = json.loads((a.pilot / "semantic-queries.json").read_text())
    if prior.get("status") != "PASS":
        raise SystemExit("successful semantic pilot required")

    if a.vector_source == "text":
        prompts = (json.loads(a.text_prompts.read_text()) if a.text_prompts
                   else DEFAULT_TEXT_PROMPTS)
        vectors = encode_text_prompts(prompts)
        vector_rows = prompts
    else:
        with np.load(a.pilot / "vecs/0000/0.npz", allow_pickle=False) as z:
            all_vectors = z["frame_siglip__vecs"]
            ids = np.linspace(0, len(all_vectors) - 1, 4, dtype=int)
            vectors = np.asarray(all_vectors[ids], dtype="<f4")
        vector_rows = ids.tolist()
        # Real image vectors probe the same semantic index; these are NOT
        # text-query relevance labels. Encoding is outside the workload
        # entirely (they are read pre-encoded from the pilot's stored npz).

    ds = db.Dataset.open(prior["ref"], backend=ENDPOINT)
    if ds.current_manifest() != prior["manifest"]:
        raise RuntimeError("pilot snapshot changed")
    expected = [query(ds, v) for v in vectors]
    if any(len(x) != 10 for x in expected):
        raise RuntimeError("serial query incomplete")

    report = {"ref": prior["ref"], "manifest": prior["manifest"],
              "vector_source": a.vector_source, "query_vector_rows": vector_rows,
              "top_k": 10, "nprobe": 32, "projection": [],
              "queries_per_level": 64, "mode": a.mode,
              "arrival_rate_qps": a.arrival_rate, "timeout_s": a.timeout_s,
              "levels": [], "status": "RUNNING",
              "scope": "closed-loop: offered==completed except on an infra "
                       "error, since the next query is only issued after the "
                       "prior one returns. open-loop: offered counts scheduled "
                       "ticks reached, not admitted in-flight requests; a late "
                       "reply is flagged as a timeout, not preempted, because "
                       "the SDK's iter_vector has no cancellation/deadline "
                       "argument. Neither loop makes a cold-cache or "
                       "relevance claim; http_stats deltas are per-worker "
                       "connector sums (Dataset.open per worker, never "
                       "branch(), so no cross-worker double count)."}
    a.out.write_text(json.dumps(report, indent=2))

    ctx = mp.get_context("spawn")
    for writers in (1, 2, 4, 8, 16):
        print(f"START readers={writers}", flush=True)
        begin = time.perf_counter()
        with ctx.Manager() as manager:
            barrier = manager.Barrier(writers)
            with ProcessPoolExecutor(writers, mp_context=ctx) as pool:
                per_worker = 64 // writers
                if a.mode == "closed":
                    jobs = [pool.submit(worker_closed, prior["ref"], prior["manifest"],
                            vectors, expected, per_worker, i * per_worker, barrier,
                            a.timeout_s) for i in range(writers)]
                else:
                    jobs = [pool.submit(worker_open, prior["ref"], prior["manifest"],
                            vectors, expected, per_worker, i * per_worker, barrier,
                            a.arrival_rate, a.timeout_s) for i in range(writers)]
                results = [j.result() for j in jobs]
        wall = time.perf_counter() - begin
        active = max(r["end"] for r in results) - min(r["start"] for r in results)
        latencies = [v for r in results for v in r["latency_s"]]
        level = {"readers": writers,
            "offered": sum(r["offered"] for r in results),
            "completed": len(latencies),
            "errors": sum(r["errors"] for r in results),
            "timeouts": sum(r["timeouts"] for r in results),
            "wall_s_including_startup": wall, "query_window_s": active,
            "qps_query_window": len(latencies) / active if active > 0 else 0.0,
            "p50_p95_p99_ms": (np.percentile(latencies, [50, 95, 99]) * 1000).tolist()
                              if latencies else None,
            "cpu_s_sum": sum(r["cpu_s"] for r in results),
            "max_worker_rss_kib_linux": max(r["max_rss_kib_linux"] for r in results),
            "http_stats": sum_http_stats([r["http_stats_delta"] for r in results])}
        report["levels"].append(level)
        a.out.write_text(json.dumps(report, indent=2))
        print(json.dumps(level), flush=True)
    report["status"] = "PASS"
    a.out.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
