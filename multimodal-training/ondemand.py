"""Bounded raw-data producer versus serial loading; no ready artifact."""

import argparse
import json
import multiprocessing as mp
import resource
import time
import traceback
from pathlib import Path

import numpy as np

from data import Reader


def batches(root, cache_bytes=0, page_cache_bytes=0, read_policy="pages"):
    receipt = json.loads((root / "receipt.json").read_text())
    reader = Reader((root / "backend").as_uri(), receipt, cache_bytes=cache_bytes,
                    page_cache_bytes=page_cache_bytes, read_policy=read_policy)
    samples = [r for r in reader.samples if r[0][0] < 6]
    rng = np.random.default_rng(71)
    for _ in range(2):
        order = rng.permutation(len(samples))
        for offset in range(0, len(order), 16):
            requests = [samples[i] for i in order[offset : offset + 16]]
            started = time.perf_counter()
            raw, stats = reader.batch(requests)
            converting = time.perf_counter()
            images = np.ascontiguousarray(
                raw["images"].transpose(0, 1, 4, 2, 3).reshape(-1, 12, 64, 64),
                dtype=np.float32,
            )
            images *= np.float32(1 / 255)
            raw["images"] = images
            measured = dict(vars(stats), transform_seconds=time.perf_counter() - converting,
                            cache_peak_bytes=reader.cache_peak, page_peak_bytes=reader.page_peak)
            yield raw, time.perf_counter() - started, measured


def produce(root, queue, cache_bytes, page_cache_bytes, read_policy):
    try:
        for batch in batches(root, cache_bytes, page_cache_bytes, read_policy):
            queue.put(("batch", batch))
        queue.put(("done", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
    except BaseException:
        queue.put(("error", traceback.format_exc()))


def train(root, mode):
    import torch
    from network import make_model

    torch.set_num_threads(4)
    torch.manual_seed(71)
    model = make_model(4).cuda()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    # Load independent capture witnesses before timing; not a producer cache.
    with np.load(root / "witness.npz") as f:
        witness = {k: f[k] for k in ("images", "sensors", "actions", "identities")}
    lookup = {tuple(row): i + 1 for i, row in enumerate(witness["identities"])}
    groups = {}
    for env, episode, step in lookup:
        if env < 6:
            groups.setdefault((env, episode), []).append(step)
    windows = []
    for (env, episode), steps in sorted(groups.items()):
        assert sorted(steps) == list(range(len(steps)))
        windows.extend([lookup[(env, episode, step)] for step in range(start, start + 4)]
                       for start in range(len(steps) - 3))
    rng = np.random.default_rng(71)
    expected_batches = []
    for _ in range(2):
        order = rng.permutation(len(windows))
        expected_batches.extend(np.asarray([windows[i] for i in order[n:n + 16]])
                                for n in range(0, len(order), 16))
    torch.cuda.synchronize()
    worker = queue = None
    report = dict(mode=mode, wait=0.0, transfer=0.0, compute=0.0, check=0.0,
                  producer_work=0.0, batches=0, sdk_calls=0, decoded_frames=0,
                  read_seconds=0.0, decode_seconds=0.0, assembly_seconds=0.0,
                  transform_seconds=0.0, cache_hits=0, cache_misses=0,
                  cache_evictions=0, cache_peak_bytes=0,
                  sdk_seconds=0.0, page_hits=0, page_misses=0, page_evictions=0,
                  page_peak_bytes=0, batch_waits=[],
                  returned_rows=0, payload_bytes=0, selected_records=0, selected_fetched_bytes=0,
                  worker_rss_kib=None, first_batch=None, max_batch_bytes=0)
    started = time.perf_counter()
    if mode in ("prefetch", "cached", "pages", "exact"):
        ctx = mp.get_context("spawn")
        queue = ctx.Queue(maxsize=2)
        worker = ctx.Process(target=produce, args=(root, queue,
                            1048576 if mode == "cached" else 0,
                            1048576 if mode == "pages" else 0,
                            "exact" if mode == "exact" else "pages"))
        worker.start()
    else:
        iterator = iter(batches(root))
    try:
        while True:
            t = time.perf_counter()
            if queue is not None:
                kind, payload = queue.get(timeout=120)
                if kind == "error":
                    raise RuntimeError(payload)
                if kind == "done":
                    report["worker_rss_kib"] = payload
                    break
            else:
                try:
                    payload = next(iterator)
                except StopIteration:
                    break
            waited = time.perf_counter() - t
            report["wait"] += waited
            report["batch_waits"].append(waited)
            if report["first_batch"] is None:
                report["first_batch"] = time.perf_counter() - started
            batch, seconds, stats = payload
            report["producer_work"] += seconds
            for key in ("sdk_calls", "decoded_frames", "read_seconds", "decode_seconds",
                        "assembly_seconds", "transform_seconds", "cache_hits", "cache_misses",
                        "cache_evictions", "sdk_seconds", "page_hits", "page_misses", "page_evictions",
                        "returned_rows", "payload_bytes", "selected_records", "selected_fetched_bytes"):
                report[key] += stats[key]
            report["cache_peak_bytes"] = max(report["cache_peak_bytes"], stats["cache_peak_bytes"])
            report["page_peak_bytes"] = max(report["page_peak_bytes"], stats["page_peak_bytes"])
            report["max_batch_bytes"] = max(report["max_batch_bytes"],
                                           sum(v.nbytes for v in batch.values()))
            t = time.perf_counter()
            np.testing.assert_array_equal(batch["anchors"], expected_batches[report["batches"]])
            indices = batch["anchors"] - 1
            expected = np.ascontiguousarray(
                witness["images"][indices].transpose(0, 1, 4, 2, 3)
                .reshape(-1, 12, 64, 64), dtype=np.float32)
            expected *= np.float32(1 / 255)
            np.testing.assert_array_equal(batch["images"], expected)
            np.testing.assert_array_equal(batch["sensors"], witness["sensors"][indices])
            np.testing.assert_array_equal(batch["targets"], witness["actions"][indices[:, -1]])
            report["check"] += time.perf_counter() - t
            t = time.perf_counter()
            images, sensors, targets = [torch.from_numpy(batch[k]).cuda()
                                        for k in ("images", "sensors", "targets")]
            torch.cuda.synchronize()
            report["transfer"] += time.perf_counter() - t
            t = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.mse_loss(model(images, sensors), targets)
            loss.backward()
            optimizer.step()
            torch.cuda.synchronize()
            report["compute"] += time.perf_counter() - t
            if not torch.isfinite(loss):
                raise ValueError("nonfinite loss")
            report["batches"] += 1
        report["loop_seconds"] = time.perf_counter() - started
        assert report["batches"] == len(expected_batches)
        report["parent_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["result"] = "PASS"
        print("ONDEMAND " + json.dumps(report), flush=True)
    finally:
        if worker is not None:
            worker.join(timeout=5)
            if worker.is_alive():
                worker.terminate()
                worker.join()
            queue.close()
            queue.join_thread()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["serial", "prefetch", "cached", "pages", "exact"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    train(args.directory.resolve(), args.mode)
