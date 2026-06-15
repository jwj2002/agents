"""Tests for decision-provenance fields added in issue #217.

Covers spec §9 ACs 1-7:
  AC1  Round-trip: fields present/absent as expected (test_roundtrip_present_absent)
  AC2  Validation: invalid guards/categories dropped, no raise (test_validation_drop_invalid)
  AC3  Backward-compat: old records survive unchanged (test_backward_compatibility)
  AC4b Collision dedup: field retained when base (newest) lacks it (test_dedup_collision)
  AC6a Write→read per-host re-tier rate via agent_metrics() (test_retier_rate_write_read)
  AC6b guards_fired variance: enum task vs no-enum task (test_guards_fired_variance)
  AC7  Size budget: representative record ≤ 4096 bytes (test_size_budget)

Run from the repo root:

    python3 -m pytest claude-config/tests/test_state_manager_decision_fields.py -v

The conftest.py in this directory adds hooks/ to sys.path automatically.
mcp-server/tools/ is added here so the agent_metrics import does not pollute
other test modules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add mcp-server/ to sys.path so `tools.agent_metrics` can be imported with its
# relative `from .vault_common import ...` intact. Scoped to this module only;
# conftest.py already adds hooks/.
_MCP_SERVER = Path(__file__).resolve().parent.parent.parent / "mcp-server"
if str(_MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(_MCP_SERVER))

from state_manager import record_metrics  # type: ignore[import-not-found]  # noqa: E402
from aggregate_metrics_to_global import aggregate  # type: ignore[import-not-found]  # noqa: E402
from tools.agent_metrics import agent_metrics  # type: ignore[import-not-found]  # noqa: E402


# ── Fixtures & helpers ───────────────────────────────────────────────────────


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Isolated project root for each test."""
    return tmp_path


def _read_metrics(project_dir: Path) -> list[dict]:
    """Read all records from metrics.jsonl in *project_dir*."""
    path = project_dir / ".claude" / "memory" / "metrics.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_global_metrics(global_dir: Path) -> list[dict]:
    """Read all records from the global metrics.jsonl."""
    path = global_dir / "metrics.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_raw_metrics(project_dir: Path, records: list[dict]) -> None:
    """Write records directly to metrics.jsonl (bypasses record_metrics validation)."""
    target = project_dir / ".claude" / "memory" / "metrics.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


# ── Test 1: Round-trip present/absent (AC1) ──────────────────────────────────


def test_roundtrip_present_absent(project_dir):
    """Fields are written when supplied and absent when not supplied (AC1)."""
    # Call with all three decision fields.
    record_metrics(
        project_dir,
        issue=1,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["MAP", "PATCH", "PROVE"],
        tier_corrected_to="COMPLEX",
        guards_fired=["VERIFICATION_GAP"],
        codex_overturned={"state": "overturned", "category": "auth"},
    )
    rows = _read_metrics(project_dir)
    assert len(rows) == 1
    row = rows[0]
    assert row["tier_corrected_to"] == "COMPLEX"
    assert row["guards_fired"] == ["VERIFICATION_GAP"]
    assert row["codex_overturned"] == {"state": "overturned", "category": "auth"}

    # Call without decision fields — none of the three keys should appear.
    record_metrics(
        project_dir,
        issue=2,
        status="PASS",
        complexity="TRIVIAL",
        stack="backend",
        agents_run=["PATCH", "PROVE"],
    )
    rows = _read_metrics(project_dir)
    second = rows[1]
    assert "tier_corrected_to" not in second
    assert "guards_fired" not in second
    assert "codex_overturned" not in second


# ── Test 2: Validation — drop invalid, no raise (AC2) ───────────────────────


def test_validation_drop_invalid(project_dir):
    """Invalid guard names are dropped; invalid codex dicts are omitted; no raise (AC2)."""
    # Mixed valid + invalid guard name: only valid name should survive.
    record_metrics(
        project_dir,
        issue=10,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["PATCH"],
        guards_fired=["ENUM_VALUE", "NOT_A_GUARD"],
    )
    rows = _read_metrics(project_dir)
    row = rows[-1]
    assert row["guards_fired"] == ["ENUM_VALUE"]

    # Invalid category: whole dict dropped.
    record_metrics(
        project_dir,
        issue=11,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["PATCH"],
        codex_overturned={"state": "overturned", "category": "BADCAT"},
    )
    rows = _read_metrics(project_dir)
    row = rows[-1]
    assert "codex_overturned" not in row

    # Invalid state: whole dict dropped.
    record_metrics(
        project_dir,
        issue=12,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["PATCH"],
        codex_overturned={"state": "BADSTATE", "category": "auth"},
    )
    rows = _read_metrics(project_dir)
    row = rows[-1]
    assert "codex_overturned" not in row

    # Ensure none of the three calls raised.
    # (Reaching this line proves no exception was raised above.)


# ── Test 3: Backward-compatibility (AC3) ────────────────────────────────────


def test_backward_compatibility(project_dir, tmp_path):
    """Pre-change records survive unchanged; new records carry decision fields (AC3)."""
    source_dir = project_dir / ".claude" / "memory"
    global_dir = tmp_path / "global"

    # Write a legacy record (no decision fields) via raw write to simulate a
    # pre-change record that would have been written before issue #217.
    _write_raw_metrics(
        project_dir,
        [
            {
                "issue": 100,
                "date": "2026-01-01",
                "recorded_at": "2026-01-01T10:00:00.000000Z",
                "status": "PASS",
                "complexity": "TRIVIAL",
                "stack": "backend",
                "agents_run": ["PATCH"],
                "project": "agents",
            }
        ],
    )

    # Write a record with decision fields for a different issue.
    record_metrics(
        project_dir,
        issue=200,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["MAP", "PATCH", "PROVE"],
        tier_corrected_to="COMPLEX",
        guards_fired=["ENUM_VALUE"],
        codex_overturned={"state": "confirmed", "category": "migration"},
    )

    aggregate("metrics", [source_dir], global_dir)
    global_rows = _read_global_metrics(global_dir)

    issue100 = next(r for r in global_rows if r["issue"] == 100)
    issue200 = next(r for r in global_rows if r["issue"] == 200)

    # Old record must not gain spurious new keys.
    assert "tier_corrected_to" not in issue100
    assert "guards_fired" not in issue100
    assert "codex_overturned" not in issue100

    # New record's decision fields must survive the rollup.
    assert issue200["tier_corrected_to"] == "COMPLEX"
    assert issue200["guards_fired"] == ["ENUM_VALUE"]
    assert issue200["codex_overturned"] == {
        "state": "confirmed",
        "category": "migration",
    }


# ── Test 4: Field-level dedup collision (AC4b, TAUTOLOGY GUARD) ─────────────


def test_dedup_collision(project_dir, tmp_path):
    """Field retained when newest-recorded_at winner for a key lacks it (AC4b).

    This test is intentionally written to FAIL against the pre-fix
    `seen[key] = record` last-wins code in aggregate_metrics_to_global.py.
    It verifies the field-level carry-forward added in issue #217.
    """
    source_dir = project_dir / ".claude" / "memory"
    global_dir = tmp_path / "global"

    # Record A: older timestamp, HAS tier_corrected_to.
    _write_raw_metrics(
        project_dir,
        [
            {
                "issue": 5,
                "date": "2026-01-01",
                "recorded_at": "2026-01-01T10:00:00.000000Z",
                "status": "PASS",
                "complexity": "SIMPLE",
                "stack": "backend",
                "agents_run": ["PATCH"],
                "project": "agents",
                "tier_corrected_to": "COMPLEX",
            },
            # Record B: newer timestamp (higher recorded_at), SAME key, NO tier_corrected_to.
            # Under old last-wins code, B overwrites A entirely, losing tier_corrected_to.
            {
                "issue": 5,
                "date": "2026-01-01",
                "recorded_at": "2026-01-01T11:00:00.000000Z",
                "status": "PASS",
                "complexity": "SIMPLE",
                "stack": "backend",
                "agents_run": ["PATCH", "PROVE"],
                "project": "agents",
            },
        ],
    )

    aggregate("metrics", [source_dir], global_dir)
    global_rows = _read_global_metrics(global_dir)

    # Only one record should exist for (issue=5, date=2026-01-01, project=agents).
    issue5_rows = [r for r in global_rows if r["issue"] == 5]
    assert len(issue5_rows) == 1

    # The aggregated record MUST carry tier_corrected_to recovered from record A.
    assert "tier_corrected_to" in issue5_rows[0], (
        "tier_corrected_to was lost — field-level carry-forward not working. "
        "This test is designed to FAIL against the pre-fix last-wins code."
    )
    assert issue5_rows[0]["tier_corrected_to"] == "COMPLEX"


# ── Test 5: Write→read per-host re-tier rate (AC6a) ─────────────────────────


def test_retier_rate_write_read(project_dir, tmp_path):
    """tier_corrected_to flows from write through aggregate to agent_metrics() (AC6a)."""
    source_dir = project_dir / ".claude" / "memory"
    # Global dir is what agent_metrics reads — we point project= at tmp_path/global.
    global_dir = tmp_path / "global_mem" / ".claude" / "memory"

    # Two SIMPLE records: one re-tiered, one not.
    record_metrics(
        project_dir,
        issue=301,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["PATCH"],
        tier_corrected_to="COMPLEX",  # re-tiered
    )
    record_metrics(
        project_dir,
        issue=302,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["PATCH"],
        # no re-tier
    )
    # One TRIVIAL record, no re-tier.
    record_metrics(
        project_dir,
        issue=303,
        status="PASS",
        complexity="TRIVIAL",
        stack="backend",
        agents_run=["PATCH"],
    )

    aggregate("metrics", [source_dir], global_dir)

    result = agent_metrics(period="all", project=str(tmp_path / "global_mem"))

    rtr = result["per_host_re_tier_rate"]
    assert rtr["SIMPLE"]["retier_count"] == 1
    assert rtr["SIMPLE"]["total"] == 2
    assert rtr["SIMPLE"]["rate"] == 0.5
    assert rtr["TRIVIAL"]["retier_count"] == 0


# ── Test 6: guards_fired variance (AC6b) ────────────────────────────────────


def test_guards_fired_variance(project_dir):
    """Enum task includes ENUM_VALUE guard; non-enum backend task omits guards (AC6b)."""
    # Enum-touching issue: guards should include ENUM_VALUE.
    record_metrics(
        project_dir,
        issue=401,
        status="PASS",
        complexity="FULLSTACK",
        stack="fullstack",
        agents_run=["MAP", "PATCH", "PROVE"],
        guards_fired=["ENUM_VALUE", "VERIFICATION_GAP"],
    )
    rows = _read_metrics(project_dir)
    enum_row = rows[-1]
    assert "guards_fired" in enum_row
    assert "ENUM_VALUE" in enum_row["guards_fired"]

    # Non-enum backend issue: no guards_fired argument at all.
    record_metrics(
        project_dir,
        issue=402,
        status="PASS",
        complexity="SIMPLE",
        stack="backend",
        agents_run=["PATCH"],
    )
    rows = _read_metrics(project_dir)
    no_enum_row = rows[-1]
    assert "guards_fired" not in no_enum_row


# ── Test 7: Size budget (AC7) ────────────────────────────────────────────────


def test_size_budget():
    """Representative record with all three fields fits within 4096 bytes (AC7)."""
    rec = {
        "issue": 9999,
        "date": "2026-06-04",
        "recorded_at": "2026-06-04T12:00:00.000000Z",
        "status": "PASS",
        "complexity": "COMPLEX",
        "stack": "fullstack",
        "agents_run": ["MAP", "PLAN", "CONTRACT", "PATCH", "PROVE"],
        "duration_seconds": 3600,
        "tier_corrected_to": "FULLSTACK",
        "guards_fired": ["VERIFICATION_GAP", "ENUM_VALUE", "COMPONENT_API"],
        "codex_overturned": {"state": "overturned", "category": "enum_contract"},
    }
    size = len(json.dumps(rec).encode("utf-8"))
    assert size <= 4096, f"Record size {size} exceeds 4096-byte PIPE_BUF budget"


# ── Tests 8–12: recall= field round-trip and validation (issue #456) ─────────


def test_recall_present_when_supplied(project_dir):
    """recall= field is written when valid dict is supplied."""
    record_metrics(
        project_dir,
        456,
        "PASS",
        "MODERATE",
        "backend",
        ["MAP-PLAN", "PATCH", "PROVE"],
        recall={"fired": True, "n": 2, "facts": ["fact_a", "fact_b"], "flag": "on"},
    )
    row = _read_metrics(project_dir)[0]
    assert "recall" in row
    assert row["recall"]["fired"] is True
    assert row["recall"]["n"] == 2
    assert row["recall"]["facts"] == ["fact_a", "fact_b"]
    assert row["recall"]["flag"] == "on"


def test_recall_absent_when_not_supplied(project_dir):
    """recall= field omitted when not passed (compact PASS records)."""
    record_metrics(
        project_dir,
        100,
        "PASS",
        "SIMPLE",
        "backend",
        ["MAP-PLAN", "PATCH", "PROVE"],
    )
    row = _read_metrics(project_dir)[0]
    assert "recall" not in row


def test_recall_dropped_on_invalid_flag(project_dir):
    """recall dict with unknown flag is dropped with warning, no raise."""
    record_metrics(
        project_dir,
        457,
        "PASS",
        "SIMPLE",
        "backend",
        [],
        recall={"fired": True, "n": 1, "facts": ["x"], "flag": "maybe"},
    )
    row = _read_metrics(project_dir)[0]
    assert "recall" not in row


def test_recall_dropped_on_non_bool_fired(project_dir):
    """recall dict with non-bool fired is dropped."""
    record_metrics(
        project_dir,
        458,
        "PASS",
        "SIMPLE",
        "backend",
        [],
        recall={"fired": "yes", "n": 1, "facts": [], "flag": "on"},
    )
    row = _read_metrics(project_dir)[0]
    assert "recall" not in row


def test_recall_fired_false_with_empty_facts(project_dir):
    """recall fired=False with n=0 and empty facts is valid."""
    record_metrics(
        project_dir,
        459,
        "PASS",
        "SIMPLE",
        "backend",
        [],
        recall={"fired": False, "n": 0, "facts": [], "flag": "on"},
    )
    row = _read_metrics(project_dir)[0]
    assert row["recall"]["fired"] is False
    assert row["recall"]["n"] == 0
    assert row["recall"]["facts"] == []
