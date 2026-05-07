"""Tests for decision/cli.py — view/list/new/update + index management."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Repo root on path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import decision.cli as cli  # noqa: E402


# ---------- fixtures ----------

_D042 = """\
schema_version: 1
id: D-042
date: '2026-03-28'
project: docketiq
topic: auth
title: Redis session cache for docketiq
context: docketiq has SSR; high-frequency reads make DB sessions too slow.
decision: Use Redis-backed sessions for SSR.
alternatives:
- option: JWT
  rejected_because: Need server-side state.
- option: Database sessions
  rejected_because: Too slow.
reasoning: Redis is fast; SSR needs server state.
outcome: Deployed; <1ms reads.
linked:
  patterns:
  - pat-auth-redis-sessions
  issues: []
  prs: []
  related_decisions:
  - D-015
created_at: '2026-03-28'
"""

_D098_LEGACY = """\
schema_version: 1
id: D-098
date: '2026-04-08'
project: flotilla
topic: architecture
title: Federated flotilla instances
context: Designing for team expansion.
decision: "Federation: each developer owns their flotilla."
alternatives:
- option: Centralized
  rejected_because: Bottleneck.
reasoning: Federation preserves autonomy.
outcome: null
linked_patterns: []
linked_issues:
- "#21-27"
linked_prs: []
related_decisions:
- D-096
created_at: '2026-04-08'
"""

_INDEX = """\
by_project:
  docketiq:
    - id: D-042
      topic: auth
      title: Redis session cache for docketiq
      date: '2026-03-28'
by_topic:
  auth:
    - D-042
by_pattern:
  pat-auth-redis-sessions:
    - D-042
"""


def _wire(monkeypatch, tmp_path: Path, *, register: tuple[str, ...] = ("docketiq", "agents")):
    """Redirect DECISIONS_DIR + KNOWLEDGE_PROJECTS_DIR + INDEX_PATH to tmp."""
    decisions_dir = tmp_path / "knowledge" / "decisions"
    decisions_dir.mkdir(parents=True)
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True)
    subs_file = tmp_path / "subs.json"

    monkeypatch.setattr(cli, "DECISIONS_DIR", decisions_dir)
    monkeypatch.setattr(cli, "INDEX_PATH", decisions_dir / "index.yaml")
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)

    for name in register:
        (projects_dir / f"{name}.yaml").write_text(
            f"schema_version: 1\nproject: {name}\nstatus: active\nfocus: ''\n"
        )
    return decisions_dir


# ---------- view mode ----------

def test_view_canonical_decision(monkeypatch, tmp_path, capsys):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    rc = cli.main(["D-042", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DECISION D-042" in out
    assert "docketiq" in out
    assert "Redis session cache" in out
    assert "pat-auth-redis-sessions" in out


def test_view_normalizes_legacy_schema(monkeypatch, tmp_path, capsys):
    """D-098-style top-level linked_* keys are folded into linked: on read."""
    d = _wire(monkeypatch, tmp_path)
    (d / "D-098.yaml").write_text(_D098_LEGACY)
    rc = cli.main(["D-098", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DECISION D-098" in out
    assert "#21-27" in out  # was at top level under linked_issues
    assert "D-096" in out   # was at top level under related_decisions


def test_view_missing_errors(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch, tmp_path)
    rc = cli.main(["D-999", "--no-prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


def test_view_invalid_id_errors(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch, tmp_path)
    rc = cli.main(["bogus-id", "--no-prompt"])
    assert rc == 1
    assert "invalid decision id" in capsys.readouterr().err


# ---------- list mode ----------

def test_list_all(monkeypatch, tmp_path, capsys):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    (d / "D-098.yaml").write_text(_D098_LEGACY)
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-042" in out and "D-098" in out
    # Sorted newest first (D-098 is 2026-04-08, D-042 is 2026-03-28).
    assert out.index("D-098") < out.index("D-042")


def test_list_filter_by_project(monkeypatch, tmp_path, capsys):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    (d / "D-098.yaml").write_text(_D098_LEGACY)
    rc = cli.main(["--list", "--project", "docketiq", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-042" in out
    assert "D-098" not in out


def test_list_filter_by_topic(monkeypatch, tmp_path, capsys):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    (d / "D-098.yaml").write_text(_D098_LEGACY)
    rc = cli.main(["--list", "--topic", "architecture", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-098" in out
    assert "D-042" not in out


def test_list_empty(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch, tmp_path)
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0
    assert "no decisions match" in capsys.readouterr().out


# ---------- new mode ----------

def test_new_assigns_next_id(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    (d / "D-098.yaml").write_text(_D098_LEGACY)
    rc = cli.main([
        "--new",
        "--title", "Test",
        "--decision", "Do X.",
        "--project", "agents",
        "--topic", "infrastructure",
        "--no-prompt",
    ])
    assert rc == 0
    new_path = d / "D-099.yaml"
    assert new_path.exists()
    data = yaml.safe_load(new_path.read_text())
    assert data["id"] == "D-099"
    assert data["schema_version"] == 1
    assert data["project"] == "agents"
    assert data["topic"] == "infrastructure"
    assert data["title"] == "Test"
    assert data["decision"] == "Do X."
    assert data["alternatives"] == []
    assert data["outcome"] is None
    assert data["linked"] == {"patterns": [], "issues": [], "prs": [], "related_decisions": []}


def test_new_writes_to_index_by_project_and_topic(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    rc = cli.main([
        "--new",
        "--title", "Migration",
        "--decision", "Switch to X.",
        "--project", "agents",
        "--topic", "infrastructure",
        "--no-prompt",
    ])
    assert rc == 0
    idx = yaml.safe_load((d / "index.yaml").read_text())
    assert "D-043" in [e["id"] for e in idx["by_project"]["agents"]]
    assert "D-043" in idx["by_topic"]["infrastructure"]


def test_new_no_existing_files_assigns_d001(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    rc = cli.main([
        "--new",
        "--title", "First",
        "--decision", "Y.",
        "--project", "agents",
        "--topic", "auth",
        "--no-prompt",
    ])
    assert rc == 0
    assert (d / "D-001.yaml").exists()


def test_new_requires_title_and_decision(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch, tmp_path)
    rc = cli.main([
        "--new",
        "--project", "agents",
        "--topic", "auth",
        "--no-prompt",
    ])
    assert rc == 1
    assert "--new requires --title and --decision" in capsys.readouterr().err


def test_new_no_prompt_requires_topic(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch, tmp_path)
    rc = cli.main([
        "--new",
        "--title", "T",
        "--decision", "D.",
        "--project", "agents",
        "--no-prompt",
    ])
    assert rc == 1
    assert "topic required" in capsys.readouterr().err.lower()


def test_new_atomic_no_temp_left(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    cli.main([
        "--new",
        "--title", "T",
        "--decision", "D.",
        "--project", "agents",
        "--topic", "auth",
        "--no-prompt",
    ])
    leftover = list(d.glob("*.tmp*"))
    assert leftover == []


# ---------- update mode ----------

def test_update_outcome_only(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    rc = cli.main(["D-042", "--outcome", "Shipped to prod, working great", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load((d / "D-042.yaml").read_text())
    assert data["outcome"] == "Shipped to prod, working great"


def test_update_add_pattern_updates_index(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    (d / "index.yaml").write_text(_INDEX)
    rc = cli.main(["D-042", "--add-pattern", "pat-fastapi-auth-wiring", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load((d / "D-042.yaml").read_text())
    assert "pat-fastapi-auth-wiring" in data["linked"]["patterns"]
    idx = yaml.safe_load((d / "index.yaml").read_text())
    assert "D-042" in idx["by_pattern"]["pat-fastapi-auth-wiring"]


def test_update_add_pr_normalizes_hash(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    rc = cli.main(["D-042", "--add-pr", "147", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load((d / "D-042.yaml").read_text())
    assert "#147" in data["linked"]["prs"]


def test_update_add_issue_keeps_hash_if_provided(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    rc = cli.main(["D-042", "--add-issue", "#148", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load((d / "D-042.yaml").read_text())
    assert data["linked"]["issues"] == ["#148"]


def test_update_add_related(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    rc = cli.main(["D-042", "--add-related", "D-091", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load((d / "D-042.yaml").read_text())
    # D-015 was already there; D-091 appended without dupes
    assert data["linked"]["related_decisions"] == ["D-015", "D-091"]


def test_update_idempotent_on_dup(monkeypatch, tmp_path, capsys):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    rc = cli.main(["D-042", "--add-related", "D-015", "--no-prompt"])  # already there
    assert rc == 0
    out = capsys.readouterr().out
    assert "no changes" in out


# ---------- schema normalization on write ----------

def test_legacy_schema_normalized_on_write(monkeypatch, tmp_path):
    """Loading a D-098-style record and writing it back produces D-042-style nested form."""
    d = _wire(monkeypatch, tmp_path)
    (d / "D-098.yaml").write_text(_D098_LEGACY)
    # Trigger a write via update
    rc = cli.main(["D-098", "--add-pattern", "pat-x", "--no-prompt"])
    assert rc == 0
    text = (d / "D-098.yaml").read_text()
    # Old top-level keys gone
    assert "linked_patterns:" not in text
    assert "linked_issues:" not in text
    # Nested form present
    data = yaml.safe_load(text)
    assert "linked" in data
    assert data["linked"]["issues"] == ["#21-27"]
    assert "pat-x" in data["linked"]["patterns"]
    assert data["linked"]["related_decisions"] == ["D-096"]


# ---------- field order ----------

def test_field_order_preserved(monkeypatch, tmp_path):
    d = _wire(monkeypatch, tmp_path)
    (d / "D-042.yaml").write_text(_D042)
    cli.main(["D-042", "--outcome", "Updated", "--no-prompt"])
    text = (d / "D-042.yaml").read_text()
    schema_idx = text.index("schema_version:")
    id_idx = text.index("id:")
    project_idx = text.index("project:")
    title_idx = text.index("title:")
    linked_idx = text.index("linked:")
    assert schema_idx < id_idx < project_idx < title_idx < linked_idx


# ---------- argparse smoke ----------

def test_parse_args_defaults():
    a = cli.parse_args(["D-042", "--no-prompt"])
    assert a.id == "D-042"
    assert a.list is False
    assert a.new is False
    assert a.outcome is None
