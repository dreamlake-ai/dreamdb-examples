"""Snapshot episode windows: application semantics, public DreamDB reads only.

The catalogue is O(transitions in the explicit prefix), not O(batch size).
Ordinal page widths bound materialized rows only for this prototype's encoding;
they do not bound native Track metadata, connector caches or total process RSS.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_left
from dataclasses import dataclass

import dreamdb
import numpy as np
from store import FORMAT, I64_MAX, event_fields


@dataclass(frozen=True)
class StepWindow:
    env_id: int
    episode_id: int
    start: int
    stop: int


@dataclass(frozen=True)
class TimeWindow:
    env_id: int
    episode_id: int
    start: float
    stop: float


@dataclass(frozen=True)
class ReadStats:
    calls: int
    returned_rows: int


@dataclass(frozen=True)
class WindowResult:
    request: StepWindow | TimeWindow
    manifest: str
    rows: tuple[dict, ...]


@dataclass(frozen=True)
class WindowBatch:
    windows: tuple[WindowResult, ...]
    stats: ReadStats
    unique_selected_rows: int
    output_rows: int


@dataclass(frozen=True)
class _Transition:
    anchor: int
    sim_time: float
    done: bool


def _integer(name, value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


class EpisodeReader:
    """Reuse an identity catalogue for repeated windows on one pinned prefix.

    The backend/Manifest come from the capture receipt, not a moving Ref. Payload
    fields are always explicit. No model load, simulation, Torch or GPU needed.
    """

    def __init__(
        self,
        backend: str,
        manifest: str,
        end_anchor: int,
        *,
        page_rows: int = 256,
        max_scan_rows: int = 100_000,
        max_requests: int = 64,
        max_output_rows: int = 8192,
    ):
        for name, value in (
            ("end_anchor", end_anchor),
            ("page_rows", page_rows),
            ("max_scan_rows", max_scan_rows),
            ("max_requests", max_requests),
            ("max_output_rows", max_output_rows),
        ):
            _integer(name, value, 1)
        if end_anchor > min(max_scan_rows, I64_MAX):
            raise ValueError("prefix exceeds scan budget or signed SDK range")
        if not manifest:
            raise ValueError("explicit Manifest required")
        self._manifest = manifest
        self.end_anchor = end_anchor
        self.page_rows = page_rows
        self.max_requests = max_requests
        self.max_output_rows = max_output_rows
        self._dataset = dreamdb.Dataset.open_by_manifest(manifest, backend=backend)
        header = self._page(["kind", "metadata"], 0, 1)
        if len(header) != 1 or header[0]["kind"] != "run_start":
            raise ValueError("missing run_start at ordinal zero")
        metadata = json.loads(header[0]["metadata"])
        if (
            metadata.get("format") != FORMAT
            or metadata.get("anchor_encoding") != "logical-record-ordinal-v1"
        ):
            raise ValueError("unsupported application format / anchor encoding")
        self._fields = set(event_fields(metadata))
        self._episodes: dict[tuple[int, int], list[_Transition]] = {}
        identity = [
            "kind",
            "env_id",
            "episode_id",
            "step_id",
            "sim_time",
            "terminated",
            "truncated",
        ]
        calls, returned, expected = 1, 1, 1
        ended = False
        for start in range(1, end_anchor, page_rows):
            rows = self._page(identity, start, min(start + page_rows, end_anchor))
            calls += 1
            returned += len(rows)
            for row in rows:
                if row["_anchor"] != expected:
                    raise ValueError("prefix is not a dense logical-ordinal recording")
                expected += 1
                if ended:
                    raise ValueError("event after run_end")
                if row["kind"] == "run_end":
                    ended = True
                    continue
                key = (_integer("env_id", row["env_id"]), _integer("episode_id", row["episode_id"]))
                step = _integer("step_id", row["step_id"])
                if row["kind"] == "reset":
                    if key in self._episodes or step != 0:
                        raise ValueError("duplicate episode reset or nonzero reset step")
                    self._episodes[key] = []
                    continue
                if row["kind"] != "transition" or key not in self._episodes:
                    raise ValueError("transition without reset or unsupported event")
                transitions = self._episodes[key]
                if step != len(transitions) or (transitions and transitions[-1].done):
                    raise ValueError("noncontiguous steps or transition after terminal")
                timestamp = row["sim_time"]
                if (
                    not isinstance(timestamp, (int, float))
                    or not math.isfinite(timestamp)
                    or timestamp < 0
                    or (transitions and timestamp < transitions[-1].sim_time)
                ):
                    raise ValueError("invalid or decreasing episode simulation time")
                if any(type(row[name]) is not bool for name in ("terminated", "truncated")):
                    raise ValueError("missing explicit terminal flags")
                transitions.append(
                    _Transition(row["_anchor"], timestamp, row["terminated"] or row["truncated"])
                )
        if expected != end_anchor:
            raise ValueError("prefix extends beyond recorded ordinals")
        self.index_stats = ReadStats(calls, returned)

    @property
    def manifest(self):
        return self._manifest

    def _page(self, fields, start, stop):
        rows = []
        for batch in self._dataset.iter_all_batches(
            fields=fields,
            start_ns=start,
            end_ns=stop,
            batch_size=self.page_rows,
        ):
            for i, anchor in enumerate(batch["_time_anchors"]):
                if not start <= anchor < stop:
                    raise ValueError("SDK returned an anchor outside requested page")
                rows.append(
                    {
                        "_anchor": anchor,
                        **{field: batch[field][i] if field in batch else None for field in fields},
                    }
                )
        return rows

    def read_windows(self, requests, *, fields, allow_incomplete=False) -> WindowBatch:
        """Return projected transitions, with independent arrays per result.

        Each touched ordinal page is hydrated once within this call. `kind` is
        an internal anchor carrier, so optional-only projections still include
        transitions where every requested payload is absent.
        """
        if not isinstance(requests, (list, tuple)) or len(requests) > self.max_requests:
            raise ValueError("bounded list/tuple of requests required")
        if (
            not isinstance(fields, (list, tuple))
            or not fields
            or any(not isinstance(field, str) for field in fields)
            or len(set(fields)) != len(fields)
            or set(fields) - self._fields
        ):
            raise ValueError("explicit distinct recorded event fields required")
        if type(allow_incomplete) is not bool:
            raise ValueError("allow_incomplete must be explicit bool")
        selected, count = [], 0
        for request in requests:
            if type(request) not in (StepWindow, TimeWindow):
                raise ValueError("StepWindow or TimeWindow required")
            key = (_integer("env_id", request.env_id), _integer("episode_id", request.episode_id))
            if key not in self._episodes:
                raise ValueError(f"unknown episode {key}")
            transitions = self._episodes[key]
            if not allow_incomplete and (not transitions or not transitions[-1].done):
                raise ValueError(f"episode {key} is incomplete in this prefix")
            if isinstance(request, StepWindow):
                _integer("start", request.start)
                _integer("stop", request.stop, 1)
                if request.stop <= request.start or request.stop > len(transitions):
                    raise ValueError("step window is empty or contains missing steps")
                start, stop = request.start, request.stop
            else:
                if any(
                    type(t) not in (int, float) or not math.isfinite(t)
                    for t in (request.start, request.stop)
                ):
                    raise ValueError("finite simulation-time bounds required")
                if request.start < 0 or request.stop <= request.start:
                    raise ValueError("invalid simulation-time interval")
                start = bisect_left(transitions, request.start, key=lambda t: t.sim_time)
                stop = bisect_left(transitions, request.stop, key=lambda t: t.sim_time)
            count += stop - start
            if count > self.max_output_rows:
                raise ValueError("batch exceeds output row budget")
            selected.append([t.anchor for t in transitions[start:stop]])
        wanted = {anchor for anchors in selected for anchor in anchors}
        pages = sorted({anchor // self.page_rows for anchor in wanted})
        projection = list(dict.fromkeys(["kind", *fields]))
        stored, returned = {}, 0
        for page in pages:
            start = page * self.page_rows
            rows = self._page(projection, start, min(start + self.page_rows, self.end_anchor))
            returned += len(rows)
            for row in rows:
                anchor = row["_anchor"]
                if anchor in wanted:
                    if anchor in stored or row["kind"] != "transition":
                        raise ValueError("duplicate/mismatched transition anchor")
                    stored[anchor] = row
        if stored.keys() != wanted:
            raise ValueError("payload read omitted requested anchors")
        results = []
        for request, anchors in zip(requests, selected, strict=True):
            rows = []
            for anchor in anchors:
                row = {"_anchor": anchor}
                for field in fields:
                    value = stored[anchor][field]
                    row[field] = value.copy() if isinstance(value, np.ndarray) else value
                rows.append(row)
            results.append(WindowResult(request, self.manifest, tuple(rows)))
        return WindowBatch(tuple(results), ReadStats(len(pages), returned), len(wanted), count)
