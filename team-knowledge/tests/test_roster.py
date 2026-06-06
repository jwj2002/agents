"""Acceptance tests for issue #238 — team-knowledge skeleton + roster (§5, §6).

Covers the five required cases: roster schema, CODEOWNERS path match, the forgeable-attribution
guard, importer rejection of un-gated provenance, and unknown-sender quarantine.
"""
import sys
from pathlib import Path

import pytest

_TK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_TK / "scripts"))

import roster as R  # noqa: E402

ROSTER_PATH = _TK / "roster.yaml"


@pytest.fixture(scope="module")
def real_roster() -> dict:
    return R.load_roster(ROSTER_PATH)


# 1. roster.yaml schema validation -----------------------------------------------------------
def test_real_roster_is_valid(real_roster):
    assert R.validate_roster(real_roster) == []
    ids = R.roster_dev_ids(real_roster)
    assert {"jason", "server-a", "laptop-wsl", "agent-b"} <= ids
    for dev in real_roster["devs"]:
        for field in R.REQUIRED_DEV_FIELDS:
            assert dev.get(field), f"{dev.get('dev_id')} missing {field}"


def test_missing_required_field_is_an_error():
    bad = {"schema_version": 1, "devs": [{"dev_id": "x", "agent_name": "a", "machine": "m"}]}
    errs = R.validate_roster(bad)
    assert any("team_tag" in e for e in errs)


def test_duplicate_dev_id_is_an_error():
    dup = {
        "schema_version": 1,
        "devs": [
            {"dev_id": "x", "agent_name": "a", "machine": "m", "team_tag": "t"},
            {"dev_id": "x", "agent_name": "a", "machine": "m", "team_tag": "t"},
        ],
    }
    assert any("duplicate" in e for e in R.validate_roster(dup))


# 2. CODEOWNERS path match -------------------------------------------------------------------
def test_audit_path_ownership():
    assert R.audit_path_owner("team-knowledge/audit/jason.jsonl") == "jason"
    assert R.is_path_owned_by("team-knowledge/audit/jason.jsonl", "jason") is True
    # server-a's shard is NOT owned by jason
    assert R.is_path_owned_by("team-knowledge/audit/server-a.jsonl", "jason") is False
    assert R.audit_path_owner("team-knowledge/audit/server-a.jsonl") == "server-a"
    # a non-audit path has no audit owner
    assert R.audit_path_owner("team-knowledge/components/catalog.yaml") is None


# 3. forgeable-attribution guard -------------------------------------------------------------
def test_trust_check_uses_pr_actor_not_git_author():
    # The platform-verified merge actor matches the owner -> trusted, even though the (forgeable)
    # git author claims to be the owner in BOTH cases. The decision must follow pr_actor only.
    assert R.verify_merge_actor("jason", pr_actor="jason", git_author="jason") is True
    # Attacker forges git author = 'jason' but the real merge actor is someone else -> REFUSED.
    assert R.verify_merge_actor("jason", pr_actor="mallory", git_author="jason") is False
    # pr_actor and git_author can legitimately differ (commit by A, merged by owner) -> still trusted.
    assert R.verify_merge_actor("jason", pr_actor="jason", git_author="contributor") is True


# 4. importer rejection of un-gated provenance ----------------------------------------------
def test_catalog_entry_rejected_without_approval_record():
    entry = {"id": "voice-pipeline-v1", "owner_dev": "jason",
             "scan_audit": "audit/jason.jsonl#evt-1"}
    # No approval record for that scan_audit ref -> refused.
    assert R.catalog_entry_valid(entry, approvals={}) is False
    # With a protected-approval record present -> accepted.
    assert R.catalog_entry_valid(entry, approvals={"audit/jason.jsonl#evt-1": {"approved_by": "jason"}}) is True
    # Missing scan_audit pointer -> refused.
    assert R.catalog_entry_valid({"id": "x", "owner_dev": "jason"}, approvals={"x": True}) is False


# 5. unknown-sender quarantine ---------------------------------------------------------------
def test_unknown_sender_is_quarantined(real_roster):
    assert R.classify_sender(real_roster, "jason") == "known"
    assert R.classify_sender(real_roster, "agent-d") == "quarantine"
    assert R.is_known_dev(real_roster, "agent-d") is False
