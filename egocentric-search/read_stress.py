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
# of a handful of repeated vectors. 8 prompts hashed to too few distinct
# index regions to say anything about saturation; this is >=50 by
# construction (asserted at import) so that property can't silently regress.
DEFAULT_TEXT_PROMPTS = [
    "a person walking down a hallway",
    "hands assembling a piece of furniture",
    "someone cooking in a kitchen",
    "a close-up of a laptop screen",
    "riding a bicycle outdoors",
    "two people having a conversation",
    "washing dishes at a sink",
    "packing a bag before leaving",
    "chopping vegetables on a cutting board",
    "typing on a keyboard at a desk",
    "opening a refrigerator door",
    "tying shoelaces",
    "pouring coffee into a mug",
    "wiping down a kitchen counter",
    "folding laundry on a bed",
    "climbing a staircase",
    "sweeping a floor with a broom",
    "reading a book on a couch",
    "loading dishes into a dishwasher",
    "putting on a jacket",
    "watering plants on a windowsill",
    "unlocking a front door with keys",
    "stirring a pot on the stove",
    "plugging in a phone charger",
    "brushing teeth at a bathroom sink",
    "carrying grocery bags into a kitchen",
    "sorting mail at a table",
    "petting a dog on the floor",
    "adjusting a thermostat on the wall",
    "slicing bread with a knife",
    "vacuuming a living room rug",
    "hanging a picture frame on a wall",
    "tightening a bolt with a wrench",
    "filling a water bottle from a tap",
    "stacking chairs in a room",
    "wrapping a gift with paper",
    "scrolling on a phone while seated",
    "wiping a whiteboard with an eraser",
    "putting groceries into a cabinet",
    "tying a knot in a rope",
    "peeling an orange by hand",
    "setting a table with plates",
    "closing a laptop lid",
    "taking a photo with a camera",
    "mixing ingredients in a bowl",
    "changing a lightbulb in a lamp",
    "parking a bicycle against a wall",
    "opening a window curtain",
    "stacking books on a shelf",
    "pressing buttons on a microwave",
    "tying a shoe on a bench",
    "walking a dog on a leash",
    "assembling a cardboard box",
    "pouring cereal into a bowl",
]
assert len(DEFAULT_TEXT_PROMPTS) >= 50, "prompt set must stay >=50 for a real saturation probe"
assert len(set(DEFAULT_TEXT_PROMPTS)) == len(DEFAULT_TEXT_PROMPTS), "prompts must be distinct"

HTTP_STATS_KEYS = (
    "attempts_started", "attempts_completed", "retries_internal",
    "put_redirect_hops", "status_2xx", "status_3xx", "status_4xx",
    "status_5xx", "status_412", "transport_errors", "body_errors",
    "cancelled", "request_body_bytes", "response_body_bytes",
    "attempt_nanos_total", "requests_get", "requests_head", "requests_put",
    "requests_post", "requests_delete", "requests_other", "ranged_gets",
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


# The counters divided here (requests_get, requests_head, ranged_gets,
# response_body_bytes, retries_internal) are each a real field in
# HTTP_STATS_KEYS, i.e. something http_stats() actually counted. Nothing
# here is derived for a field the connector does not itself report.
HTTP_PER_QUERY_RATE_KEYS = (
    "requests_get", "requests_head", "ranged_gets", "response_body_bytes",
)


def http_per_completed_query(http_stats, completed):
    if http_stats is None or completed <= 0:
        return None
    rates = {f"{k}_per_completed_query": http_stats[k] / completed
             for k in HTTP_PER_QUERY_RATE_KEYS}
    rates["retries_internal"] = http_stats["retries_internal"]
    return rates


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


def _open_loop_schedule(vectors, expected, count, start, rate_qps, timeout_s,
                         max_in_flight, worker_index, num_workers, run_query):
    """Fixed GLOBAL-arrival-rate scheduling, admission decoupled from
    completion. Pure — takes `run_query(index) -> anchors` instead of a
    Dataset, so this is directly testable without a backend.

    `rate_qps` is the TOTAL offered rate across all `num_workers` workers
    combined, not a per-worker rate — a worker's own tick spacing is
    `num_workers / rate_qps`, and worker `worker_index`'s j-th tick lands at
    `begin + (worker_index + j * num_workers) / rate_qps`. Interleaving the
    `num_workers` workers' ticks this way (a disjoint round-robin split of
    one global schedule) reproduces the same global tick times a single
    scheduler would use, so summing `offered` across workers gives the CLI's
    `--arrival-rate` value at the intended level, not `--arrival-rate *
    num_workers`.

    A scheduler ticks at a fixed rate, independent of when any prior query
    finished — a version that issues each query synchronously in the
    scheduling loop instead pushes every later tick back by however long the
    prior query took, so it isn't a real fixed-arrival-rate model. Here each
    tick is admitted into a bounded pool of `max_in_flight` concurrently
    in-flight queries (a non-blocking `Semaphore.acquire`); the query then
    runs on its own thread. `iter_vector`'s underlying Rust call releases the
    GIL for the network/compute work (`py.detach` + `block_on` in
    dreamdb-dataset-python/src/lib.rs), so admitted queries genuinely
    overlap rather than serializing behind the Python interpreter.

    Four disjoint, real counts — nothing here is inferred from a count the
    loop did not itself take:
      - `offered`:   every scheduled tick reached, always increments, even
                     while an earlier admitted query is still in flight.
      - `admitted`:  ticks where a slot was free and the query actually
                     started.
      - `dropped`:   ticks where the in-flight pool was full at that tick.
                     A real, explicit drop — the schedule never blocks
                     waiting for a slot, so there is no unbounded backlog
                     to absorb it silently, and no FIFO queue that a
                     "queueing delay" could be measured against.
      - `completed`: admitted queries that returned successfully (len of
                     `latency_s`). `timeouts` is a SUBSET of `completed`,
                     not a separate bucket: a late reply still finished and
                     is counted in both `completed` and `timeouts` — it was
                     never preempted, since the installed SDK's
                     `iter_vector` has no cancellation/deadline argument.
                     `errors` (infra failures) are excluded from
                     `completed`.

    Latency is measured from the query's SCHEDULED tick time to when it
    finished, so it includes scheduling/dispatch/thread-start latency —
    but NOT queueing delay, because there is no queue: a tick that finds
    the pool full is dropped immediately, not held.
    """
    import threading

    begin = time.perf_counter()
    sem = threading.Semaphore(max_in_flight)
    lock = threading.Lock()
    latencies, errors, timeouts = [], 0, 0
    fatal = []

    def run_one(index, scheduled):
        nonlocal errors, timeouts
        try:
            anchors = run_query(index)
        except Exception as exc:                                # noqa: BLE001
            with lock:
                errors += 1
            sem.release()
            return
        finished = time.perf_counter()
        if anchors != expected[index]:
            # A wrong answer against a pinned snapshot is a potential Core
            # bug, not a load-test error to count and move past — but
            # raising from a non-main thread is silently swallowed by the
            # interpreter, so stash it and re-raise on the scheduling
            # thread once every worker thread has been joined.
            fatal.append("query anchors/order differ from serial baseline")
            sem.release()
            return
        elapsed_from_schedule = finished - scheduled
        with lock:
            latencies.append(elapsed_from_schedule)
            if elapsed_from_schedule > timeout_s:
                timeouts += 1
        sem.release()

    threads = []
    offered = admitted = dropped = 0
    offer_times = []
    for j in range(count):
        scheduled = begin + (worker_index + j * num_workers) / rate_qps
        now = time.perf_counter()
        if now < scheduled:
            time.sleep(scheduled - now)
        offered += 1
        offer_times.append(time.perf_counter())
        index = (start + j) % len(vectors)
        if sem.acquire(blocking=False):
            admitted += 1
            th = threading.Thread(target=run_one, args=(index, scheduled))
            th.start()
            threads.append(th)
        else:
            dropped += 1
    for th in threads:
        th.join()
    if fatal:
        raise RuntimeError(fatal[0])
    return {"latency_s": latencies, "start": begin, "end": time.perf_counter(),
            "offered": offered, "admitted": admitted, "dropped": dropped,
            "completed": len(latencies), "errors": errors, "timeouts": timeouts,
            "first_offer_t": offer_times[0] if offer_times else begin,
            "last_offer_t": offer_times[-1] if offer_times else begin}


def worker_open(ref, tip, vectors, expected, count, start, barrier,
                 rate_qps, timeout_s, max_in_flight, worker_index, num_workers):
    ds = db.Dataset.open(ref, backend=ENDPOINT)
    if ds.current_manifest() != tip:
        raise RuntimeError("snapshot changed")
    barrier.wait(timeout=120)

    before = ds.http_stats()
    cpu = time.process_time()
    result = _open_loop_schedule(
        vectors, expected, count, start, rate_qps, timeout_s, max_in_flight,
        worker_index, num_workers, run_query=lambda index: query(ds, vectors[index]))
    after = ds.http_stats()
    result["cpu_s"] = time.process_time() - cpu
    result["max_rss_kib_linux"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["http_stats_delta"] = http_stats_delta(before, after)
    return result


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
                     help="TOTAL queries/sec offered across all workers "
                          "combined at a given level, required for --mode "
                          "open. Split across workers as a disjoint "
                          "round-robin of one global schedule, so summed "
                          "`offered` matches this value regardless of "
                          "worker count — not workers x this value.")
    ap.add_argument("--max-in-flight", type=int, default=32,
                     help="bound on concurrent in-flight queries per open-loop "
                          "worker; a tick that finds the pool full is counted "
                          "as a real, explicit drop rather than queued "
                          "unboundedly. Ignored for --mode closed.")
    ap.add_argument("--timeout-s", type=float, default=5.0,
                     help="a query slower than this (closed: call latency; "
                          "open: latency from its scheduled offer time) is "
                          "counted as a timeout, not discarded")
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit("new output required")
    if a.mode == "open" and not a.arrival_rate:
        raise SystemExit("--arrival-rate is required for --mode open")
    if a.mode == "open" and a.arrival_rate <= 0:
        raise SystemExit("--arrival-rate must be > 0")
    if a.max_in_flight <= 0:
        raise SystemExit("--max-in-flight must be > 0")

    prior = json.loads((a.pilot / "semantic-queries.json").read_text())
    if prior.get("status") != "PASS":
        raise SystemExit("successful semantic pilot required")

    if a.vector_source == "text":
        prompts = (json.loads(a.text_prompts.read_text()) if a.text_prompts
                   else DEFAULT_TEXT_PROMPTS)
        if not prompts:
            raise SystemExit("prompt list must not be empty")
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

    expected_dim = EMBED_SPEC["hard"]["dim"]
    if vectors.ndim != 2 or vectors.shape[1] != expected_dim:
        raise SystemExit(
            f"vector dim {vectors.shape[1:] if vectors.ndim >= 2 else vectors.shape} "
            f"!= expected {expected_dim}; a mismatch here would surface as an "
            "opaque failure partway through a real run, not at startup")

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
                       "prior one returns; timeouts is a SUBSET of completed "
                       "(a late reply still finished, just slower than "
                       "--timeout-s), not a separate bucket. open-loop: "
                       "--arrival-rate is the TOTAL offered rate across all "
                       "workers at a level combined, split into a disjoint "
                       "round-robin schedule per worker (not per-worker "
                       "rate x worker count) — each level reports "
                       "actual_offered_window_s/actual_offered_rate_qps "
                       "measured from real tick issuance times, comparable "
                       "to the target --arrival-rate. A scheduler ticks "
                       "independent of query completion (max_in_flight="
                       f"{a.max_in_flight}, --max-in-flight). offered counts "
                       "every scheduled tick reached, including ticks while "
                       "an earlier query is still in flight; admitted counts "
                       "ticks where the in-flight pool had a free slot and "
                       "the query actually started; dropped counts ticks "
                       "that found the pool full — a real, explicit drop, "
                       "never an unbounded backlog and never queued, so "
                       "there is no queueing delay to report; completed "
                       "counts admitted queries that returned successfully, "
                       "and includes late ones (timeouts is a SUBSET of "
                       "completed, same as closed-loop). Latency is measured "
                       "from the query's SCHEDULED tick time to completion, "
                       "so it includes scheduling/dispatch/thread-start "
                       "latency but NOT queueing delay (there is no queue); "
                       "a late reply is flagged as a timeout, not preempted, "
                       "because the SDK's iter_vector has no cancellation/"
                       "deadline argument. Neither loop makes a cold-cache "
                       "or relevance claim; http_stats deltas are per-worker "
                       "connector sums (Dataset.open per worker, never "
                       "branch(), so no cross-worker double count); "
                       "http_per_completed_query divides only fields "
                       "HTTP_STATS_KEYS actually counted."}
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
                            a.arrival_rate, a.timeout_s, a.max_in_flight,
                            i, writers) for i in range(writers)]
                results = [j.result() for j in jobs]
        wall = time.perf_counter() - begin
        active = max(r["end"] for r in results) - min(r["start"] for r in results)
        latencies = [v for r in results for v in r["latency_s"]]
        level_http_stats = sum_http_stats([r["http_stats_delta"] for r in results])
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
            "http_stats": level_http_stats,
            "http_per_completed_query": http_per_completed_query(
                level_http_stats, len(latencies))}
        if a.mode == "open":
            level["admitted"] = sum(r["admitted"] for r in results)
            level["dropped"] = sum(r["dropped"] for r in results)
            offered_window_s = (max(r["last_offer_t"] for r in results)
                                 - min(r["first_offer_t"] for r in results))
            level["actual_offered_window_s"] = offered_window_s
            level["actual_offered_rate_qps"] = (
                level["offered"] / offered_window_s if offered_window_s > 0 else None)
        report["levels"].append(level)
        a.out.write_text(json.dumps(report, indent=2))
        print(json.dumps(level), flush=True)
    report["status"] = "PASS"
    a.out.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
