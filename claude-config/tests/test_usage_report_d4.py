"""Acceptance tests for issue #322 — D4 report enhancements.

Tests:
- mixed-billing fixture → three separate buckets, never summed; subscription has `*`
- all-unattributed fixture → renders, coverage 0%, no crash, "unattributed" row present
- quarantine non-empty → "Quarantine: N rows" + model names; empty/None → section absent
- diagnostic badge present in recommendations heading
- write_report → .md file created with billing split + coverage text
- tier_approximate logic: pr_git → not approximate; absent/other → approximate
"""

import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_report as R  # noqa: E402
import usage_aggregator as A  # noqa: E402


def _rec(**kw):
    base = {
        "provider": "claude",
        "model": "claude-opus-4",
        "project": "agents",
        "task": "issue:42",
        "input": 900_000,
        "output": 1000,
        "cache_read": 100_000,
        "cache_creation": 0,
        "cost_usd": 2.0,
        "inference_host": "mac",
        "work_host": "mac",
        "session_id": "s1",
        "ts": "2026-06-01T00:00:00Z",
        "billing_type": "subscription",
        "files_changed": 3,
        "files_changed_source": "none",
    }
    base.update(kw)
    return base


def _parses(html_str: str) -> bool:
    HTMLParser().feed(html_str)
    return (
        "<!DOCTYPE html>" in html_str
        and html_str.count("<body>") == 1
        and html_str.count("</body>") == 1
    )


# ---------------------------------------------------------------------------
# AC: mixed-billing fixture → three separate buckets, NEVER one summed total
# ---------------------------------------------------------------------------


def test_billing_headline_three_buckets():
    """Mixed metered+subscription → three labeled lines, never a single summed total (D4 AC)."""
    recs = [
        _rec(billing_type="metered", cost_usd=1.50, session_id="m1"),
        _rec(billing_type="subscription", cost_usd=3.00, session_id="s1"),
        _rec(billing_type="unknown", cost_usd=0.50, session_id="u1"),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert _parses(h)
    # Each bucket must appear as a labeled line
    assert "Metered (real $):" in h
    assert "Subscription (projected $, notional) *:" in h
    assert "Unknown:" in h
    # Subscription must carry * marker
    assert "notional) *:" in h
    # Must NOT contain a single unlabeled total — "Total:" outside of fallback must not appear
    # The old single-line "Total: $X.XX" should be gone from the headline paragraph
    assert "Metered (real $): $1.50" in h
    assert "Subscription (projected $, notional) *: $3.00" in h
    assert "Unknown: $0.50" in h


def test_billing_headline_subscription_only():
    """Subscription-only data → single labeled subscription line (not old flat total)."""
    recs = [_rec(billing_type="subscription", cost_usd=5.0, session_id="s1")]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert "Subscription (projected $, notional) *:" in h
    assert "Metered (real $)" not in h
    assert "Unknown:" not in h


def test_billing_headline_metered_only():
    """Metered-only data → single labeled metered line with no subscription star."""
    recs = [_rec(billing_type="metered", cost_usd=2.0, session_id="m1")]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert "Metered (real $): $2.00" in h
    assert "Subscription" not in h or "Subscription (projected" not in h


def test_billing_headline_no_single_summed_total_when_mixed():
    """When metered + subscription are both present, there MUST be NO single summed total line
    in the billing headline (D4 AC: 'never a single summed total')."""
    recs = [
        _rec(billing_type="metered", cost_usd=1.0, session_id="m1"),
        _rec(billing_type="subscription", cost_usd=2.0, session_id="s1"),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    # The old pattern "Total: $X.XX" must not appear in the headline paragraph
    # (it would be a single summed total)
    assert "Metered (real $):" in h and "Subscription (projected $, notional) *:" in h
    # Confirm NO raw summation: $3.00 is the sum — if it appears, it should only be in
    # billing-aware contexts (e.g., a table cell), not as a standalone "Total:" headline
    # We check the headline paragraph specifically
    import re

    headline_match = re.search(r"<p>(.*?)</p>", h, re.DOTALL)
    assert headline_match is not None
    first_p = headline_match.group(1)
    assert "Total:" not in first_p


# ---------------------------------------------------------------------------
# AC: all-unattributed fixture → renders, coverage 0%, no crash, "unattributed" row
# ---------------------------------------------------------------------------


def test_all_unattributed_no_crash():
    """All records with project=None AND task=None → renders without crash (D4 AC)."""
    recs = [
        _rec(
            project=None,
            task=None,
            billing_type="metered",
            cost_usd=1.0,
            session_id="u1",
        ),
        _rec(
            project=None,
            task=None,
            billing_type="metered",
            cost_usd=2.0,
            session_id="u2",
        ),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert _parses(h)


def test_all_unattributed_coverage_zero():
    """All records unattributed → attribution coverage shows 0% (D4 AC)."""
    recs = [
        _rec(
            project=None,
            task=None,
            billing_type="metered",
            cost_usd=1.0,
            session_id="u1",
        ),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    # Coverage section should show 0%
    assert "0.0%" in h


def test_all_unattributed_row_present():
    """project/task == None → 'unattributed' row present in By Project/Task table (D4 AC)."""
    recs = [
        _rec(
            project=None,
            task=None,
            billing_type="metered",
            cost_usd=1.0,
            session_id="u1",
        ),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert "unattributed" in h


def test_partial_attribution_unattributed_row():
    """Some records attributed, some not → unattributed row present and coverage < 100%."""
    recs = [
        _rec(
            project="proj-a",
            task="issue:1",
            billing_type="metered",
            cost_usd=3.0,
            session_id="a1",
        ),
        _rec(
            project=None,
            task=None,
            billing_type="metered",
            cost_usd=1.0,
            session_id="u1",
        ),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert "unattributed" in h
    # Coverage is 3.0/4.0 = 75%
    assert "75.0%" in h


# ---------------------------------------------------------------------------
# AC: quarantine non-empty → "Quarantine: N rows" + model names; empty → absent
# ---------------------------------------------------------------------------


def test_quarantine_non_empty_renders():
    """Non-empty quarantine → 'Quarantine: N rows' + model names (D4 AC)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    q = {"count": 3, "models": ["claude-new-x", "gpt-6"]}
    h = R.render_html(agg, records=recs, quarantine=q)
    assert "Quarantine: 3 rows" in h
    assert "claude-new-x" in h
    assert "gpt-6" in h


def test_quarantine_none_omitted():
    """quarantine=None → quarantine section absent (D4 AC)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs, quarantine=None)
    assert "Quarantine:" not in h


def test_quarantine_empty_dict_omitted():
    """quarantine with count=0 and no models → section absent (D4 AC)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs, quarantine={"count": 0, "models": []})
    assert "Quarantine:" not in h


def test_quarantine_int_form():
    """quarantine as plain int → 'Quarantine: N rows' (alternate call form)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs, quarantine=5)
    assert "Quarantine: 5 rows" in h


def test_quarantine_model_name_escaped():
    """Model names in quarantine are HTML-escaped (no XSS)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    q = {"count": 1, "models": ["<script>alert(1)</script>"]}
    h = R.render_html(agg, records=recs, quarantine=q)
    assert "<script>alert(1)</script>" not in h
    assert "&lt;script&gt;" in h


# ---------------------------------------------------------------------------
# AC: [diagnostic] badge present in recommendations heading
# ---------------------------------------------------------------------------


def test_diagnostic_badge_in_recommendations_heading():
    """Recommendations section heading must contain '[diagnostic]' badge (D4 AC)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert "[diagnostic]" in h
    # Badge must be inside the recommendations heading element
    assert "id='recommendations'" in h
    idx = h.index("id='recommendations'")
    # Find the heading tag containing "recommendations"
    heading_chunk = h[idx : idx + 200]
    assert "[diagnostic]" in heading_chunk


# ---------------------------------------------------------------------------
# AC: write_report → .md file created alongside .html
# ---------------------------------------------------------------------------


def test_write_report_creates_md_file(tmp_path):
    """write_report must produce a .md file alongside the .html (D4 AC)."""
    recs = [
        _rec(billing_type="metered", cost_usd=2.0, session_id="m1"),
        _rec(billing_type="subscription", cost_usd=3.0, session_id="s1"),
    ]
    agg = A.aggregate(recs)
    out_html = tmp_path / "reports" / "usage.html"
    R.write_report(agg, out_html, records=recs)
    md_path = tmp_path / "reports" / "usage.md"
    assert md_path.exists(), ".md summary file must be created alongside .html"


def test_write_report_md_contains_billing_split(tmp_path):
    """The .md summary must contain billing split lines (D4 AC)."""
    recs = [
        _rec(billing_type="metered", cost_usd=2.0, session_id="m1"),
        _rec(billing_type="subscription", cost_usd=3.0, session_id="s1"),
    ]
    agg = A.aggregate(recs)
    out_html = tmp_path / "report.html"
    R.write_report(agg, out_html, records=recs)
    md = (tmp_path / "report.md").read_text()
    assert "Metered" in md
    assert "Subscription" in md
    assert "$2.00" in md
    assert "$3.00" in md


def test_write_report_md_contains_coverage(tmp_path):
    """The .md summary must contain attribution coverage text (D4 AC)."""
    recs = [
        _rec(
            billing_type="metered",
            cost_usd=1.0,
            project="proj",
            task="issue:1",
            session_id="a1",
        ),
        _rec(
            billing_type="metered",
            cost_usd=1.0,
            project=None,
            task=None,
            session_id="u1",
        ),
    ]
    agg = A.aggregate(recs)
    out_html = tmp_path / "report.html"
    R.write_report(agg, out_html, records=recs)
    md = (tmp_path / "report.md").read_text()
    assert "Attribution Coverage" in md
    assert "50.0%" in md


def test_write_report_md_contains_quarantine(tmp_path):
    """The .md summary must include quarantine info when non-empty (D4 AC)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    out_html = tmp_path / "report.html"
    R.write_report(
        agg, out_html, records=recs, quarantine={"count": 2, "models": ["model-xyz"]}
    )
    md = (tmp_path / "report.md").read_text()
    assert "2 rows quarantined" in md
    assert "model-xyz" in md


def test_write_report_md_quarantine_none_when_absent(tmp_path):
    """The .md summary shows 'None' for quarantine when not passed (D4 AC)."""
    recs = [_rec(billing_type="metered", cost_usd=1.0)]
    agg = A.aggregate(recs)
    out_html = tmp_path / "report.html"
    R.write_report(agg, out_html, records=recs)
    md = (tmp_path / "report.md").read_text()
    assert "Quarantine" in md
    assert "None" in md


# ---------------------------------------------------------------------------
# AC: tier_approximate logic
# ---------------------------------------------------------------------------


def test_model_tier_pr_git_not_approximate():
    """Records with files_changed_source=pr_git → tier NOT marked approximate (D4 spec)."""
    recs = [
        _rec(
            project="proj",
            task="issue:1",
            model="claude-opus-4",
            files_changed=1,
            files_changed_source="pr_git",
            billing_type="metered",
            cost_usd=1.0,
            session_id="pg1",
        ),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    # TRIVIAL tier from files_changed=1 and all records are pr_git → should NOT have "(tier approximate)"
    assert "tier approximate" not in h


def test_model_tier_missing_source_is_approximate():
    """Records with files_changed_source absent/none → tier marked approximate (D4 spec)."""
    recs = [
        _rec(
            project="proj",
            task="issue:1",
            model="claude-opus-4",
            files_changed=1,
            files_changed_source="none",
            billing_type="metered",
            cost_usd=1.0,
            session_id="ms1",
        ),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    assert "tier approximate" in h


def test_model_tier_mixed_source_is_approximate():
    """Group with one pr_git + one session_shard record → still approximate (all must be pr_git)."""
    recs = [
        _rec(
            project="proj",
            task="issue:1",
            model="claude-opus-4",
            files_changed=1,
            files_changed_source="pr_git",
            billing_type="metered",
            cost_usd=1.0,
            session_id="pg1",
        ),
        _rec(
            project="proj",
            task="issue:2",
            model="claude-opus-4",
            files_changed=1,
            files_changed_source="session_shard",
            billing_type="metered",
            cost_usd=1.0,
            session_id="ss1",
        ),
    ]
    agg = A.aggregate(recs)
    h = R.render_html(agg, records=recs)
    # At least one non-pr_git record in the group → approximate
    assert "tier approximate" in h


# ---------------------------------------------------------------------------
# AC: by project/task table shows unattributed row explicitly
# ---------------------------------------------------------------------------


def test_by_project_task_unattributed_row_explicit():
    """project=None and task=None → 'unattributed' row appears (not hidden) in the table (D4 AC)."""
    recs = [
        _rec(
            project="proj-a",
            task="issue:1",
            billing_type="metered",
            cost_usd=3.0,
            session_id="a1",
        ),
        _rec(
            project=None,
            task=None,
            billing_type="metered",
            cost_usd=1.0,
            session_id="u1",
        ),
    ]
    h = R._by_project_task_html(recs)
    assert "unattributed" in h
    assert "proj-a" in h


def test_by_project_task_only_unattributed():
    """All records unattributed → table still renders with unattributed row (D4 AC)."""
    recs = [
        _rec(
            project=None,
            task=None,
            billing_type="metered",
            cost_usd=1.0,
            session_id="u1",
        ),
    ]
    h = R._by_project_task_html(recs)
    assert "unattributed" in h
    assert "no data" not in h


def test_by_project_task_empty_records():
    """Empty records → no-data state (no crash) (D4 AC)."""
    h = R._by_project_task_html([])
    assert "no data" in h


# ---------------------------------------------------------------------------
# Integration: full render with all D4 features together
# ---------------------------------------------------------------------------


def test_d4_full_integration():
    """Full integration test: mixed billing, unattributed records, quarantine, all sections render."""
    recs = [
        _rec(
            billing_type="metered",
            cost_usd=2.0,
            project="proj-a",
            task="issue:1",
            session_id="m1",
            files_changed=3,
            files_changed_source="pr_git",
        ),
        _rec(
            billing_type="subscription",
            cost_usd=3.0,
            project=None,
            task=None,
            session_id="s1",
            files_changed=1,
            files_changed_source="none",
        ),
    ]
    agg = A.aggregate(recs)
    q = {"count": 2, "models": ["new-model-x"]}
    h = R.render_html(agg, records=recs, quarantine=q)
    assert _parses(h)
    # Billing split
    assert "Metered (real $):" in h
    assert "Subscription (projected $, notional) *:" in h
    # Unattributed
    assert "unattributed" in h
    # Quarantine
    assert "Quarantine: 2 rows" in h
    assert "new-model-x" in h
    # Diagnostic badge
    assert "[diagnostic]" in h
    # Attribution coverage present
    assert "Attribution Coverage" in h
