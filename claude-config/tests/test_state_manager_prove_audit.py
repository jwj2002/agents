"""Tests for state_manager — per-AC audit + prove-log.jsonl writer (#1612).

Run from the repo root:

    python3 -m pytest claude-config/tests/ -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from state_manager import (  # type: ignore[import-not-found]
    count_acceptance_bullets,
    record_prove_audit,
    validate_ac_audit,
    validate_runtime_smoke,
)


# ── validate_ac_audit ────────────────────────────────────────────────────────


def test_all_implemented_passes():
    """All ACs implemented → no downgrade."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py:10"},
            {"ac": "AC 2", "status": "implemented", "evidence": "src/b.py:20"},
        ]
    )
    assert audit["valid"] is True
    assert audit["downgrade_to"] is None
    assert audit["missing"] == []


def test_five_acs_four_implemented_one_missing_fails():
    """AC test from issue #1612: 5 ACs, PR implements 4 → FAIL with the
    missing AC named."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1: foo", "status": "implemented", "evidence": "src/a.py:1"},
            {"ac": "AC 2: bar", "status": "implemented", "evidence": "src/b.py:2"},
            {"ac": "AC 3: baz", "status": "implemented", "evidence": "src/c.py:3"},
            {"ac": "AC 4: qux", "status": "implemented", "evidence": "src/d.py:4"},
            {"ac": "AC 5: quux", "status": "missing", "evidence": ""},
        ]
    )
    assert audit["downgrade_to"] == "FAIL"
    assert len(audit["missing"]) == 1
    entry = audit["missing"][0]
    assert "AC 5: quux" in entry["ac"]
    assert entry["status"] == "missing"


def test_partial_status_forbids_pass():
    """AC marked `partial` → FAIL."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "tests/test_a.py"},
            {"ac": "AC 2", "status": "partial", "evidence": "only read path; write path missing"},
        ]
    )
    assert audit["downgrade_to"] == "FAIL"
    assert len(audit["missing"]) == 1
    assert audit["missing"][0]["status"] == "partial"


def test_deferred_with_issue_number_is_accepted():
    """AC test from issue #1612: 'deferred' AC with follow-up # → accepted."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py:1"},
            {"ac": "AC 2", "status": "deferred", "evidence": "deferred to #1620"},
            {"ac": "AC 3", "status": "deferred", "evidence": "Deferred to GH-1621 per Discuss"},
        ]
    )
    assert audit["downgrade_to"] is None
    assert audit["missing"] == []


def test_deferred_without_issue_number_is_treated_as_missing():
    """AC test from issue #1612: 'deferred' AC without # → treated as missing."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py:1"},
            {"ac": "AC 2", "status": "deferred", "evidence": "deferred to a follow-up"},
        ]
    )
    assert audit["downgrade_to"] == "FAIL"
    assert len(audit["missing"]) == 1
    assert "deferred without follow-up" in audit["missing"][0]["reason"]


def test_deferred_with_empty_evidence_is_missing():
    """Empty evidence on `deferred` is the same as no follow-up — FAIL."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "deferred", "evidence": ""},
        ]
    )
    assert audit["downgrade_to"] == "FAIL"


def test_na_status_is_accepted():
    """`n/a` is acceptable (rare but valid)."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py:1"},
            {"ac": "AC 2", "status": "n/a", "evidence": "test infra only — no runtime path"},
        ]
    )
    assert audit["downgrade_to"] is None


def test_missing_ac_audit_array_is_failure():
    """No ac_audit → cannot verify → FAIL."""
    audit = validate_ac_audit(None)
    assert audit["valid"] is False
    assert audit["downgrade_to"] == "FAIL"


def test_empty_ac_audit_array_is_failure():
    """Empty array → no ACs verified → FAIL."""
    audit = validate_ac_audit([])
    assert audit["valid"] is False
    assert audit["downgrade_to"] == "FAIL"


def test_unknown_status_string_is_failure():
    """Garbage status (e.g. typo) → flagged as invalid."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implmented", "evidence": "src/a.py:1"},
        ]
    )
    assert audit["valid"] is False
    assert audit["downgrade_to"] == "FAIL"


def test_non_dict_entry_is_failure():
    """ac_audit[i] must be a dict; anything else → FAIL."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py:1"},
            "this is a string, not a dict",
        ]
    )
    assert audit["valid"] is False
    assert audit["downgrade_to"] == "FAIL"


# ── validate_runtime_smoke (issue #460) ──────────────────────────────────────


def test_smoke_pass_with_command_and_evidence_ok():
    """status: PASS with both command and evidence → no downgrade."""
    smoke = validate_runtime_smoke(
        {"status": "PASS", "command": "python -m m --help", "evidence": "exit 0"}
    )
    assert smoke["valid"] is True
    assert smoke["downgrade_to"] is None
    assert smoke["missing"] == []


def test_smoke_absent_is_violation():
    """None (absent block) → fail-closed with the re-run message."""
    smoke = validate_runtime_smoke(None)
    assert smoke["valid"] is False
    assert smoke["downgrade_to"] == "FAIL"
    assert "re-run PROVE" in smoke["missing"][0]["reason"]


def test_smoke_fail_is_violation():
    """status: FAIL → blocked."""
    smoke = validate_runtime_smoke(
        {"status": "FAIL", "command": "x", "evidence": "crashed"}
    )
    assert smoke["downgrade_to"] == "FAIL"
    assert "FAIL" in smoke["missing"][0]["reason"]


def test_smoke_pass_without_command_is_violation():
    """status: PASS requires the command that was run."""
    smoke = validate_runtime_smoke(
        {"status": "PASS", "command": "", "evidence": "ran"}
    )
    assert smoke["downgrade_to"] == "FAIL"


def test_smoke_pass_without_evidence_is_violation():
    """status: PASS requires non-empty evidence."""
    smoke = validate_runtime_smoke(
        {"status": "PASS", "command": "x", "evidence": ""}
    )
    assert smoke["downgrade_to"] == "FAIL"


def test_smoke_na_with_evidence_ok():
    """status: n/a with evidence (justification) → no downgrade."""
    smoke = validate_runtime_smoke({"status": "n/a", "evidence": "docs only"})
    assert smoke["downgrade_to"] is None


def test_smoke_na_without_evidence_is_violation():
    """status: n/a still requires a justification in evidence."""
    smoke = validate_runtime_smoke({"status": "n/a", "evidence": ""})
    assert smoke["downgrade_to"] == "FAIL"


def test_smoke_scalar_string_coerced_to_na_ok():
    """#459 backward-compat: a bare string coerces to n/a, no downgrade."""
    smoke = validate_runtime_smoke("n/a (no runnable surface)")
    assert smoke["valid"] is True
    assert smoke["downgrade_to"] is None


def test_smoke_unknown_status_is_violation():
    """Garbage status string → invalid → FAIL."""
    smoke = validate_runtime_smoke({"status": "maybe", "evidence": "x"})
    assert smoke["valid"] is False
    assert smoke["downgrade_to"] == "FAIL"


def test_smoke_non_mapping_non_string_is_violation():
    """A list/int (neither dict nor str nor None) → FAIL."""
    smoke = validate_runtime_smoke([1, 2])
    assert smoke["valid"] is False
    assert smoke["downgrade_to"] == "FAIL"


# ── record_prove_audit ───────────────────────────────────────────────────────


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Isolated project root for each test."""
    return tmp_path


def _read_log(project_dir: Path) -> list[dict]:
    path = project_dir / ".claude" / "memory" / "prove-log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_record_prove_audit_writes_pass_row(project_dir):
    record_prove_audit(
        project_dir,
        issue=1610,
        verdict="PASS",
        ac_audit=[{"ac": "AC 1", "status": "implemented", "evidence": "src/a.py:1"}],
        applicable_evals=["E15"],
        eval_results={"E15": "pass"},
    )
    rows = _read_log(project_dir)
    assert len(rows) == 1
    row = rows[0]
    assert row["issue"] == 1610
    assert row["phase"] == "PROVE"
    assert row["verdict"] == "PASS"
    assert row["ac_audit"] == [
        {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py:1"}
    ]
    assert row["applicable_evals"] == ["E15"]
    assert row["eval_results"] == {"E15": "pass"}
    assert "downgrade_reason" not in row


def test_record_prove_audit_writes_fail_row_with_reason(project_dir):
    record_prove_audit(
        project_dir,
        issue=1610,
        verdict="FAIL",
        ac_audit=[{"ac": "AC 5", "status": "missing", "evidence": ""}],
        downgrade_reason="AC 5: AC #5 marked missing",
    )
    rows = _read_log(project_dir)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "FAIL"
    assert "AC 5" in rows[0]["downgrade_reason"]


def test_record_prove_audit_appends_not_overwrites(project_dir):
    record_prove_audit(project_dir, 1, "PASS", [])
    record_prove_audit(project_dir, 2, "PASS", [])
    record_prove_audit(project_dir, 3, "FAIL", [{"ac": "x", "status": "missing"}])
    rows = _read_log(project_dir)
    assert len(rows) == 3
    assert [r["issue"] for r in rows] == [1, 2, 3]


def test_record_prove_audit_creates_memory_dir(project_dir):
    """First call creates .claude/memory/ if absent."""
    assert not (project_dir / ".claude" / "memory").exists()
    record_prove_audit(project_dir, 1, "PASS", [])
    assert (project_dir / ".claude" / "memory" / "prove-log.jsonl").exists()


def test_record_prove_audit_handles_none_ac_audit(project_dir):
    """ac_audit=None → recorded as []."""
    record_prove_audit(project_dir, 1, "FAIL", None, downgrade_reason="no ac_audit array")
    rows = _read_log(project_dir)
    assert rows[0]["ac_audit"] == []


def test_record_prove_audit_omits_optional_fields_when_absent(project_dir):
    """applicable_evals / eval_results / downgrade_reason are optional."""
    record_prove_audit(project_dir, 1, "PASS", [{"ac": "x", "status": "implemented"}])
    rows = _read_log(project_dir)
    assert "applicable_evals" not in rows[0]
    assert "eval_results" not in rows[0]
    assert "downgrade_reason" not in rows[0]


# ── count_acceptance_bullets ────────────────────────────────────────────────


def test_count_acceptance_bullets_under_h2():
    body = """\
## What

Some prose.

## Acceptance

- [ ] First AC
- [ ] Second AC
- [x] Third AC (already checked)

## Out of scope

- [ ] Not an AC bullet
"""
    assert count_acceptance_bullets(body) == 3


def test_count_acceptance_bullets_under_h3():
    body = "### Acceptance criteria\n\n- [ ] One\n- [ ] Two\n"
    assert count_acceptance_bullets(body) == 2


def test_count_acceptance_bullets_zero_when_no_section():
    body = "## Background\n\nNo acceptance criteria here."
    assert count_acceptance_bullets(body) == 0


def test_count_acceptance_bullets_zero_on_empty_input():
    assert count_acceptance_bullets("") == 0
    assert count_acceptance_bullets(None) == 0  # type: ignore[arg-type]


def test_count_acceptance_bullets_stops_at_next_heading():
    """Bullets after a subsequent heading should not be counted."""
    body = """\
## Acceptance
- [ ] AC 1
- [ ] AC 2
## Out of scope
- [ ] Not an AC
"""
    assert count_acceptance_bullets(body) == 2


# ── coverage gate (expected_ac_count) ───────────────────────────────────────


def test_emit_fewer_than_expected_is_failure():
    """Codex R1 bypass fix: 5 expected ACs, only 4 emitted (all
    implemented) → FAIL because AC #5 is silently omitted."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py"},
            {"ac": "AC 2", "status": "implemented", "evidence": "src/b.py"},
            {"ac": "AC 3", "status": "implemented", "evidence": "src/c.py"},
            {"ac": "AC 4", "status": "implemented", "evidence": "src/d.py"},
        ],
        expected_ac_count=5,
    )
    assert audit["downgrade_to"] == "FAIL"
    assert any("AC #5" in m["reason"] for m in audit["missing"])


def test_emit_equal_to_expected_is_pass():
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py"},
            {"ac": "AC 2", "status": "implemented", "evidence": "src/b.py"},
        ],
        expected_ac_count=2,
    )
    assert audit["downgrade_to"] is None


def test_emit_more_than_expected_is_pass():
    """Tolerate over-counting; under-counting is the load-bearing case."""
    audit = validate_ac_audit(
        [
            {"ac": "AC 1", "status": "implemented", "evidence": "src/a.py"},
            {"ac": "AC 2", "status": "implemented", "evidence": "src/b.py"},
            {"ac": "AC 3 (bonus)", "status": "implemented", "evidence": "src/c.py"},
        ],
        expected_ac_count=2,
    )
    assert audit["downgrade_to"] is None


def test_expected_ac_count_none_skips_coverage_check():
    """Backward compat: callers that don't pass the count keep the
    emit-only validation behavior (unit tests, issues with no parseable
    AC section)."""
    audit = validate_ac_audit(
        [{"ac": "AC 1", "status": "implemented", "evidence": "src/a.py"}],
        expected_ac_count=None,
    )
    assert audit["downgrade_to"] is None
