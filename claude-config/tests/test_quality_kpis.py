"""Tests for quality_kpis.py — first-pass-correct rate + gates-caught KPIs.

Issue #386. All tests use tmp_path; no real ~/.claude files are read.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import quality_kpis as Q  # noqa: E402

# ---------------------------------------------------------------------------
# Fixed reference datetime: 2026-06-09 (Monday) = 2026-W24
# ---------------------------------------------------------------------------
NOW = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)

# Weeks built from NOW (oldest first, 8 weeks):
# 2026-W17, W18, W19, W20, W21, W22, W23, W24
WEEK_24 = "2026-W24"  # current week (contains 2026-06-09)
WEEK_23 = "2026-W23"  # one week ago
WEEK_22 = "2026-W22"  # two weeks ago


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _metrics(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "metrics.jsonl"
    _write_jsonl(p, records)
    return p


def _prove_log(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "prove-log.jsonl"
    _write_jsonl(p, records)
    return p


def _overrides(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "prove-overrides.jsonl"
    _write_jsonl(p, records)
    return p


def _absent(tmp_path: Path, name: str) -> Path:
    return tmp_path / name  # does NOT exist


# ---------------------------------------------------------------------------
# Test 1: empty sources → 8 zero rows, no exception
# ---------------------------------------------------------------------------

def test_empty_sources_returns_zero_table(tmp_path):
    kpis = Q.compute_kpis(
        metrics_path=_absent(tmp_path, "metrics.jsonl"),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[_absent(tmp_path, "overrides.jsonl")],
        weeks=8,
        now=NOW,
    )
    assert len(kpis["rows"]) == 8
    for row in kpis["rows"]:
        assert row["fpc_rate"] is None
        assert row["fpc_n"] == 0
        assert row["gates_caught"] == 0
    assert kpis["totals"]["fpc_rate"] is None
    assert kpis["totals"]["fpc_n"] == 0
    assert kpis["totals"]["gates_caught"] == 0


# ---------------------------------------------------------------------------
# Test 2: first-pass rate computed correctly
# ---------------------------------------------------------------------------

def test_first_pass_rate_computed_correctly(tmp_path):
    # 3 true, 1 false in WEEK_24 → 75%
    recs = [
        {"issue": 1, "date": "2026-06-09", "first_pass_correct": True},
        {"issue": 2, "date": "2026-06-09", "first_pass_correct": True},
        {"issue": 3, "date": "2026-06-09", "first_pass_correct": True},
        {"issue": 4, "date": "2026-06-09", "first_pass_correct": False},
    ]
    kpis = Q.compute_kpis(
        metrics_path=_metrics(tmp_path, recs),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[],
        now=NOW,
    )
    # Find WEEK_24 row
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    assert row["fpc_n"] == 4
    assert abs(row["fpc_rate"] - 0.75) < 1e-9
    assert row["gates_caught"] == 0


# ---------------------------------------------------------------------------
# Test 3: records without first_pass_correct field excluded from denominator
# ---------------------------------------------------------------------------

def test_records_without_fpc_field_excluded_from_denominator(tmp_path):
    recs = [
        {"issue": 1, "date": "2026-06-09"},            # no fpc field — excluded
        {"issue": 2, "date": "2026-06-09", "first_pass_correct": None},  # explicit None — excluded
        {"issue": 3, "date": "2026-06-09", "first_pass_correct": True},  # counts
    ]
    kpis = Q.compute_kpis(
        metrics_path=_metrics(tmp_path, recs),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[],
        now=NOW,
    )
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    assert row["fpc_n"] == 1   # only the explicit True counts
    assert row["fpc_rate"] == 1.0


# ---------------------------------------------------------------------------
# Test 4: gates_caught counts FAIL verdicts
# ---------------------------------------------------------------------------

def test_gates_caught_counts_fail_verdicts(tmp_path):
    recs = [
        {"ts": "2026-06-09T10:00:00Z", "issue": 10, "verdict": "FAIL", "eval_results": {}},
    ]
    kpis = Q.compute_kpis(
        metrics_path=_absent(tmp_path, "metrics.jsonl"),
        prove_log_path=_prove_log(tmp_path, recs),
        overrides_paths=[],
        now=NOW,
    )
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    assert row["gates_caught"] == 1


# ---------------------------------------------------------------------------
# Test 5: gates_caught counts eval_results failures
# ---------------------------------------------------------------------------

def test_gates_caught_counts_eval_failures(tmp_path):
    recs = [
        {
            "ts": "2026-06-09T10:00:00Z",
            "issue": 11,
            "verdict": "PASS",  # verdict is PASS but eval failed
            "eval_results": {"E01": "fail", "E04": "pass"},
        },
    ]
    kpis = Q.compute_kpis(
        metrics_path=_absent(tmp_path, "metrics.jsonl"),
        prove_log_path=_prove_log(tmp_path, recs),
        overrides_paths=[],
        now=NOW,
    )
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    assert row["gates_caught"] == 1


# ---------------------------------------------------------------------------
# Test 6: gates_caught counts overrides with non-zero gate_exit
# ---------------------------------------------------------------------------

def test_gates_caught_counts_overrides_with_nonzero_exit(tmp_path):
    recs_pass = [
        {"ts": "2026-06-09T10:00:00Z", "issue": 20, "verdict": "PASS", "eval_results": {}},
    ]
    recs_override = [
        {"ts": "2026-06-09T11:00:00Z", "issue": 21, "gate_exit": 2, "gate_reason": "blocker"},
        {"ts": "2026-06-09T12:00:00Z", "issue": 22, "gate_exit": 0, "gate_reason": "ok"},
    ]
    kpis = Q.compute_kpis(
        metrics_path=_absent(tmp_path, "metrics.jsonl"),
        prove_log_path=_prove_log(tmp_path, recs_pass),
        overrides_paths=[_overrides(tmp_path, recs_override)],
        now=NOW,
    )
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    # prove_log PASS with no eval failures = 0 gates from prove-log
    # override gate_exit=2 → 1 gate; gate_exit=0 → 0 gates
    assert row["gates_caught"] == 1


# ---------------------------------------------------------------------------
# Test 7: format_kpi_section markdown structure
# ---------------------------------------------------------------------------

def test_format_kpi_section_markdown_structure(tmp_path):
    recs = [{"issue": 1, "date": "2026-06-09", "first_pass_correct": True}]
    kpis = Q.compute_kpis(
        metrics_path=_metrics(tmp_path, recs),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[],
        now=NOW,
    )
    md = Q.format_kpi_section(kpis)
    assert "## Quality KPIs" in md
    assert "| Week |" in md
    assert "First-pass rate" in md
    assert "Gates caught" in md
    assert "**Total**" in md


# ---------------------------------------------------------------------------
# Test 8: format_kpi_section renders (not empty) even on all-zero data
# ---------------------------------------------------------------------------

def test_format_kpi_section_not_empty_on_all_zero_data(tmp_path):
    kpis = Q.compute_kpis(
        metrics_path=_absent(tmp_path, "metrics.jsonl"),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[],
        now=NOW,
    )
    md = Q.format_kpi_section(kpis)
    # All-zero data should still render the table (not return empty string)
    assert md != ""
    assert "n/a" in md  # all rates are n/a when no fpc data


# ---------------------------------------------------------------------------
# Test 9: week bucketing — record in week N does not bleed into week N+1
# ---------------------------------------------------------------------------

def test_week_bucketing_correct(tmp_path):
    # 2026-06-01 is W23, 2026-06-08 is W24 (starts on Monday 2026-06-08)
    recs = [
        {"issue": 1, "date": "2026-06-01", "first_pass_correct": True},   # W23
        {"issue": 2, "date": "2026-06-08", "first_pass_correct": False},  # W24
    ]
    kpis = Q.compute_kpis(
        metrics_path=_metrics(tmp_path, recs),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[],
        now=NOW,
    )
    row_23 = next(r for r in kpis["rows"] if r["week"] == WEEK_23)
    row_24 = next(r for r in kpis["rows"] if r["week"] == WEEK_24)

    assert row_23["fpc_n"] == 1
    assert row_23["fpc_rate"] == 1.0   # 1 true in W23
    assert row_24["fpc_n"] == 1
    assert row_24["fpc_rate"] == 0.0   # 1 false in W24 (no bleed from W23)


# ---------------------------------------------------------------------------
# Test 10: compute_kpis returns exactly `weeks` rows
# ---------------------------------------------------------------------------

def test_compute_kpis_week_count(tmp_path):
    for n in (1, 4, 8, 12):
        kpis = Q.compute_kpis(
            metrics_path=_absent(tmp_path, "metrics.jsonl"),
            prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
            overrides_paths=[],
            weeks=n,
            now=NOW,
        )
        assert len(kpis["rows"]) == n, f"expected {n} rows, got {len(kpis['rows'])}"


# ---------------------------------------------------------------------------
# Bonus: BLOCKED verdict also counts as gate-caught
# ---------------------------------------------------------------------------

def test_gates_caught_counts_blocked_verdicts(tmp_path):
    recs = [
        {"ts": "2026-06-09T10:00:00Z", "issue": 30, "verdict": "BLOCKED", "eval_results": {}},
    ]
    kpis = Q.compute_kpis(
        metrics_path=_absent(tmp_path, "metrics.jsonl"),
        prove_log_path=_prove_log(tmp_path, recs),
        overrides_paths=[],
        now=NOW,
    )
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    assert row["gates_caught"] == 1


# ---------------------------------------------------------------------------
# Bonus: multiple overrides paths (aggregated)
# ---------------------------------------------------------------------------

def test_multiple_overrides_paths_aggregated(tmp_path):
    ov1 = tmp_path / "ov1.jsonl"
    ov2 = tmp_path / "ov2.jsonl"
    _write_jsonl(ov1, [{"ts": "2026-06-09T10:00:00Z", "gate_exit": 1}])
    _write_jsonl(ov2, [{"ts": "2026-06-09T11:00:00Z", "gate_exit": 2}])
    kpis = Q.compute_kpis(
        metrics_path=_absent(tmp_path, "metrics.jsonl"),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[ov1, ov2],
        now=NOW,
    )
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    assert row["gates_caught"] == 2


# ---------------------------------------------------------------------------
# Bonus: totals aggregate across all weeks
# ---------------------------------------------------------------------------

def test_totals_aggregate_across_all_weeks(tmp_path):
    recs = [
        {"issue": 1, "date": "2026-06-01", "first_pass_correct": True},   # W23
        {"issue": 2, "date": "2026-06-09", "first_pass_correct": False},  # W24
    ]
    kpis = Q.compute_kpis(
        metrics_path=_metrics(tmp_path, recs),
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[],
        now=NOW,
    )
    assert kpis["totals"]["fpc_n"] == 2
    assert abs(kpis["totals"]["fpc_rate"] - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# Bonus: malformed JSONL lines are skipped gracefully
# ---------------------------------------------------------------------------

def test_malformed_jsonl_skipped_gracefully(tmp_path):
    p = tmp_path / "metrics.jsonl"
    p.write_text(
        '{"issue": 1, "date": "2026-06-09", "first_pass_correct": true}\n'
        "not-json-at-all\n"
        '{"issue": 2, "date": "2026-06-09", "first_pass_correct": false}\n',
        encoding="utf-8",
    )
    kpis = Q.compute_kpis(
        metrics_path=p,
        prove_log_path=_absent(tmp_path, "prove-log.jsonl"),
        overrides_paths=[],
        now=NOW,
    )
    row = next(r for r in kpis["rows"] if r["week"] == WEEK_24)
    assert row["fpc_n"] == 2  # malformed line skipped, 2 valid records parsed
