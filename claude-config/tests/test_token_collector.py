"""Acceptance tests for issue #231 — cache-aware token cost collector (§1.1-§1.5)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import token_collector as C  # noqa: E402
import otel_sink as O  # noqa: E402

SONNET = "claude-sonnet-4"


# 1. cost computation at known prices --------------------------------------------------------
def test_cost_computation_known_prices():
    rec = {"input": 1000, "output": 500, "cache_read": 200, "cache_creation": 100, "model": SONNET}
    p = O.PRICES[SONNET]
    expected = (1000 * p["input"] + 500 * p["output"] + 200 * p["cache_read"] + 100 * p["cache_creation"])
    assert C.session_cost(rec) == pytest.approx(expected, rel=1e-9)


# 2. cache-read ≈ 10% of fresh input ---------------------------------------------------------
def test_cache_read_ten_percent_of_input():
    n = 50_000
    fresh = C.session_cost({"input": n, "model": SONNET})
    cached = C.session_cost({"cache_read": n, "model": SONNET})
    assert cached == pytest.approx(0.10 * fresh, rel=1e-6)


# 3. output is dearest -----------------------------------------------------------------------
def test_output_dearest():
    n = 10_000
    assert C.session_cost({"output": n, "model": SONNET}) > C.session_cost({"input": n, "model": SONNET})


# 4. multi-session task sum ------------------------------------------------------------------
def test_multi_session_task_sum():
    sink = [
        {"session_id": "s1", "input": 1000, "model": SONNET},
        {"session_id": "s2", "input": 2000, "model": SONNET},
    ]
    meta = {"s1": {"issue": 42}, "s2": {"issue": 42}}  # same logical task
    agg = C.aggregate(C.collect_sessions(sink, meta))
    assert len(agg["tasks"]) == 1
    task = agg["tasks"][0]
    assert task["task_link"] == "issue:42"
    assert set(task["sessions"]) == {"s1", "s2"}
    assert task["cost_usd"] == pytest.approx(
        C.session_cost(sink[0]) + C.session_cost(sink[1]), rel=1e-9)


# 5. unattributed cost -----------------------------------------------------------------------
def test_unattributed_cost():
    sink = [{"session_id": "lonely", "input": 1000, "model": SONNET}]
    agg = C.aggregate(C.collect_sessions(sink, session_meta={}))  # no task link
    assert agg["tasks"] == []
    assert agg["unattributed_cost_usd"] == pytest.approx(C.session_cost(sink[0]), rel=1e-9)
    assert agg["attribution_coverage"] == 0.0


# 6. reconciliation alarm --------------------------------------------------------------------
def test_reconciliation_alarm():
    drift = C.reconcile(attributed_total=10.0, otel_global_total=12.0, tolerance=0.01)
    assert drift["alarm"] is True and drift["reason"] == "reconciliation_drift"
    ok = C.reconcile(attributed_total=11.99, otel_global_total=12.0, tolerance=0.01)
    assert ok["alarm"] is False and ok["reason"] == "ok"


# 7. model not in price table → error, not silent zero ---------------------------------------
def test_unknown_model_errors():
    with pytest.raises(ValueError) as ei:
        C.session_cost({"input": 1000, "model": "gpt-4-turbo"})
    assert "gpt-4-turbo" in str(ei.value)
    assert C.is_known_model("claude-opus-4") is True
    assert C.is_known_model("gpt-4-turbo") is False


# (+) excluded work-type cost is bucketed separately -----------------------------------------
def test_excluded_work_type_cost_separated():
    sink = [
        {"session_id": "impl", "input": 1000, "model": SONNET},
        {"session_id": "spec", "input": 5000, "model": SONNET},
    ]
    meta = {"impl": {"issue": 7, "work_type": "implementation"},
            "spec": {"work_type": "deliberative"}}  # spec/design = excluded (§2.5)
    agg = C.aggregate(C.collect_sessions(sink, meta))
    assert agg["excluded_cost_usd"] == pytest.approx(C.session_cost(sink[1]), rel=1e-9)
    # the excluded deliberative session is NOT in tasks or unattributed
    assert agg["attributed_cost_usd"] == pytest.approx(C.session_cost(sink[0]), rel=1e-9)
    assert agg["unattributed_cost_usd"] == 0.0


# (+) report labels gated metrics diagnostic_only --------------------------------------------
def test_report_marks_targets_diagnostic_only():
    rep = C.build_report([{"session_id": "s", "input": 1000, "model": SONNET}],
                         session_meta={"s": {"issue": 1}}, otel_global_total=None)
    assert "waste_token_share" in rep["diagnostic_only"]
    assert rep["diagnostic_only"]["cost_per_no_observed_defect"] is None
