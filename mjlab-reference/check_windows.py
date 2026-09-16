"""CPU public-SDK check and bounded overlap measurement; no training claim.

Uses the existing real minimal model/storage fixture, not a new simulator or
validation framework. All generated storage/model files are removed on exit.
"""

from __future__ import annotations

import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import dreamdb
import mujoco
import numpy as np
from check_storage import MODEL, events
from store import LocalRunWriter, read_episode
from windows import EpisodeReader, StepWindow, TimeWindow

FIELDS = [
    "env_id",
    "episode_id",
    "step_id",
    "obs_t",
    "action",
    "reward",
    "obs_after",
    "next_observation_valid",
    "terminated",
    "truncated",
    "sim_time",
]


@contextmanager
def count_public_reads():
    """Count real calls/returned rows, not GETs or native metadata allocations."""
    window = dreamdb.Dataset.iter_all_batches
    scalar = dreamdb.Dataset.query_scalar
    counts = {"window_calls": 0, "scalar_calls": 0, "returned_rows": 0, "fields": []}

    def measured_window(self, *args, **kwargs):
        batches = window(self, *args, **kwargs)
        counts["window_calls"] += 1
        counts["returned_rows"] += sum(len(b["_time_anchors"]) for b in batches)
        counts["fields"].append(kwargs.get("fields"))
        return batches

    def measured_scalar(self, *args, **kwargs):
        counts["scalar_calls"] += 1
        return scalar(self, *args, **kwargs)

    dreamdb.Dataset.iter_all_batches = measured_window
    dreamdb.Dataset.query_scalar = measured_scalar
    try:
        yield counts
    finally:
        dreamdb.Dataset.iter_all_batches = window
        dreamdb.Dataset.query_scalar = scalar


def same_rows(got, want, fields):
    assert len(got) == len(want)
    for actual, expected in zip(got, want, strict=True):
        assert actual["_anchor"] == expected["_anchor"]
        assert set(actual) == {"_anchor", *fields}
        for field in fields:
            value, source = actual[field], expected.get(field)
            if isinstance(source, np.ndarray):
                assert value.dtype == source.dtype and value.shape == source.shape
                assert value.tobytes() == source.tobytes()
            else:
                assert value == source, (field, value, source)


def selected(rows, request):
    return [
        row
        for row in rows
        if row["kind"] == "transition"
        and (row["env_id"], row["episode_id"]) == (request.env_id, request.episode_id)
        and request.start
        <= row["step_id" if isinstance(request, StepWindow) else "sim_time"]
        < request.stop
    ]


def check(root):
    model = mujoco.MjModel.from_xml_string(MODEL)
    path = root / "fixture.mjb"
    mujoco.mj_saveModel(model, str(path))
    metadata = {
        "run_id": "window-fixture",
        "dimensions": {
            "qpos": 2,
            "qvel": 2,
            "obs_t": 5,
            "obs_after": 5,
            "action": 1,
        },
    }
    writer = LocalRunWriter(root / "backend", metadata, path.read_bytes())
    # Interleave eight independent copies of the existing episode fixture.
    source = []
    fixture = events()
    for original in fixture:
        for group in range(8):
            source.append({**original, "env_id": original["env_id"] + 2 * group})
    writer.append(source[:32])
    old_tip = writer.append(source[32:])
    expected = [{"_anchor": i + 1, **row} for i, row in enumerate(source)]
    backend = writer.backend
    # New reader opens persisted data independently, not the writer's Dataset.
    with count_public_reads() as cold:
        tick = time.perf_counter()
        reader = EpisodeReader(backend, old_tip, len(source) + 1, page_rows=32, max_output_rows=16)
        index_seconds = time.perf_counter() - tick
    assert all(
        set(f)
        <= {
            "kind",
            "metadata",
            "env_id",
            "episode_id",
            "step_id",
            "sim_time",
            "terminated",
            "truncated",
        }
        for f in cold["fields"]
    )
    requests = [
        StepWindow(0, 0, 0, 2),
        StepWindow(1, 0, 0, 2),
        StepWindow(0, 0, 1, 2),
        StepWindow(0, 0, 0, 2),
        TimeWindow(0, 0, 0.05, 0.1),
        StepWindow(0, 1, 0, 1),
    ]
    with count_public_reads() as calls:
        batch = reader.read_windows(requests, fields=FIELDS)
    for request, result in zip(requests, batch.windows, strict=True):
        assert result.request == request and result.manifest == old_tip
        same_rows(result.rows, selected(expected, request), FIELDS)
    touched = {r["_anchor"] // 32 for request in requests for r in selected(expected, request)}
    assert calls["window_calls"] == len(touched) == batch.stats.calls
    assert calls["scalar_calls"] == 0
    assert all(set(f) == {"kind", *FIELDS} for f in calls["fields"])
    empty_time = reader.read_windows([TimeWindow(0, 0, 1.0, 2.0)], fields=FIELDS)
    assert empty_time.windows[0].rows == () and empty_time.stats.calls == 0
    assert reader.read_windows([], fields=FIELDS).windows == ()
    try:
        reader.read_windows([StepWindow(0, 0, 0, 2)] * 9, fields=FIELDS)
    except ValueError as exc:
        assert "output row budget" in str(exc)
    else:
        raise AssertionError("oversized output batch accepted")
    # Optional-only projection must still return a terminal row with None.
    optional = reader.read_windows([StepWindow(0, 0, 1, 2)], fields=["obs_after"])
    assert optional.windows[0].rows[0]["obs_after"] is None
    # Overlaps do not alias mutable arrays across caller-owned results.
    saved = batch.windows[3].rows[0]["obs_t"].copy()
    batch.windows[0].rows[0]["obs_t"][0] += 99
    np.testing.assert_array_equal(batch.windows[3].rows[0]["obs_t"], saved)

    for request, options, message in (
        (StepWindow(1, 1, 0, 1), {}, "incomplete"),
        (StepWindow(0, 0, 0, 3), {}, "missing steps"),
    ):
        try:
            reader.read_windows([request], fields=FIELDS, **options)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError("invalid window silently accepted")
    partial = StepWindow(1, 1, 0, 1)
    same_rows(
        reader.read_windows([partial], fields=FIELDS, allow_incomplete=True).windows[0].rows,
        selected(expected, partial),
        FIELDS,
    )

    # Complete one old incomplete episode in a later publication.
    later = {
        **fixture[-1],
        "step_id": 1,
        "sim_step": 4,
        "sim_time": 0.1,
        "truncated": True,
        "next_observation_valid": False,
    }
    later.pop("obs_after")
    writer.append([later])
    new_tip = writer.finish()
    assert new_tip != old_tip
    after = reader.read_windows(requests, fields=FIELDS)
    for request, result in zip(requests, after.windows, strict=True):
        same_rows(result.rows, selected(expected, request), FIELDS)
    latest = EpisodeReader(backend, new_tip, len(source) + 3, page_rows=32)
    completed = latest.read_windows([StepWindow(1, 1, 0, 2)], fields=FIELDS)
    assert len(completed.windows[0].rows) == 2 and completed.windows[0].rows[-1]["truncated"]

    # Separate one-time index work from repeated payload reads. Identical
    # fields/requests, same 256-ordinal page size as the existing reader.
    tick = time.perf_counter()
    warm = EpisodeReader(backend, old_tip, len(source) + 1, page_rows=256)
    benchmark_index_seconds = time.perf_counter() - tick
    workload = [StepWindow(env, 0, 0, 2) for env in range(16)] * 2
    baseline_ds = dreamdb.Dataset.open_by_manifest(old_tip, backend=backend)
    timings, facts = {}, {}
    for name in ("existing", "batched"):
        with count_public_reads() as observed:
            tick = time.perf_counter()
            if name == "existing":
                outputs = []
                for request in workload:
                    rows = read_episode(
                        baseline_ds, request.env_id, request.episode_id, fields=["kind", *FIELDS]
                    )
                    picked = selected(rows, request)
                    outputs.append(
                        [{"_anchor": r["_anchor"], **{f: r.get(f) for f in FIELDS}} for r in picked]
                    )
            else:
                outputs = [r.rows for r in warm.read_windows(workload, fields=FIELDS).windows]
            timings[name] = time.perf_counter() - tick
        for request, output in zip(workload, outputs, strict=True):
            same_rows(output, selected(expected, request), FIELDS)
        facts[name] = {k: v for k, v in observed.items() if k != "fields"}
    print(
        "WINDOW_ACCEPTANCE "
        + json.dumps(
            {
                "result": "PASS",
                "snapshot_pinned": True,
                "fixture_events": len(source),
                "index_seconds_page32": index_seconds,
                "index_calls_page32": cold["window_calls"],
                "overlap_payload_calls": calls["window_calls"],
                "requests": len(workload),
                "output_rows": sum(len(x) for x in outputs),
                "benchmark_index_seconds_page256": benchmark_index_seconds,
                "payload_seconds": timings,
                "sdk_boundary_counts": facts,
                "boundary": "local file backend; SDK calls/rows, not network GETs; no scale claim",
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="ddb-window-check-") as temp:
        check(Path(temp))
    print("WINDOW_CLEANED: temporary model and datasets removed", flush=True)
