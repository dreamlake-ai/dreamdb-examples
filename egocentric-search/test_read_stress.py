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


def test_http_per_completed_query_divides_only_declared_rate_keys():
    stats = {k: 100 for k in rs.HTTP_STATS_KEYS}
    rates = rs.http_per_completed_query(stats, 10)
    for k in rs.HTTP_PER_QUERY_RATE_KEYS:
        assert rates[f"{k}_per_completed_query"] == 10.0
    assert rates["retries_internal"] == 100
    assert "requests_put_per_completed_query" not in rates


def test_http_per_completed_query_none_without_stats_or_completions():
    stats = {k: 1 for k in rs.HTTP_STATS_KEYS}
    assert rs.http_per_completed_query(None, 10) is None
    assert rs.http_per_completed_query(stats, 0) is None


def test_default_text_prompts_are_at_least_fifty_and_distinct():
    assert len(rs.DEFAULT_TEXT_PROMPTS) >= 50
    assert len(set(rs.DEFAULT_TEXT_PROMPTS)) == len(rs.DEFAULT_TEXT_PROMPTS)


def test_open_loop_keeps_offering_while_a_query_is_in_flight_then_drops_at_limit():
    # The product claim under test: the schedule is decoupled from query
    # completion (offered keeps advancing while an earlier query hasn't
    # returned) and admission is bounded (a full pool is a real, counted
    # drop, not a block). A slow-but-controllable stand-in for the network
    # call proves this without opening a real Dataset.
    import time

    # rate_qps=200 spaces the 3 ticks 5ms apart (15ms total); a 200ms
    # "query" comfortably outlasts all three ticks' issuance without any
    # cross-thread signaling the test would otherwise need to arrange.
    def slow_query(index):
        time.sleep(0.2)
        return [0]

    result = rs._open_loop_schedule(
        vectors=[None, None, None], expected=[[0], [0], [0]], count=3,
        start=0, rate_qps=200.0, timeout_s=5.0, max_in_flight=1,
        worker_index=0, num_workers=1, run_query=slow_query)

    assert result["offered"] == 3, "every tick must be reached regardless of the in-flight query"
    assert result["admitted"] == 1, "only the first tick found a free slot"
    assert result["dropped"] == 2, "the pool was full for both later ticks — a real, explicit drop"
    assert result["completed"] == 1


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


def test_open_loop_error_samples_are_bounded_and_capture_type_and_message():
    # The product claim: infra query failures retain a bounded, inspectable
    # sample (type/message/index) instead of only incrementing a counter —
    # bounded per worker so a pathological run can't blow up the report.
    def failing_query(index):
        raise ValueError(f"boom {index}")

    result = rs._open_loop_schedule(
        vectors=[None] * 10, expected=[[0]] * 10, count=10,
        start=0, rate_qps=1000.0, timeout_s=5.0, max_in_flight=10,
        worker_index=0, num_workers=1, run_query=failing_query)

    assert result["errors"] == 10
    assert len(result["error_samples"]) == rs.MAX_ERROR_SAMPLES_PER_WORKER
    for s in result["error_samples"]:
        assert s["type"] == "ValueError"
        assert s["message"].startswith("boom")
        assert "query_index" in s


def test_production_mode_requires_ref_tip_and_text_vector_source_together():
    result = subprocess.run(
        [sys.executable, str(HERE / "read_stress.py"),
         "--out", "/tmp/does-not-matter-3.json",
         "--ref", rs.PRODUCTION_REF],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "production mode requires" in (result.stderr + result.stdout)


def test_production_mode_rejects_a_ref_other_than_the_authorized_one():
    result = subprocess.run(
        [sys.executable, str(HERE / "read_stress.py"),
         "--out", "/tmp/does-not-matter-4.json",
         "--ref", "some-other-ref", "--tip", "deadbeef",
         "--vector-source", "text"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "--ref must be" in (result.stderr + result.stdout)


def test_missing_pilot_and_no_production_flags_fails_fast():
    result = subprocess.run(
        [sys.executable, str(HERE / "read_stress.py"),
         "--out", "/tmp/does-not-matter-5.json"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "--pilot is required" in (result.stderr + result.stdout)


def test_queries_per_level_hard_cap_is_enforced():
    result = subprocess.run(
        [sys.executable, str(HERE / "read_stress.py"),
         "--pilot", "/nonexistent", "--out", "/tmp/does-not-matter-6.json",
         "--queries-per-level", "1000"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "queries-per-level" in (result.stderr + result.stdout)


def test_levels_must_be_strictly_increasing_and_within_the_concurrency_cap():
    result = subprocess.run(
        [sys.executable, str(HERE / "read_stress.py"),
         "--pilot", "/nonexistent", "--out", "/tmp/does-not-matter-7.json",
         "--levels", "8,4"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "--levels" in (result.stderr + result.stdout)


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
