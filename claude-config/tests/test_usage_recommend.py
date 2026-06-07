"""Tests for issue #268 Phase 1 — right-sizing recommendation engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_recommend as REC  # noqa: E402
import usage_aggregator as A  # noqa: E402
import usage_report as R  # noqa: E402
import otel_sink as O  # noqa: E402


def _r(**kw):
    """Minimal synthetic usage record factory (matches test_usage_aggregator convention)."""
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
        "files_changed": 1,  # TRIVIAL by default
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Empty / edge input
# ---------------------------------------------------------------------------


def test_empty_records_returns_empty_list():
    agg = A.aggregate([])
    result = REC.recommend(agg, [])
    assert result == []


def test_none_records_returns_empty_list():
    """recommend() must not crash when records=None."""
    agg = A.aggregate([])
    result = REC.recommend(agg, None)
    assert result == []


# ---------------------------------------------------------------------------
# Type 1 — model_tier_mismatch
# ---------------------------------------------------------------------------


def test_no_mismatch_when_cheapest_model_used():
    """TRIVIAL records on claude-haiku-4 (cheapest) → no type1 finding."""
    recs = [_r(model="claude-haiku-4", files_changed=1)]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type1 = [f for f in findings if f["type"] == "model_tier_mismatch"]
    assert type1 == []


def test_mismatch_detected_opus_on_trivial():
    """TRIVIAL record using claude-opus-4 → one type1 finding."""
    recs = [_r(model="claude-opus-4", files_changed=1, billing_type="subscription")]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type1 = [f for f in findings if f["type"] == "model_tier_mismatch"]
    assert len(type1) == 1
    assert type1[0]["type"] == "model_tier_mismatch"
    assert type1[0]["evidence"]["model_used"] == "claude-opus-4"
    assert type1[0]["evidence"]["tier"] == "TRIVIAL"


def test_mismatch_detected_sonnet_on_simple():
    """SIMPLE record on claude-sonnet-4 → type1 finding (haiku is cheaper)."""
    recs = [_r(model="claude-sonnet-4", files_changed=2, billing_type="metered")]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type1 = [f for f in findings if f["type"] == "model_tier_mismatch"]
    assert len(type1) == 1
    assert type1[0]["evidence"]["suggested_model"] == "claude-haiku-4"


def test_no_mismatch_on_complex_tier():
    """COMPLEX records with expensive model are not flagged (downshift only for TRIVIAL/SIMPLE)."""
    recs = [_r(model="claude-opus-4", files_changed=5, billing_type="subscription")]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type1 = [f for f in findings if f["type"] == "model_tier_mismatch"]
    assert type1 == []


# ---------------------------------------------------------------------------
# Downshift savings math
# ---------------------------------------------------------------------------


def test_downshift_savings_math():
    """Single opus-4 record: 1M input tokens. savings = 1M × (15e-6 - 0.80e-6) = 14.20 exactly."""
    rec = _r(
        model="claude-opus-4",
        input=1_000_000,
        output=0,
        cache_read=0,
        cache_creation=0,
    )
    # downshift to haiku (cheapest in _CLAUDE_TIER_ORDER[0])
    savings = REC._downshift_savings([rec], "claude-haiku-4")
    expected = 1_000_000 * (
        O.PRICES["claude-opus-4"]["input"] - O.PRICES["claude-haiku-4"]["input"]
    )
    assert abs(savings - expected) < 1e-6


def test_downshift_savings_opus_to_sonnet():
    """1M input tokens opus→sonnet savings = 1M × (15e-6 - 3e-6) = 12.00."""
    rec = _r(
        model="claude-opus-4",
        input=1_000_000,
        output=0,
        cache_read=0,
        cache_creation=0,
    )
    savings = REC._downshift_savings([rec], "claude-sonnet-4")
    assert abs(savings - 12.00) < 1e-6


def test_downshift_savings_empty_records():
    assert REC._downshift_savings([], "claude-haiku-4") == 0.0


# ---------------------------------------------------------------------------
# Billing framing in estimated_impact
# ---------------------------------------------------------------------------


def test_subscription_impact_labeled_notional():
    """Mismatch on subscription records → estimated_impact contains 'notional'."""
    recs = [
        _r(
            model="claude-opus-4",
            files_changed=1,
            billing_type="subscription",
            input=100_000,
        )
    ]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type1 = [f for f in findings if f["type"] == "model_tier_mismatch"]
    assert type1, "Expected a type1 finding"
    impact = type1[0]["estimated_impact"]
    assert impact is not None
    assert "notional" in impact


def test_metered_impact_labeled_dollar():
    """Mismatch on metered records → estimated_impact starts with '$'."""
    recs = [
        _r(
            model="claude-opus-4",
            files_changed=1,
            billing_type="metered",
            input=100_000,
        )
    ]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type1 = [f for f in findings if f["type"] == "model_tier_mismatch"]
    assert type1, "Expected a type1 finding"
    impact = type1[0]["estimated_impact"]
    assert impact is not None
    assert impact.startswith("$")
    assert "notional" not in impact


def test_mixed_billing_impact_is_none():
    """Mismatch where records span subscription+metered → estimated_impact is None."""
    recs = [
        _r(
            model="claude-opus-4",
            files_changed=1,
            billing_type="subscription",
            session_id="a",
        ),
        _r(
            model="claude-opus-4",
            files_changed=1,
            billing_type="metered",
            session_id="b",
        ),
    ]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type1 = [f for f in findings if f["type"] == "model_tier_mismatch"]
    assert type1, "Expected a type1 finding"
    assert type1[0]["estimated_impact"] is None


# ---------------------------------------------------------------------------
# Type 2 — cost_outlier
# ---------------------------------------------------------------------------


def test_outlier_requires_three_tasks():
    """Only 2 tasks with numeric cost_per_file → no type2 findings."""
    recs = [
        _r(
            task="issue:1",
            files_changed=1,
            cost_usd=1.0,
            billing_type="metered",
            session_id="a",
        ),
        _r(
            task="issue:2",
            files_changed=1,
            cost_usd=10.0,
            billing_type="metered",
            session_id="b",
        ),
    ]
    files_by_task = {"issue:1": 1, "issue:2": 1}
    agg = A.aggregate(recs, files_by_task=files_by_task)
    findings = REC.recommend(agg, recs)
    type2 = [f for f in findings if f["type"] == "cost_outlier"]
    assert type2 == []


def test_outlier_detected_above_3x_median():
    """3 tasks: costs 1.0, 1.0, 4.0 per file → task with 4.0 flagged (ratio=4.0)."""
    recs = [
        _r(
            task="issue:1",
            files_changed=1,
            cost_usd=1.0,
            billing_type="metered",
            session_id="a",
        ),
        _r(
            task="issue:2",
            files_changed=1,
            cost_usd=1.0,
            billing_type="metered",
            session_id="b",
        ),
        _r(
            task="issue:3",
            files_changed=1,
            cost_usd=4.0,
            billing_type="metered",
            session_id="c",
        ),
    ]
    files_by_task = {"issue:1": 1, "issue:2": 1, "issue:3": 1}
    agg = A.aggregate(recs, files_by_task=files_by_task)
    findings = REC.recommend(agg, recs)
    type2 = [f for f in findings if f["type"] == "cost_outlier"]
    assert len(type2) == 1
    assert type2[0]["evidence"]["task"] == "issue:3"
    assert type2[0]["evidence"]["ratio"] >= 3.0


def test_no_outlier_below_3x_median():
    """3 tasks: costs 1.0, 1.5, 2.9 → none flagged (max ratio < 3×)."""
    recs = [
        _r(
            task="issue:1",
            files_changed=1,
            cost_usd=1.0,
            billing_type="metered",
            session_id="a",
        ),
        _r(
            task="issue:2",
            files_changed=1,
            cost_usd=1.5,
            billing_type="metered",
            session_id="b",
        ),
        _r(
            task="issue:3",
            files_changed=1,
            cost_usd=2.9,
            billing_type="metered",
            session_id="c",
        ),
    ]
    files_by_task = {"issue:1": 1, "issue:2": 1, "issue:3": 1}
    agg = A.aggregate(recs, files_by_task=files_by_task)
    findings = REC.recommend(agg, recs)
    type2 = [f for f in findings if f["type"] == "cost_outlier"]
    assert type2 == []


def test_outlier_impact_is_none():
    """Cost outlier estimated_impact is always None (investigation flag, not a recomputation)."""
    recs = [
        _r(
            task="issue:1",
            files_changed=1,
            cost_usd=1.0,
            billing_type="metered",
            session_id="a",
        ),
        _r(
            task="issue:2",
            files_changed=1,
            cost_usd=1.0,
            billing_type="metered",
            session_id="b",
        ),
        _r(
            task="issue:3",
            files_changed=1,
            cost_usd=4.0,
            billing_type="metered",
            session_id="c",
        ),
    ]
    files_by_task = {"issue:1": 1, "issue:2": 1, "issue:3": 1}
    agg = A.aggregate(recs, files_by_task=files_by_task)
    findings = REC.recommend(agg, recs)
    type2 = [f for f in findings if f["type"] == "cost_outlier"]
    assert type2
    assert type2[0]["estimated_impact"] is None


# ---------------------------------------------------------------------------
# Type 3 — model_mix_skew
# ---------------------------------------------------------------------------


def test_model_mix_skew_detected_high_opus_share():
    """Project with 80% spend on claude-opus-4 including TRIVIAL records → type3 finding."""
    recs = [
        # 8 TRIVIAL records on opus (80% of spend)
        *[
            _r(
                model="claude-opus-4",
                files_changed=1,
                cost_usd=1.0,
                billing_type="subscription",
                session_id=f"a{i}",
            )
            for i in range(8)
        ],
        # 2 TRIVIAL records on haiku (20% of spend)
        *[
            _r(
                model="claude-haiku-4",
                files_changed=1,
                cost_usd=0.25,
                billing_type="subscription",
                session_id=f"b{i}",
            )
            for i in range(2)
        ],
    ]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type3 = [f for f in findings if f["type"] == "model_mix_skew"]
    assert len(type3) >= 1
    assert type3[0]["evidence"]["opus_share_pct"] > 70


def test_model_mix_skew_not_flagged_below_threshold():
    """Project with 60% opus spend → no type3 finding."""
    recs = [
        # 6 opus records (60%)
        *[
            _r(
                model="claude-opus-4",
                files_changed=1,
                cost_usd=1.0,
                billing_type="subscription",
                session_id=f"a{i}",
            )
            for i in range(6)
        ],
        # 4 haiku records (40%)
        *[
            _r(
                model="claude-haiku-4",
                files_changed=1,
                cost_usd=1.0,
                billing_type="subscription",
                session_id=f"b{i}",
            )
            for i in range(4)
        ],
    ]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type3 = [f for f in findings if f["type"] == "model_mix_skew"]
    assert type3 == []


def test_model_mix_skew_no_trivial_simple_opus_not_flagged():
    """High opus share but no TRIVIAL/SIMPLE opus records → no type3 finding."""
    recs = [
        # Opus only on COMPLEX (8 files each)
        *[
            _r(
                model="claude-opus-4",
                files_changed=8,
                cost_usd=1.0,
                billing_type="subscription",
                session_id=f"a{i}",
            )
            for i in range(8)
        ],
        # Haiku on TRIVIAL
        _r(
            model="claude-haiku-4",
            files_changed=1,
            cost_usd=0.25,
            billing_type="subscription",
            session_id="b0",
        ),
    ]
    agg = A.aggregate(recs)
    findings = REC.recommend(agg, recs)
    type3 = [f for f in findings if f["type"] == "model_mix_skew"]
    assert type3 == []


# ---------------------------------------------------------------------------
# Type 4 — cache_inefficiency
# ---------------------------------------------------------------------------


def test_cache_inefficiency_detected():
    """Project with cache_pct=0.05, total input 500_000 → type4 finding."""
    # Inject a synthetic agg directly (aggregator doesn't carry total_input_tokens)
    agg = {
        "cost_by_model_tier": {},
        "cost_per_pr": {},
        "cache_by_project": {
            "agents": {
                "cache_pct": 0.05,
                "total_input_tokens": 500_000,
                "billing_type": "subscription",
                "cache_saved_by_billing": {},
            }
        },
    }
    findings = REC.recommend(agg, [])
    type4 = [f for f in findings if f["type"] == "cache_inefficiency"]
    assert len(type4) == 1
    assert type4[0]["project"] == "agents"
    assert type4[0]["evidence"]["cache_pct"] == 0.05


def test_cache_not_flagged_small_project():
    """Project with cache_pct=0.02, total input 50_000 (< threshold) → no finding."""
    agg = {
        "cost_by_model_tier": {},
        "cost_per_pr": {},
        "cache_by_project": {
            "small": {
                "cache_pct": 0.02,
                "total_input_tokens": 50_000,
                "billing_type": "subscription",
                "cache_saved_by_billing": {},
            }
        },
    }
    findings = REC.recommend(agg, [])
    type4 = [f for f in findings if f["type"] == "cache_inefficiency"]
    assert type4 == []


def test_cache_not_flagged_above_threshold():
    """Project with cache_pct=0.15 → no finding (above the 10% threshold)."""
    agg = {
        "cost_by_model_tier": {},
        "cost_per_pr": {},
        "cache_by_project": {
            "agents": {
                "cache_pct": 0.15,
                "total_input_tokens": 500_000,
                "billing_type": "subscription",
                "cache_saved_by_billing": {},
            }
        },
    }
    findings = REC.recommend(agg, [])
    type4 = [f for f in findings if f["type"] == "cache_inefficiency"]
    assert type4 == []


def test_cache_impact_is_none():
    """Cache inefficiency estimated_impact is always None."""
    agg = {
        "cost_by_model_tier": {},
        "cost_per_pr": {},
        "cache_by_project": {
            "agents": {
                "cache_pct": 0.02,
                "total_input_tokens": 500_000,
                "billing_type": "subscription",
                "cache_saved_by_billing": {},
            }
        },
    }
    findings = REC.recommend(agg, [])
    type4 = [f for f in findings if f["type"] == "cache_inefficiency"]
    assert type4
    assert type4[0]["estimated_impact"] is None


def test_cache_inefficiency_fires_through_real_aggregate():
    """End-to-end (regression guard against dormancy): type-4 must fire from a REAL
    A.aggregate() output, NOT a hand-injected dict. This catches the case where
    cache_by_project stops emitting total_input_tokens (the field type-4 reads)."""
    # one project, 200k input, no cache reads → cache_pct=0 (<10%), input >= 100k threshold
    recs = [_r(project="agents", input=200_000, cache_read=0, cache_creation=0)]
    agg = A.aggregate(recs)
    assert (
        agg["cache_by_project"]["agents"]["total_input_tokens"] == 200_000
    )  # wiring present
    findings = REC.recommend(agg, recs)
    assert [f for f in findings if f["type"] == "cache_inefficiency"], (
        "type-4 did not fire through real aggregate() — cache_by_project wiring regressed"
    )


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


def test_recommend_output_is_sorted():
    """Mixed findings → sorted by type then project (string sort)."""
    recs = [_r(model="claude-opus-4", files_changed=1, billing_type="subscription")]
    agg = A.aggregate(recs)
    # Inject a cache finding as well
    agg["cache_by_project"]["agents"]["total_input_tokens"] = 500_000
    agg["cache_by_project"]["agents"]["cache_pct"] = 0.02
    findings = REC.recommend(agg, recs)
    types = [f["type"] for f in findings]
    assert types == sorted(types), "Findings must be sorted by type"


# ---------------------------------------------------------------------------
# Render integration
# ---------------------------------------------------------------------------


def test_render_html_includes_recommendations_section():
    """render_html with a mismatch record includes id='recommendations' and the finding text."""
    recs = [
        _r(
            model="claude-opus-4",
            files_changed=1,
            billing_type="subscription",
            input=100_000,
        )
    ]
    agg = A.aggregate(recs)
    html = R.render_html(agg, records=recs)
    assert "id='recommendations'" in html
    assert "model_tier_mismatch" in html


def test_render_html_no_data_state():
    """render_html with empty records includes id='recommendations' and 'No recommendations'."""
    agg = A.aggregate([])
    html = R.render_html(agg, records=[])
    assert "id='recommendations'" in html
    assert "No recommendations" in html


def test_render_html_seven_sections():
    """All 7 SECTIONS (including recommendations) are present in rendered HTML."""
    recs = [_r(model="claude-opus-4", files_changed=1)]
    agg = A.aggregate(recs)
    html = R.render_html(agg, records=recs)
    for sid, _ in R.SECTIONS:
        assert f"id='{sid}'" in html, f"Missing section: {sid}"
