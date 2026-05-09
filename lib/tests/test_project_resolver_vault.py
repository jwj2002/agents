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


def test_read_subscriptions_dict_legacy_synthesizes_default_vault(subs_file):
    subs_file.write_text(json.dumps({"subscribed": ["agents", "buddy"]}))
    out = pr.read_subscriptions_dict()
    assert out == {pr.DEFAULT_VAULT_FALLBACK: {"subscribed": ["agents", "buddy"], "ssh_writes": []}}


def test_read_subscriptions_dict_legacy_does_not_rewrite_file(subs_file):
    subs_file.write_text(json.dumps({"subscribed": ["agents"]}))
    pr.read_subscriptions_dict()
    on_disk = json.loads(subs_file.read_text())
    assert "subscribed" in on_disk  # still legacy shape


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


# ---------- read_subscriptions (legacy aggregator over both formats) ----------

def test_read_subscriptions_legacy_format(subs_file):
    subs_file.write_text(json.dumps({"subscribed": ["a", "b"]}))
    assert pr.read_subscriptions() == ["a", "b"]


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


# ---------- add/remove subscription preserves on-disk format ----------

def test_add_subscription_legacy_stays_legacy(subs_file):
    subs_file.write_text(json.dumps({"subscribed": ["a"]}))
    pr.add_subscription("b")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk == {"subscribed": ["a", "b"]}


def test_add_subscription_to_empty_writes_legacy(subs_file):
    pr.add_subscription("a")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk == {"subscribed": ["a"]}


def test_add_subscription_vault_keyed_routes_to_default_vault(subs_file, monkeypatch):
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "DV")
    subs_file.write_text(json.dumps({
        "DV": {"subscribed": ["a"], "ssh_writes": []},
    }))
    pr.add_subscription("b")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["DV"]["subscribed"] == ["a", "b"]


def test_remove_subscription_legacy_stays_legacy(subs_file):
    subs_file.write_text(json.dumps({"subscribed": ["a", "b"]}))
    pr.remove_subscription("a")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk == {"subscribed": ["b"]}


def test_remove_subscription_vault_keyed_drops_from_all_vaults(subs_file):
    subs_file.write_text(json.dumps({
        "V1": {"subscribed": ["a", "shared"], "ssh_writes": []},
        "V2": {"subscribed": ["shared"], "ssh_writes": []},
    }))
    pr.remove_subscription("shared")
    on_disk = json.loads(subs_file.read_text())
    assert "shared" not in on_disk["V1"]["subscribed"]
    assert "shared" not in on_disk["V2"]["subscribed"]


# ---------- vault-aware ops migrate legacy on first write ----------

def test_add_subscription_to_vault_migrates_legacy(subs_file, monkeypatch):
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "DV")
    subs_file.write_text(json.dumps({"subscribed": ["existing"]}))
    pr.add_subscription_to_vault("NewVault", "fresh")
    on_disk = json.loads(subs_file.read_text())
    # Legacy entries land in DV
    assert on_disk["DV"]["subscribed"] == ["existing"]
    # New vault has the new entry
    assert on_disk["NewVault"]["subscribed"] == ["fresh"]
    assert on_disk["NewVault"]["ssh_writes"] == []


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


def test_claim_ssh_host_migrates_legacy(subs_file, monkeypatch):
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "DV")
    subs_file.write_text(json.dumps({"subscribed": ["a"]}))
    pr.claim_ssh_host("V", "h1")
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["DV"]["subscribed"] == ["a"]
    assert on_disk["V"]["ssh_writes"] == ["h1"]


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


def test_resolve_vault_for_project_legacy_routes_to_default(subs_file, monkeypatch):
    monkeypatch.setenv(pr.DEFAULT_VAULT_ENV, "DV")
    subs_file.write_text(json.dumps({"subscribed": ["agents"]}))
    assert pr.resolve_vault_for_project("agents") == "DV"


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
