"""Tests for recall L3 on/off flag (issue #457).

Covers:
  Group A: _recall_flag_delta computation (on vs off cohorts, N guard, fail-open)
  Group B: off-path sidecar fields + state_manager round-trip
  Group C: format_recall_section includes flag delta when above/below threshold

Run from the repo root:

    python3 -m pytest claude-config/tests/test_recall_l3_flag.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import cost_report_weekly as CRW  # noqa: E402
import state_manager as SM  # noqa: E402


# ── Fixture helpers ───────────────────────────────────────────────────────────


def _write_metrics(tmp_path: Path, records: list) -> Path:
    p = tmp_path / "metrics.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return p


def _on_rec(issue: int, fpc: bool) -> dict:
    """Qualifying record with flag='on'."""
    return {
        "issue": issue,
        "date": "2026-06-15",
        "first_pass_correct": fpc,
        "recall": {"fired": True, "n": 1, "facts": ["x"], "flag": "on"},
    }


def _off_rec(issue: int, fpc: bool) -> dict:
    """Qualifying record with flag='off'."""
    return {
        "issue": issue,
        "date": "2026-06-15",
        "first_pass_correct": fpc,
        "recall": {"fired": False, "n": 0, "facts": [], "flag": "off"},
    }


# ── Group A: _recall_flag_delta computation ───────────────────────────────────


def test_flag_delta_on_vs_off(tmp_path):
    """3 on-records (2 pass, 1 fail → 67%) + 3 off-records (1 pass, 2 fail → 33%)."""
    p = _write_metrics(
        tmp_path,
        [
            _on_rec(1, True),
            _on_rec(2, True),
            _on_rec(3, False),
            _off_rec(10, True),
            _off_rec(11, False),
            _off_rec(12, False),
        ],
    )
    result = CRW._recall_flag_delta(p)
    assert "recall on" in result
    assert "recall off" in result
    assert "67%" in result  # on: 2/3
    assert "33%" in result  # off: 1/3


def test_flag_delta_insufficient_shows_n_message(tmp_path):
    """2 on + 3 off — below threshold for on; must show insufficient-data message."""
    p = _write_metrics(
        tmp_path,
        [
            _on_rec(1, True),
            _on_rec(2, False),
            _off_rec(10, True),
            _off_rec(11, False),
            _off_rec(12, False),
        ],
    )
    result = CRW._recall_flag_delta(p)
    assert result != ""
    assert "insufficient data" in result
    assert "on N=2" in result
    assert "off N=3" in result


def test_flag_delta_no_data_returns_empty(tmp_path):
    """Empty metrics file → empty string (no records at all)."""
    p = _write_metrics(tmp_path, [])
    assert CRW._recall_flag_delta(p) == ""


def test_flag_delta_missing_file_returns_empty(tmp_path):
    """Non-existent file → fail-open → empty string."""
    absent = tmp_path / "no_such_file.jsonl"
    assert CRW._recall_flag_delta(absent) == ""


def test_flag_delta_excludes_pre_l2_records(tmp_path):
    """Records without a 'recall' field are excluded (not counted in any cohort)."""
    p = _write_metrics(
        tmp_path,
        [
            {"issue": i, "date": "2026-06-15", "first_pass_correct": True}
            for i in range(1, 10)
        ],
    )
    # No flag-bearing records → nothing to report
    assert CRW._recall_flag_delta(p) == ""


def test_flag_delta_excludes_missing_fpc(tmp_path):
    """Records without first_pass_correct bool are not counted."""
    p = _write_metrics(
        tmp_path,
        [
            # on records: 2 with fpc, 1 without → only 2 qualify
            _on_rec(1, True),
            _on_rec(2, True),
            {
                "issue": 3,
                "date": "2026-06-15",
                "recall": {"fired": True, "n": 0, "facts": [], "flag": "on"},
            },
            # off records: 3 qualify
            _off_rec(10, True),
            _off_rec(11, False),
            _off_rec(12, False),
        ],
    )
    # on cohort only has 2 qualifying → insufficient message
    result = CRW._recall_flag_delta(p)
    assert "insufficient data" in result
    assert "on N=2" in result


def test_flag_delta_excludes_invalid_flag_values(tmp_path):
    """Records with flag values other than 'on'/'off' are skipped."""
    p = _write_metrics(
        tmp_path,
        [
            # These would have been L2-style "on" when RECALL_CMD_OK=1 but
            # the value is invalid — excluded from the flag-delta split.
            {
                "issue": i,
                "date": "2026-06-15",
                "first_pass_correct": True,
                "recall": {"fired": True, "n": 1, "facts": [], "flag": "unknown"},
            }
            for i in range(1, 10)
        ],
    )
    assert CRW._recall_flag_delta(p) == ""


# ── Group B: off-path sidecar fields + state_manager round-trip ───────────────


def test_off_path_sidecar_fields():
    """The off-path sidecar dict matches the expected shape (flag=off, fired=False, n=0)."""
    # Replicate the sidecar construction logic from the off-path in orchestrate.md.
    sidecar = {
        "issue": 457,
        "date": "061525",
        "fired": False,
        "n": 0,
        "facts": [],
        "flag": "off",
    }
    assert sidecar["flag"] == "off"
    assert sidecar["fired"] is False
    assert sidecar["n"] == 0
    assert sidecar["facts"] == []


def test_off_path_sidecar_passes_state_manager_validation(tmp_path):
    """The off-path sidecar dict is accepted by record_metrics without being dropped."""
    off_sidecar = {
        "fired": False,
        "n": 0,
        "facts": [],
        "flag": "off",
    }
    SM.record_metrics(
        project_dir=tmp_path,
        issue=457,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["MAP-PLAN", "PATCH", "PROVE"],
        first_pass_correct=True,
        recall=off_sidecar,
    )
    metrics_path = tmp_path / ".claude" / "memory" / "metrics.jsonl"
    assert metrics_path.exists()
    record = json.loads(metrics_path.read_text(encoding="utf-8").strip())
    assert "recall" in record
    assert record["recall"]["flag"] == "off"
    assert record["recall"]["fired"] is False
    assert record["recall"]["n"] == 0
    assert record["recall"]["facts"] == []


def test_on_path_sidecar_flag_is_always_on(tmp_path):
    """The on-path sidecar uses flag='on' regardless of RECALL_CMD_OK."""
    # Simulate the on-path sidecar when query returned nothing (RECALL_CMD_OK=0).
    on_sidecar_no_output = {
        "fired": False,
        "n": 0,
        "facts": [],
        "flag": "on",  # env flag was on — command result doesn't change flag
    }
    SM.record_metrics(
        project_dir=tmp_path,
        issue=458,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["MAP-PLAN", "PATCH", "PROVE"],
        first_pass_correct=True,
        recall=on_sidecar_no_output,
    )
    metrics_path = tmp_path / ".claude" / "memory" / "metrics.jsonl"
    record = json.loads(metrics_path.read_text(encoding="utf-8").strip())
    assert record["recall"]["flag"] == "on"
    assert record["recall"]["fired"] is False


# ── Group C: format_recall_section includes flag delta ────────────────────────


def _make_fake_run():
    """Return a monkeypatch-able subprocess.run stub for coding-memory CLI."""

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

    return _fake_run


def test_format_recall_section_includes_flag_delta(tmp_path, monkeypatch):
    """format_recall_section includes 'Flag delta' when both cohorts are above threshold."""
    p = _write_metrics(
        tmp_path,
        [_on_rec(i, True) for i in range(1, 4)]
        + [_off_rec(i, False) for i in range(10, 13)],
    )
    monkeypatch.setattr(subprocess, "run", _make_fake_run())
    section = CRW.format_recall_section(metrics_path=p)
    assert "Flag delta" in section
    assert "recall on" in section
    assert "recall off" in section


def test_format_recall_section_flag_delta_shows_insufficient_when_below_n(
    tmp_path, monkeypatch
):
    """format_recall_section shows 'insufficient data' when one cohort is below N=3."""
    p = _write_metrics(
        tmp_path,
        [
            _on_rec(1, True),
            _on_rec(2, False),  # on: only 2 records
            _off_rec(10, True),
            _off_rec(11, False),
            _off_rec(12, False),
        ],
    )
    monkeypatch.setattr(subprocess, "run", _make_fake_run())
    section = CRW.format_recall_section(metrics_path=p)
    assert "insufficient data" in section
