"""Direct checks for the new CLI/metrics surface in read_stress.py.

Plain asserts, no pytest, no network — validates the pure accounting helpers
and the --mode/--arrival-rate CLI contract only. Run with the same
interpreter/venv as read_stress.py itself (needs `dreamdb`, `numpy`):

    python3 test_read_stress.py
"""
import subprocess
import sys
from pathlib import Path

import read_stress as rs

HERE = Path(__file__).parent


def test_http_stats_delta_subtracts_each_key():
    before = {k: 10 for k in rs.HTTP_STATS_KEYS}
    after = {k: 10 + i for i, k in enumerate(rs.HTTP_STATS_KEYS)}
    delta = rs.http_stats_delta(before, after)
    assert delta == {k: i for i, k in enumerate(rs.HTTP_STATS_KEYS)}


def test_http_stats_delta_none_on_non_http_backend():
    assert rs.http_stats_delta(None, {k: 0 for k in rs.HTTP_STATS_KEYS}) is None
    assert rs.http_stats_delta({k: 0 for k in rs.HTTP_STATS_KEYS}, None) is None


def test_sum_http_stats_adds_across_workers():
    a = {k: 1 for k in rs.HTTP_STATS_KEYS}
    b = {k: 2 for k in rs.HTTP_STATS_KEYS}
    total = rs.sum_http_stats([a, b])
    assert total == {k: 3 for k in rs.HTTP_STATS_KEYS}


def test_sum_http_stats_none_when_all_workers_none():
    assert rs.sum_http_stats([None, None]) is None


def test_http_stats_keys_match_the_rust_snapshot_field_names():
    # Guards against silent drift from dreamdb-connector-http/src/stats.rs's
    # HttpStatsSnapshot. If a future SDK adds/renames a counter, this list
    # (and the aggregation above) needs an explicit update, not a silent gap.
    expected = {
        "attempts_started", "attempts_completed", "retries_internal",
        "put_redirect_hops", "status_2xx", "status_3xx", "status_4xx",
        "status_5xx", "status_412", "transport_errors", "body_errors",
        "cancelled", "request_body_bytes", "response_body_bytes",
        "attempt_nanos_total", "requests_get", "requests_head",
        "requests_put", "requests_post", "requests_delete", "requests_other",
    }
    assert set(rs.HTTP_STATS_KEYS) == expected
    assert len(rs.HTTP_STATS_KEYS) == len(expected)


def test_open_mode_requires_arrival_rate():
    result = subprocess.run(
        [sys.executable, str(HERE / "read_stress.py"),
         "--pilot", "/nonexistent", "--out", "/tmp/does-not-matter.json",
         "--mode", "open"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "arrival-rate" in (result.stderr + result.stdout)


def test_closed_mode_does_not_require_arrival_rate_flag():
    # Should get past CLI validation and fail later, on the missing pilot
    # file — not on the --mode/--arrival-rate contract.
    result = subprocess.run(
        [sys.executable, str(HERE / "read_stress.py"),
         "--pilot", "/nonexistent", "--out", "/tmp/does-not-matter-2.json"],
        capture_output=True, text=True)
    assert "arrival-rate" not in (result.stderr + result.stdout)


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_all()
