"""Tests for the Path B vault-aware additions in lib/project_resolver.py.

Covers:
- read_subscriptions_dict / write_subscriptions_dict (vault-keyed format)
- add_subscription_to_vault / remove_subscription_from_vault
- claim_ssh_host / release_ssh_host
- resolve_vault_for_project (single match / zero match / multi match)
- project_md_path / decision_md_path / vault_path
- default_vault env override
- legacy ↔ vault-keyed format coexistence and migration on first vault-aware write
- legacy add/remove ops preserve legacy format until vault-aware op forces migration
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import project_resolver as pr  # noqa: E402


@pytest.fixture
def subs_file(monkeypatch, tmp_path: Path) -> Path:
    """Redirect SUBSCRIPTIONS_PATH to a tmp file; clear default-vault env var."""
    f = tmp_path / "subs.json"
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", f)
    monkeypatch.delenv(pr.DEFAULT_VAULT_ENV, raising=False)
    return f


@pytest.fixture
def vaults_root(monkeypatch, tmp_path: Path) -> Path:
    base = tmp_path / "vaults"
    monkeypatch.setattr(pr, "VAULTS_BASE", base)
    return base


# ---------- default_vault ----------

def test_default_vault_uses_env_override(monkeypatch):
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "Custom-Vault")
    assert pr.default_vault() == "Custom-Vault"


def test_default_vault_falls_back_when_env_unset(monkeypatch):
    monkeypatch.delenv(pr.DEFAULT_VAULT_ENV, raising=False)
    assert pr.default_vault() == pr.DEFAULT_VAULT_FALLBACK


# ---------- vault / md paths ----------

def test_vault_path_resolves_under_base(vaults_root):
    assert pr.vault_path("MyVault") == vaults_root / "MyVault"


def test_decision_md_path_under_vault(vaults_root):
    assert pr.decision_md_path("D-042", "V") == vaults_root / "V" / "Decisions" / "D-042.md"


def test_project_md_path_with_explicit_vault(vaults_root):
    assert pr.project_md_path("agents", vault="V") == vaults_root / "V" / "Projects" / "agents.md"


def test_project_md_path_resolves_vault_from_subscriptions(subs_file, vaults_root):
    subs_file.write_text(json.dumps({
        "V1": {"subscribed": ["agents"], "ssh_writes": []},
        "V2": {"subscribed": ["other"], "ssh_writes": []},
    }))
    assert pr.project_md_path("agents") == vaults_root / "V1" / "Projects" / "agents.md"


# ---------- read_subscriptions_dict ----------

def test_read_subscriptions_dict_empty(subs_file):
    assert pr.read_subscriptions_dict() == {}


def test_read_subscriptions_dict_legacy_format_refused(subs_file):
    """Legacy {"subscribed": [...]} is no longer supported — Path B migrated it.

    Encountering it on read raises a clear error pointing at the migration script.
    """
    subs_file.write_text(json.dumps({"subscribed": ["agents", "buddy"]}))
    with pytest.raises(pr.ProjectResolutionError, match="legacy flat format"):
        pr.read_subscriptions_dict()


def test_read_subscriptions_dict_vault_keyed(subs_file):
    subs_file.write_text(json.dumps({
        "V1": {"subscribed": ["a"], "ssh_writes": ["h1"]},
        "V2": {"subscribed": ["b", "c"], "ssh_writes": []},
    }))
    out = pr.read_subscriptions_dict()
    assert out["V1"]["subscribed"] == ["a"]
    assert out["V1"]["ssh_writes"] == ["h1"]
    assert out["V2"]["subscribed"] == ["b", "c"]


def test_read_subscriptions_dict_normalizes_missing_keys(subs_file):
    """A vault entry missing ssh_writes/subscribed is normalized to []."""
    subs_file.write_text(json.dumps({"V1": {"subscribed": ["a"]}}))
    out = pr.read_subscriptions_dict()
    assert out["V1"] == {"subscribed": ["a"], "ssh_writes": []}


# ---------- read_subscriptions (vault-keyed aggregator) ----------

def test_read_subscriptions_aggregates_across_vaults(subs_file):
    subs_file.write_text(json.dumps({
        "V1": {"subscribed": ["a", "b"], "ssh_writes": []},
        "V2": {"subscribed": ["c"], "ssh_writes": []},
    }))
    assert sorted(pr.read_subscriptions()) == ["a", "b", "c"]


def test_read_subscriptions_dedups_across_vaults(subs_file):
    subs_file.write_text(json.dumps({
        "V1": {"subscribed": ["shared"], "ssh_writes": []},
        "V2": {"subscribed": ["shared", "extra"], "ssh_writes": []},
    }))
    assert sorted(pr.read_subscriptions()) == ["extra", "shared"]


# ---------- add/remove subscription ----------

def test_add_subscription_to_empty_writes_vault_keyed(subs_file, monkeypatch):
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "DV")
    pr.add_subscription("a")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk == {"DV": {"subscribed": ["a"], "ssh_writes": []}}


def test_add_subscription_routes_to_default_vault(subs_file, monkeypatch):
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "DV")
    subs_file.write_text(json.dumps({
        "DV": {"subscribed": ["a"], "ssh_writes": []},
    }))
    pr.add_subscription("b")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["DV"]["subscribed"] == ["a", "b"]


def test_add_subscription_idempotent_across_vaults(subs_file, monkeypatch):
    """If `name` is already subscribed in any vault, add_subscription is a no-op."""
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "DV")
    subs_file.write_text(json.dumps({
        "Other": {"subscribed": ["existing"], "ssh_writes": []},
    }))
    pr.add_subscription("existing")
    on_disk = json.loads(subs_file.read_text())
    # No DV vault created — existing entry honored
    assert "DV" not in on_disk
    assert on_disk["Other"]["subscribed"] == ["existing"]


def test_remove_subscription_vault_keyed_drops_from_all_vaults(subs_file):
    subs_file.write_text(json.dumps({
        "V1": {"subscribed": ["a", "shared"], "ssh_writes": []},
        "V2": {"subscribed": ["shared"], "ssh_writes": []},
    }))
    pr.remove_subscription("shared")
    on_disk = json.loads(subs_file.read_text())
    assert "shared" not in on_disk["V1"]["subscribed"]
    assert "shared" not in on_disk["V2"]["subscribed"]


# ---------- vault-aware ops ----------

def test_add_subscription_to_vault_idempotent(subs_file):
    pr.add_subscription_to_vault("V", "p")
    pr.add_subscription_to_vault("V", "p")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["V"]["subscribed"] == ["p"]


def test_add_subscription_to_vault_creates_vault_entry(subs_file):
    pr.add_subscription_to_vault("BrandNew", "p")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["BrandNew"] == {"subscribed": ["p"], "ssh_writes": []}


def test_remove_subscription_from_vault(subs_file):
    pr.add_subscription_to_vault("V", "a")
    pr.add_subscription_to_vault("V", "b")
    pr.remove_subscription_from_vault("V", "a")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["V"]["subscribed"] == ["b"]


def test_remove_subscription_from_vault_missing_vault_is_noop(subs_file):
    pr.add_subscription_to_vault("V", "a")
    pr.remove_subscription_from_vault("OtherVault", "a")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["V"]["subscribed"] == ["a"]


# ---------- claim_ssh_host / release_ssh_host ----------

def test_claim_ssh_host_creates_vault_entry(subs_file):
    pr.claim_ssh_host("V", "jbox06")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["V"] == {"subscribed": [], "ssh_writes": ["jbox06"]}


def test_claim_ssh_host_idempotent(subs_file):
    pr.claim_ssh_host("V", "jbox06")
    pr.claim_ssh_host("V", "jbox06")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["V"]["ssh_writes"] == ["jbox06"]


def test_release_ssh_host(subs_file):
    pr.claim_ssh_host("V", "h1")
    pr.claim_ssh_host("V", "h2")
    pr.release_ssh_host("V", "h1")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["V"]["ssh_writes"] == ["h2"]


def test_release_ssh_host_missing_is_noop(subs_file):
    pr.claim_ssh_host("V", "h1")
    pr.release_ssh_host("V", "absent")  # not present
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["V"]["ssh_writes"] == ["h1"]


# ---------- resolve_vault_for_project ----------

def test_resolve_vault_for_project_single_match(subs_file):
    pr.add_subscription_to_vault("V1", "agents")
    pr.add_subscription_to_vault("V2", "other")
    assert pr.resolve_vault_for_project("agents") == "V1"


def test_resolve_vault_for_project_no_match_errors(subs_file):
    pr.add_subscription_to_vault("V1", "agents")
    with pytest.raises(pr.ProjectResolutionError, match="not subscribed"):
        pr.resolve_vault_for_project("missing")


def test_resolve_vault_for_project_multiple_match_errors(subs_file):
    pr.add_subscription_to_vault("V1", "shared")
    pr.add_subscription_to_vault("V2", "shared")
    with pytest.raises(pr.ProjectResolutionError, match="multiple vaults"):
        pr.resolve_vault_for_project("shared")


# ---------- write_subscriptions_dict ----------

def test_write_subscriptions_dict_atomic(subs_file):
    pr.write_subscriptions_dict({
        "V": {"subscribed": ["a"], "ssh_writes": ["h"]},
    })
    on_disk = json.loads(subs_file.read_text())
    assert on_disk == {"V": {"subscribed": ["a"], "ssh_writes": ["h"]}}
    # No tmp leftover
    assert not list(subs_file.parent.glob("*.tmp"))


def test_write_subscriptions_dict_normalizes_input(subs_file):
    """Junk extra keys + missing fields get cleaned to canonical shape."""
    pr.write_subscriptions_dict({
        "V": {"subscribed": ["a"], "ssh_writes": [], "junk": "ignored"},
        "Bad": "not-a-dict",  # silently dropped
    })
    on_disk = json.loads(subs_file.read_text())
    assert on_disk == {"V": {"subscribed": ["a"], "ssh_writes": []}}
