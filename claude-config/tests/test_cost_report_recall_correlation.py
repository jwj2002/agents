"""Tests for recall outcome correlation in cost_report_weekly.py (issue #456).

Covers:
  - _recall_correlation split by recall.fired
  - N<3 gate returns ""
  - pre-L2 records (no recall field) excluded from split
  - format_recall_section appends correlation block when metrics_path supplied
  - format_recall_section fail-open when metrics_path doesn't exist

Run from the repo root:

    python3 -m pytest claude-config/tests/test_cost_report_recall_correlation.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cost_report_weekly as CRW  # noqa: E402


# ── Fixture helpers ───────────────────────────────────────────────────────────


def _write_metrics(tmp_path: Path, records: list) -> Path:
    p = tmp_path / "metrics.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_correlation_fired_vs_not(tmp_path):
    """Split by recall.fired; compute first-pass rate per cohort."""
    p = _write_metrics(
        tmp_path,
        [
            # fired=True cohort: 2 pass, 1 fail → 67%
            {
                "issue": 1,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": ["x"], "flag": "on"},
            },
            {
                "issue": 2,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": ["y"], "flag": "on"},
            },
            {
                "issue": 3,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": True, "n": 0, "facts": [], "flag": "on"},
            },
            # fired=False cohort: 1 pass, 2 fail → 33%
            {
                "issue": 4,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
            {
                "issue": 5,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
            {
                "issue": 6,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
        ],
    )
    result = CRW._recall_correlation(p)
    assert "recall fired" in result
    assert "67%" in result  # fired: 2/3 = 67%
    assert "33%" in result  # not fired: 1/3 = 33%


def test_correlation_omitted_when_too_few_fired(tmp_path):
    """Returns '' when fired cohort has fewer than 3 qualifying records."""
    p = _write_metrics(
        tmp_path,
        [
            {
                "issue": 1,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "on"},
            },
            # not_fired cohort has 3, but fired only has 1
            {
                "issue": 2,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
            {
                "issue": 3,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
            {
                "issue": 4,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
        ],
    )
    assert CRW._recall_correlation(p) == ""


def test_correlation_omitted_when_too_few_not_fired(tmp_path):
    """Returns '' when not-fired cohort has fewer than 3 qualifying records."""
    p = _write_metrics(
        tmp_path,
        [
            # fired cohort has 3
            {
                "issue": 1,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "on"},
            },
            {
                "issue": 2,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "on"},
            },
            {
                "issue": 3,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": True, "n": 0, "facts": [], "flag": "on"},
            },
            # not_fired only has 1
            {
                "issue": 4,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
        ],
    )
    assert CRW._recall_correlation(p) == ""


def test_correlation_excludes_no_recall_field(tmp_path):
    """Records without recall field (pre-L2) are excluded from the split."""
    p = _write_metrics(
        tmp_path,
        [
            # 3 pre-L2 records (no recall field) — should NOT be counted
            {"issue": i, "date": "2026-06-09", "first_pass_correct": True}
            for i in range(1, 4)
        ]
        + [
            # Only 1 fired record — below threshold
            {
                "issue": 10,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "on"},
            },
        ],
    )
    # Only 1 fired record, 0 not-fired → below threshold → empty
    assert CRW._recall_correlation(p) == ""


def test_correlation_missing_file_returns_empty(tmp_path):
    """Returns '' when the metrics file doesn't exist."""
    absent = tmp_path / "no_such_file.jsonl"
    assert CRW._recall_correlation(absent) == ""


def test_correlation_excludes_records_missing_fpc(tmp_path):
    """Records without first_pass_correct bool are excluded from rate computation."""
    p = _write_metrics(
        tmp_path,
        [
            # fired cohort: 3 records but one lacks first_pass_correct → only 2 qualify
            {
                "issue": 1,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "on"},
            },
            {
                "issue": 2,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "on"},
            },
            {
                "issue": 3,
                "date": "2026-06-09",  # no first_pass_correct
                "recall": {"fired": True, "n": 0, "facts": [], "flag": "on"},
            },
            # not_fired cohort: 3 qualify
            {
                "issue": 4,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
            {
                "issue": 5,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
            {
                "issue": 6,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            },
        ],
    )
    # fired cohort only has 2 qualifying records → below threshold
    assert CRW._recall_correlation(p) == ""


def test_format_recall_section_includes_correlation_when_metrics_path_supplied(
    tmp_path, monkeypatch
):
    """format_recall_section appends correlation block when metrics_path given."""
    p = _write_metrics(
        tmp_path,
        [
            {
                "issue": i,
                "date": "2026-06-09",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "on"},
            }
            for i in range(1, 4)
        ]
        + [
            {
                "issue": i,
                "date": "2026-06-09",
                "first_pass_correct": False,
                "recall": {"fired": False, "n": 0, "facts": [], "flag": "on"},
            }
            for i in range(10, 13)
        ],
    )

    # Stub out the coding-memory subprocess call to avoid requiring the CLI.
    def _fake_run(cmd, **kwargs):
        class _R:
            returncode = 0
            stdout = json.dumps(
                {
                    "n_total": 5,
                    "n_push": 3,
                    "n_pull": 2,
                    "n_injected_total": 4,
                    "n_returned_total": 5,
                    "p50_latency_ms": 120,
                    "top_facts": [],
                    "days": 7,
                }
            )

        return _R()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    section = CRW.format_recall_section(metrics_path=p)
    assert "Outcome correlation" in section
    assert "recall fired" in section
    assert "recall not fired" in section


def test_format_recall_section_no_crash_when_metrics_absent(tmp_path, monkeypatch):
    """format_recall_section is fail-open when metrics_path doesn't exist."""
    absent = tmp_path / "no_such_file.jsonl"

    def _fake_run(cmd, **kwargs):
        class _R:
            returncode = 0
            stdout = json.dumps(
                {
                    "n_total": 0,
                    "n_push": 0,
                    "n_pull": 0,
                    "n_injected_total": 0,
                    "n_returned_total": 0,
                    "p50_latency_ms": None,
                    "top_facts": [],
                    "days": 7,
                }
            )

        return _R()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    section = CRW.format_recall_section(metrics_path=absent)
    # Must return a string without raising
    assert isinstance(section, str)
    # Correlation subsection absent (not enough data)
    assert "Outcome correlation" not in section


def test_format_recall_section_no_metrics_path_backward_compat(monkeypatch):
    """format_recall_section without metrics_path still works (backward compat)."""

    def _fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = ""

        return _R()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    section = CRW.format_recall_section()
    assert "data unavailable" in section
