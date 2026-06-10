"""Tests for regression-set score.py parse and regression-detection logic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "regression-set"))

import score  # noqa: E402

BASELINE = (
    Path(__file__).resolve().parents[1]
    / "regression-set"
    / "results"
    / "2026-06-09-baseline.md"
)


def test_parse_baseline():
    """Baseline file: 3 cases, correct recall values, zero noise."""
    r = score.parse_results(BASELINE)
    assert r["n_cases"] == 3
    # CRITICAL recall: 0/2 caught → 0.0%
    assert r["critical_recall"] == 0.0
    # WARNING recall: 0/3 caught → 0.0%
    assert r["warning_recall"] == 0.0
    # No false positives in baseline
    assert r["noise_rate"] == 0.0


def test_score_regression_detected(tmp_path):
    """A new run with lower CRITICAL recall than baseline is flagged REGRESSED."""
    baseline_text = (
        "---\nrun_name: base\ndate: 2026-01-01\nconfig_version: abc\n---\n\n"
        "# 001 case-a\n"
        "- critical_expected: 1\n"
        "- critical_caught: 1\n"
        "- warning_expected: 0\n"
        "- warning_caught: 0\n"
        "- false_positives: 0\n"
        "- false_positives_known: 0\n"
        "- reviewer_output_lines: 5\n"
    )
    new_run_text = (
        "---\nrun_name: new\ndate: 2026-02-01\nconfig_version: def\n---\n\n"
        "# 001 case-a\n"
        "- critical_expected: 1\n"
        "- critical_caught: 0\n"
        "- warning_expected: 0\n"
        "- warning_caught: 0\n"
        "- false_positives: 0\n"
        "- false_positives_known: 0\n"
        "- reviewer_output_lines: 2\n"
    )
    baseline_path = tmp_path / "base.md"
    new_run_path = tmp_path / "new.md"
    baseline_path.write_text(baseline_text, encoding="utf-8")
    new_run_path.write_text(new_run_text, encoding="utf-8")

    a = score.parse_results(baseline_path)
    b = score.parse_results(new_run_path)

    regressed = b["critical_recall"] < a["critical_recall"] or (
        b["warning_recall"] < a["warning_recall"] - 0.05
        and b["noise_rate"] >= a["noise_rate"]
    )
    assert regressed is True


def test_score_ok_to_ship(tmp_path):
    """A new run with equal CRITICAL recall and lower noise is OK to ship."""
    baseline_text = (
        "---\nrun_name: base\ndate: 2026-01-01\nconfig_version: abc\n---\n\n"
        "# 001 case-a\n"
        "- critical_expected: 1\n"
        "- critical_caught: 1\n"
        "- warning_expected: 1\n"
        "- warning_caught: 1\n"
        "- false_positives: 2\n"
        "- false_positives_known: 0\n"
        "- reviewer_output_lines: 10\n"
    )
    new_run_text = (
        "---\nrun_name: new\ndate: 2026-02-01\nconfig_version: def\n---\n\n"
        "# 001 case-a\n"
        "- critical_expected: 1\n"
        "- critical_caught: 1\n"
        "- warning_expected: 1\n"
        "- warning_caught: 1\n"
        "- false_positives: 0\n"
        "- false_positives_known: 0\n"
        "- reviewer_output_lines: 8\n"
    )
    baseline_path = tmp_path / "base.md"
    new_run_path = tmp_path / "new.md"
    baseline_path.write_text(baseline_text, encoding="utf-8")
    new_run_path.write_text(new_run_text, encoding="utf-8")

    a = score.parse_results(baseline_path)
    b = score.parse_results(new_run_path)

    regressed = b["critical_recall"] < a["critical_recall"] or (
        b["warning_recall"] < a["warning_recall"] - 0.05
        and b["noise_rate"] >= a["noise_rate"]
    )
    assert regressed is False
