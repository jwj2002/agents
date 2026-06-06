"""Acceptance tests for issue #267 — Tier-A static HTML usage report (§7)."""

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
    }
    base.update(kw)
    return base


def _parses(html: str) -> bool:
    HTMLParser().feed(html)  # raises on nothing-fatal; structural sanity
    return (
        "<!DOCTYPE html>" in html
        and html.count("<body>") == 1
        and html.count("</body>") == 1
    )


# all six section headers present -------------------------------------------------------------------
def test_six_sections():
    agg = A.aggregate(
        [_rec(model="claude-opus-4"), _rec(model="claude-haiku-4", session_id="s2")],
        files_by_task={"issue:42": 3},
    )
    html = R.render_html(agg)
    for sid, _ in R.SECTIONS:
        assert f"id='{sid}'" in html, sid
    assert _parses(html)


# subscription → notional annotation -----------------------------------------------------------------
def test_subscription_notional_labeled():
    html = R.render_html(A.aggregate([_rec(billing_type="subscription")]))
    assert "notional" in html  # footnote present
    assert "$2.00 *" in html  # the subscription figure is starred


# metered → plain, no notional star next to it -----------------------------------------------------
def test_metered_not_starred():
    html = R.render_html(A.aggregate([_rec(billing_type="metered", cost_usd=2.0)]))
    assert (
        "$2.00" in html and "$2.00 *" not in html
    )  # metered cash is not starred
    assert R._NOTIONAL_FOOTNOTE not in html  # no subscription → no notional footnote
    # (the cost-chart axis title carries a general notional caveat — that's expected, not the footnote)


# mixed billing → both labeled, never a single unlabeled figure ------------------------------------
def test_mixed_billing_labeled():
    recs = [
        _rec(billing_type="subscription", cost_usd=3.0, session_id="a"),
        _rec(billing_type="metered", cost_usd=2.0, session_id="b"),
    ]
    html = R.render_html(A.aggregate(recs))
    assert "mixed (" in html  # broken out, not summed
    # subscription bucket inside mixed is ALSO marked notional (*); metered is plain
    assert "subscription: $3.00 *" in html and "metered: $2.00" in html


# malformed numeric fields render safely, never crash ----------------------------------------------
def test_malformed_fields_no_crash():
    # a malicious/malformed cost_usd must not crash AND must not inject HTML
    agg = {
        "totals": {
            "cost_usd": "</script><img onerror=alert(1)>",
            "billing_type": "metered",
            "records": 1,
        },
        "by_issue": {},
        "by_tier": {"SIMPLE": {"cost_usd": "n/a", "billing_type": "metered"}},
        "cost_per_pr": {},
        "model_mix": {},
        "cost_by_model_tier": {},
        "cache_by_project": {
            "p": {"cache_pct": "bad", "cache_saved_usd": "x", "billing_type": "metered"}
        },
        "concurrency": {},
    }
    html = R.render_html(agg)  # must not raise
    assert _parses(html)
    assert "n/a" in html  # malformed cost rendered as n/a
    assert "</script><img" not in html  # not injected


# zero records → no crash, no-data states ----------------------------------------------------------
def test_zero_records():
    html = R.render_html(A.aggregate([]))
    assert _parses(html)
    assert "no data" in html
    for sid, _ in R.SECTIONS:
        assert f"id='{sid}'" in html


# cache_pct 0.10 surfaces in the cache section -----------------------------------------------------
def test_cache_pct_rendered():
    # input 900k + cache_read 100k → 10%
    html = R.render_html(A.aggregate([_rec(input=900_000, cache_read=100_000)]))
    assert "10.0%" in html


# two hosts with overlapping sessions → per-host peak in concurrency --------------------------------
def test_concurrency_per_host():
    recs = []
    for host in ("mac", "server"):
        for sid in ("A", "B"):  # two overlapping sessions per host
            recs.append(
                _rec(
                    inference_host=host,
                    session_id=f"{host}{sid}",
                    ts="2026-06-01T01:00:00Z",
                )
            )
            recs.append(
                _rec(
                    inference_host=host,
                    session_id=f"{host}{sid}",
                    ts="2026-06-01T02:00:00Z",
                )
            )
    agg = A.aggregate(recs)
    assert agg["concurrency"]["mac"]["peak_concurrent_sessions"] == 2
    html = R.render_html(agg)
    assert "id='concurrency'" in html and "mac" in html and "server" in html


# XSS guard: a malicious string in data cannot break out of the <script> block ----------------------
def test_xss_guard():
    html = R.render_html(
        A.aggregate([_rec(project="</script><img src=x onerror=alert(1)>")])
    )
    assert (
        "</script><img" not in html
    )  # escaped in both the table (html.escape) and the JSON blob


# integration: aggregator fixture → file on disk → valid HTML --------------------------------------
def test_integration_write_report(tmp_path):
    recs = [
        _rec(files_changed=3),
        _rec(
            project="buddy",
            model="gpt-5.5",
            provider="codex",
            billing_type="metered",
            cost_usd=0.1,
            session_id="s9",
            ts="2026-06-08T00:00:00Z",
            files_changed=1,
            task="issue:9",
        ),
    ]
    agg = A.aggregate(recs, files_by_task={"issue:42": 3, "issue:9": 1})
    out = tmp_path / "reports" / "usage.html"
    path = R.write_report(agg, out, records=recs)
    written = Path(path).read_text()
    assert _parses(written)
    assert "Cost by Project" in written and "Concurrency" in written
