"""Acceptance tests for issue #266 — usage aggregator + normalization (§5)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_aggregator as A  # noqa: E402
import otel_sink as O  # noqa: E402


def _r(**kw):
    base = {
        "provider": "claude",
        "model": "claude-opus-4",
        "project": "agents",
        "task": "issue:42",
        "input": 1000,
        "output": 100,
        "cache_read": 0,
        "cache_creation": 0,
        "cost_usd": 1.0,
        "inference_host": "mac",
        "work_host": "mac",
        "session_id": "s1",
        "ts": "2026-06-01T00:00:00Z",
        "billing_type": "subscription",
    }
    base.update(kw)
    return base


# cross-host shards attributed by inference_host -----------------------------------------------------
def test_read_shards_two_hosts(tmp_path):
    for host, cost in (("mac", 1.0), ("server", 2.0)):
        d = tmp_path / host
        d.mkdir()
        (d / "usage.jsonl").write_text(
            json.dumps(_r(inference_host=host, cost_usd=cost)) + "\n"
        )
    recs = A.read_shards(tmp_path)
    assert {r["inference_host"] for r in recs} == {"mac", "server"}
    assert A._cost(recs) == 3.0


# $/issue = sum of the task's records ---------------------------------------------------------------
def test_cost_per_issue():
    recs = [
        _r(cost_usd=1.0, session_id="a"),
        _r(cost_usd=2.0, session_id="b"),
        _r(cost_usd=3.0, session_id="c"),
    ]
    assert A.by_issue(recs)["issue:42"]["cost_usd"] == 6.0


# task_tier bands ----------------------------------------------------------------------------------
def test_task_tier_bands():
    assert A.task_tier(1) == A.TIER_TRIVIAL
    assert A.task_tier(3) == A.TIER_SIMPLE
    assert A.task_tier(8) == A.TIER_COMPLEX
    assert A.task_tier(None) == A.TIER_UNKNOWN


# cache_pct ----------------------------------------------------------------------------------------
def test_cache_pct():
    assert A.cache_pct({"input": 900_000, "cache_read": 100_000}) == 0.10


# cache_saved_usd vs full input price --------------------------------------------------------------
def test_cache_saved_usd():
    row = O.PRICES["claude-opus-4"]
    expected = 100_000 * (row["input"] - row["cache_read"])
    assert A.cache_saved_usd(
        {"model": "claude-opus-4", "cache_read": 100_000}
    ) == round(expected, 10)


# burn-rate over UNION of overlapping spans, not 2x serial ------------------------------------------
def test_burn_rate_union_span():
    # A [00:00,02:00] $10 ; B [01:00,03:00] $10 ; union = 3h → burn = 20/3
    recs = [
        _r(session_id="A", ts="2026-06-01T00:00:00Z", cost_usd=5.0),
        _r(session_id="A", ts="2026-06-01T02:00:00Z", cost_usd=5.0),
        _r(session_id="B", ts="2026-06-01T01:00:00Z", cost_usd=5.0),
        _r(session_id="B", ts="2026-06-01T03:00:00Z", cost_usd=5.0),
    ]
    c = A.concurrency(recs)["mac"]
    assert c["active_wall_clock_hours"] == 3.0  # union, not 2+2=4 serial
    assert round(c["burn_rate_usd_per_hour"], 2) == round(20 / 3, 2)


# peak concurrent sessions -------------------------------------------------------------------------
def test_peak_concurrent():
    # 3 sessions all overlapping 01:00-01:30
    recs = []
    for sid in ("A", "B", "C"):
        recs.append(_r(session_id=sid, ts="2026-06-01T01:00:00Z"))
        recs.append(_r(session_id=sid, ts="2026-06-01T02:00:00Z"))
    assert A.concurrency(recs)["mac"]["peak_concurrent_sessions"] == 3


# mixed billing_type labeled mixed, NEVER summed to one cash figure --------------------------------
def test_mixed_billing_not_summed():
    recs = [
        _r(billing_type="subscription", session_id="a", cost_usd=3.0),
        _r(billing_type="metered", session_id="b", cost_usd=2.0),
    ]
    grp = A.by_issue(recs)["issue:42"]
    assert grp["billing_type"] == "mixed"
    assert grp["cost_usd"] is None  # no single mixed cash figure
    assert grp["cost_by_billing"] == {
        "subscription": 3.0,
        "metered": 2.0,
    }  # broken out instead
    tot = A.aggregate(recs)["totals"]
    assert tot["cost_usd"] is None and tot["cost_by_billing"]["metered"] == 2.0
    # single-billing still gets a flat cost_usd
    single = A.by_issue([_r(cost_usd=5.0)])["issue:42"]
    assert single["cost_usd"] == 5.0 and single["billing_type"] == "subscription"


# missing billing_type counts as a distinct kind → mixed (not folded into a real type) -------------
def test_missing_billing_is_mixed():
    recs = [
        _r(billing_type="metered", session_id="a", cost_usd=2.0),
        _r(billing_type=None, session_id="b", cost_usd=3.0),
    ]
    grp = A.by_issue(recs)["issue:42"]
    assert grp["billing_type"] == "mixed"  # metered + unknown → mixed, NOT "metered"
    assert grp["cost_usd"] is None
    assert grp["cost_by_billing"] == {"metered": 2.0, "unknown": 3.0}


# cache_saved_usd is mixed-guarded too -------------------------------------------------------------
def test_cache_saved_mixed_guard():
    recs = [
        _r(billing_type="subscription", session_id="a", cache_read=100_000),
        _r(billing_type="metered", session_id="b", cache_read=100_000),
    ]
    proj = A.cache_by_project(recs)["agents"]
    assert proj["cache_saved_usd"] is None  # mixed → no single savings figure
    assert set(proj["cache_saved_by_billing"]) == {"subscription", "metered"}
    # single-billing project → flat savings present
    single = A.cache_by_project([_r(cache_read=100_000)])["agents"]
    assert single["cache_saved_usd"] is not None


# malformed cost_usd does not crash aggregation ----------------------------------------------------
def test_malformed_cost_no_crash():
    recs = [_r(cost_usd="n/a", session_id="a"), _r(cost_usd=2.0, session_id="b")]
    assert (
        A.by_issue(recs)["issue:42"]["cost_usd"] == 2.0
    )  # bad value coerced to 0, no crash


# git join missing → unavailable, not 0 ------------------------------------------------------------
def test_cost_per_pr_unavailable():
    recs = [_r(task="issue:99", cost_usd=5.0)]
    out = A.cost_per_pr(recs, files_by_task={})  # no git data for issue:99
    assert out["issue:99"]["cost_per_file_changed"] == A.UNAVAILABLE
    assert out["issue:99"]["cost_per_pr"] == A.UNAVAILABLE
    # with files data → computed
    out2 = A.cost_per_pr(recs, files_by_task={"issue:99": 5})
    assert out2["issue:99"]["cost_per_file_changed"] == 1.0


# model mix per project ----------------------------------------------------------------------------
def test_model_mix():
    recs = [
        _r(model="claude-opus-4", cost_usd=10.0),
        _r(model="gpt-5.5", cost_usd=2.0, provider="codex"),
    ]
    mix = A.model_mix(recs)["agents"]
    assert (
        mix["claude-opus-4"]["cost_usd"] == 10.0 and mix["gpt-5.5"]["cost_usd"] == 2.0
    )


# full pipeline: two shards → aggregate JSON with all sections --------------------------------------
def test_integration_aggregate(tmp_path):
    for host in ("mac", "server"):
        d = tmp_path / host
        d.mkdir()
        (d / "usage.jsonl").write_text(
            "\n".join(
                json.dumps(r)
                for r in [
                    _r(
                        inference_host=host,
                        session_id=f"{host}1",
                        files_changed=3,
                        ts="2026-06-01T00:00:00Z",
                    ),
                    _r(
                        inference_host=host,
                        session_id=f"{host}1",
                        files_changed=3,
                        ts="2026-06-01T01:00:00Z",
                    ),
                ]
            )
        )
    out = A.aggregate(A.read_shards(tmp_path), files_by_task={"issue:42": 3})
    for section in (
        "totals",
        "by_issue",
        "by_tier",
        "cost_per_pr",
        "model_mix",
        "cost_by_model_tier",
        "cache_by_project",
        "concurrency",
    ):
        assert section in out, section
    assert out["totals"]["records"] == 4
    assert out["by_tier"]["SIMPLE"]["cost_usd"] == 4.0  # files_changed=3 → SIMPLE
    assert set(out["concurrency"]) == {"mac", "server"}
