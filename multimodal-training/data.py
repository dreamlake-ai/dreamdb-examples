"""Application-owned image/sensor samples using only public DreamDB APIs."""

from __future__ import annotations

import io
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import dreamdb
import numpy as np
from PIL import Image

FORMAT = "image-sensor-windows-v1"
SIZE = 64
WIDTH = 4
IDENTITY = ["env_id", "episode_id", "step_id", "sim_time", "terminated", "truncated"]
PAYLOAD = ["image", "sensor", "action"]


def png(pixels):
    if pixels.dtype != np.uint8 or pixels.shape != (SIZE, SIZE, 3):
        raise ValueError("64x64 RGB uint8 required")
    out = io.BytesIO()
    Image.fromarray(pixels).save(out, format="PNG")
    return out.getvalue()


class Writer:
    def __init__(self, root: Path, metadata: dict):
        root.mkdir(exist_ok=False)
        self.backend = root.resolve().as_uri()
        schema = dreamdb.Schema()
        schema.add_scalar_string("metadata", required=False)
        for name in IDENTITY[:3]:
            schema.add_scalar_int(name, required=False)
        schema.add_scalar_float("sim_time", required=False)
        for name in IDENTITY[-2:]:
            schema.add_scalar_bool(name, required=False)
        schema.add_image("image", mime="png", required=False)
        schema.add_array("sensor", "f32", [metadata["sensor_dim"]], required=False)
        schema.add_array("action", "f32", [1], required=False)
        self.dataset = dreamdb.Dataset.create("capture", schema, backend=self.backend)
        self.next_anchor = 0
        self.append([{"metadata": json.dumps({**metadata, "format": FORMAT})}])

    def append(self, rows):
        if not rows:
            return
        values = [dict(row, _anchor=self.next_anchor + i) for i, row in enumerate(rows)]
        if self.dataset.append_many(values, commit=True) != len(values):
            raise RuntimeError("partial append; do not retry ambiguous publication")
        self.next_anchor += len(values)

    def receipt(self):
        return {"manifest": self.dataset.current_manifest(), "end_anchor": self.next_anchor}


@dataclass
class Stats:
    sdk_calls: int = 0
    returned_rows: int = 0
    payload_bytes: int = 0
    decoded_frames: int = 0
    read_seconds: float = 0.0
    decode_seconds: float = 0.0
    assembly_seconds: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_evictions: int = 0
    sdk_seconds: float = 0.0
    page_hits: int = 0
    page_misses: int = 0
    page_evictions: int = 0
    selected_records: int = 0
    selected_fetched_bytes: int = 0


class Reader:
    def __init__(self, backend, receipt, *, page_rows=32, max_scan_rows=4096, cache_bytes=0,
                 page_cache_bytes=0):
        if type(cache_bytes) is not int or cache_bytes < 0:
            raise ValueError("nonnegative cache byte budget required")
        self.cache_budget = cache_bytes
        self.cache = OrderedDict()
        self.cache_bytes = self.cache_peak = 0
        if type(page_cache_bytes) is not int or page_cache_bytes < 0:
            raise ValueError("nonnegative page-cache budget required")
        self.page_budget = page_cache_bytes
        self.page_cache = OrderedDict()
        self.page_bytes = self.page_peak = 0
        if type(page_rows) is not int or not 1 <= page_rows <= 256:
            raise ValueError("page_rows must be in [1,256]")
        self.end = receipt["end_anchor"]
        if type(self.end) is not int or not 1 < self.end <= max_scan_rows:
            raise ValueError("explicit bounded nonempty capture required")
        self.manifest = receipt["manifest"]
        self.ds = dreamdb.Dataset.open_by_manifest(self.manifest, backend=backend)
        self.page_rows = page_rows
        started = time.perf_counter()
        stats = Stats()
        header = self._read(["metadata"], 0, 1, stats)
        self.metadata = json.loads(header[0]["metadata"])
        if self.metadata["format"] != FORMAT or self.metadata["image_shape"] != [SIZE, SIZE, 3]:
            raise ValueError("unsupported application layout")
        self.episodes = {}
        expected = 1
        for start in range(1, self.end, page_rows):
            for row in self._read(IDENTITY, start, min(start + page_rows, self.end), stats):
                if row["_anchor"] != expected:
                    raise ValueError("missing or unordered capture ordinal")
                expected += 1
                key = (row["env_id"], row["episode_id"])
                episode = self.episodes.setdefault(key, [])
                if row["step_id"] != len(episode):
                    raise ValueError("missing episode step")
                if episode and (episode[-1]["terminated"] or episode[-1]["truncated"]):
                    raise ValueError("window would cross reset")
                if not np.isfinite(row["sim_time"]) or (
                    episode and row["sim_time"] <= episode[-1]["sim_time"]
                ):
                    raise ValueError("invalid pre-action clock")
                if any(type(row[f]) is not bool for f in IDENTITY[-2:]):
                    raise ValueError("explicit outcome flags required")
                episode.append(row)
        if expected != self.end:
            raise ValueError("receipt extends beyond capture")
        self.samples = []
        for key, rows in sorted(self.episodes.items()):
            if not (rows[-1]["terminated"] or rows[-1]["truncated"]):
                raise ValueError("incomplete episode; no silent inclusion or dropping")
            self.samples.extend((key, stop - WIDTH) for stop in range(WIDTH, len(rows) + 1))
        self.index_seconds = time.perf_counter() - started
        self.index_stats = stats

    def _read(self, fields, start, stop, stats):
        key = (tuple(fields), start, stop)
        cacheable = self.page_budget and fields == PAYLOAD
        if cacheable and key in self.page_cache:
            stats.page_hits += 1
            self.page_cache.move_to_end(key)
            return self.page_cache[key][0]
        if cacheable:
            stats.page_misses += 1
        stats.sdk_calls += 1
        rows = []
        started = time.perf_counter()
        batches = self.ds.iter_all_batches(
            fields=fields, start_ns=start, end_ns=stop, batch_size=self.page_rows
        )
        stats.sdk_seconds += time.perf_counter() - started
        for batch in batches:
            for i, anchor in enumerate(batch["_time_anchors"]):
                if not start <= anchor < stop:
                    raise ValueError("out-of-range public read")
                row = {"_anchor": anchor}
                for name in fields:
                    value = batch[name][i] if name in batch else None
                    row[name] = value
                    if isinstance(value, (bytes, bytearray)):
                        stats.payload_bytes += len(value)
                    elif isinstance(value, np.ndarray):
                        stats.payload_bytes += value.nbytes
                rows.append(row)
        stats.returned_rows += len(rows)
        if cacheable:
            size = sum(8 + sum(len(v) if isinstance(v, (bytes, bytearray)) else
                              v.nbytes if isinstance(v, np.ndarray) else 0
                              for name, v in row.items() if name != "_anchor")
                       for row in rows)
            if size <= self.page_budget:
                while self.page_bytes + size > self.page_budget:
                    _, (_, evicted_size) = self.page_cache.popitem(last=False)
                    self.page_bytes -= evicted_size
                    stats.page_evictions += 1
                owned = [{name: v.copy() if isinstance(v, np.ndarray) else
                          bytes(v) if isinstance(v, bytearray) else v
                          for name, v in row.items()} for row in rows]
                self.page_cache[key] = (owned, size)
                self.page_bytes += size
                self.page_peak = max(self.page_peak, self.page_bytes)
                assert self.page_bytes <= self.page_budget
        return rows

    def batch(self, requests):
        if not isinstance(requests, (list, tuple)) or not 1 <= len(requests) <= 16:
            raise ValueError("batch requires 1..16 samples")
        selections = []
        for key, start in requests:
            if key not in self.episodes or type(start) is not int or start < 0:
                raise ValueError("invalid episode window")
            rows = self.episodes[key][start : start + WIDTH]
            if len(rows) != WIDTH:
                raise ValueError("missing window steps")
            selections.append([row["_anchor"] for row in rows])
        wanted = {anchor for selection in selections for anchor in selection}
        stats = Stats()
        stats.selected_records = len(wanted)
        stored = {}
        for anchor in sorted(wanted):
            if anchor in self.cache:
                stored[anchor] = self.cache[anchor]
                self.cache.move_to_end(anchor)
                stats.cache_hits += 1
        missing = wanted - stored.keys()
        stats.cache_misses = len(missing)
        pages = sorted({anchor // self.page_rows for anchor in missing})
        for page in pages:
            started = time.perf_counter()
            rows = self._read(
                PAYLOAD, page * self.page_rows, min((page + 1) * self.page_rows, self.end), stats
            )
            stats.read_seconds += time.perf_counter() - started
            for row in rows:
                anchor = row["_anchor"]
                if anchor not in missing:
                    continue
                started = time.perf_counter()
                if anchor in stored or any(row[f] is None for f in PAYLOAD):
                    raise ValueError("duplicate or missing selected payload")
                with Image.open(io.BytesIO(row["image"])) as image:
                    if image.mode != "RGB" or image.size != (SIZE, SIZE):
                        raise ValueError("unexpected image layout")
                    pixels = np.asarray(image).copy()
                sensor, action = row["sensor"], row["action"]
                for value, shape in ((sensor, (self.metadata["sensor_dim"],)), (action, (1,))):
                    if (
                        value.dtype != np.dtype("<f4")
                        or value.shape != shape
                        or not np.isfinite(value).all()
                    ):
                        raise ValueError("invalid exact training array")
                stats.decoded_frames += 1
                # Encoded bytes of selected records consumed from a read page,
                # including page-cache hits, excluding decoded-record cache hits.
                stats.selected_fetched_bytes += len(row["image"]) + sensor.nbytes + action.nbytes
                stored[anchor] = (pixels, sensor, action)
                stats.decode_seconds += time.perf_counter() - started
                size = sum(v.nbytes for v in stored[anchor])
                if self.cache_budget and size <= self.cache_budget:
                    while self.cache_bytes + size > self.cache_budget:
                        _, evicted = self.cache.popitem(last=False)
                        self.cache_bytes -= sum(v.nbytes for v in evicted)
                        stats.cache_evictions += 1
                    # Own array storage, not a view retaining a larger SDK buffer.
                    self.cache[anchor] = tuple(v.copy() for v in stored[anchor])
                    self.cache_bytes += size
                    self.cache_peak = max(self.cache_peak, self.cache_bytes)
                    assert self.cache_bytes <= self.cache_budget
        if stored.keys() != wanted:
            raise ValueError("selected records missing")
        started = time.perf_counter()
        result = {
            "anchors": np.asarray(selections, dtype=np.int64),
            "images": np.stack([np.stack([stored[a][0] for a in s]) for s in selections]),
            "sensors": np.stack([np.stack([stored[a][1] for a in s]) for s in selections]),
            "targets": np.stack([stored[s[-1]][2] for s in selections]),
        }
        stats.assembly_seconds += time.perf_counter() - started
        return result, stats
