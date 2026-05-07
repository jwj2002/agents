"""Tests for dashboard/cli.py — pure-read project status overview."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import dashboard.cli as cli


# ---------- mode resolution ----------

def _ns(**kwargs):
    import argparse
    kwargs.setdefault("project_arg", None)
    return argparse.Namespace(**kwargs)


def test_mode_resolves_explicit_arg(monkeypatch, tmp_path):
    args = _ns(project_arg="agents")
    assert cli.resolve_mode(args) == ("single", "agents")


def test_mode_resolves_cwd_in_agents(monkeypatch, tmp_path):
    monkeypatch.chdir(cli.HOME / "agents")
    assert cli.resolve_mode(_ns()) == ("single", "agents")


def test_mode_resolves_cwd_outside_known_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert cli.resolve_mode(_ns()) == ("multi", None)


def test_mode_skips_archived_dir(monkeypatch, tmp_path):
    archived = tmp_path / "_archived" / "flotilla"
    archived.mkdir(parents=True)
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.chdir(archived)
    # No fake `~/projects` first segment match → falls through to multi
    assert cli.resolve_mode(_ns()) == ("multi", None)


# ---------- subscriptions ----------

def test_subscriptions_missing_file(monkeypatch, tmp_path):
    fake = tmp_path / "missing.json"
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", fake)
    with pytest.raises(cli.DashboardError) as exc:
        cli.read_subscriptions()
    assert "missing or empty" in str(exc.value)
    assert "/project NAME --subscribe" in str(exc.value)


def test_subscriptions_malformed(monkeypatch, tmp_path):
    fake = tmp_path / "subs.json"
    fake.write_text("not valid json {")
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", fake)
    with pytest.raises(cli.DashboardError) as exc:
        cli.read_subscriptions()
    assert "malformed" in str(exc.value)


def test_subscriptions_empty_array(monkeypatch, tmp_path):
    fake = tmp_path / "subs.json"
    fake.write_text(json.dumps({"subscribed": []}))
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", fake)
    with pytest.raises(cli.DashboardError) as exc:
        cli.read_subscriptions()
    assert "no subscriptions" in str(exc.value)


def test_subscriptions_no_subscribed_key(monkeypatch, tmp_path):
    fake = tmp_path / "subs.json"
    fake.write_text(json.dumps({"other": "thing"}))
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", fake)
    with pytest.raises(cli.DashboardError):
        cli.read_subscriptions()


def test_subscriptions_valid(monkeypatch, tmp_path):
    fake = tmp_path / "subs.json"
    fake.write_text(json.dumps({"subscribed": ["agents", "buddy"]}))
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", fake)
    assert cli.read_subscriptions() == ["agents", "buddy"]


# ---------- knowledge YAML ----------

def test_load_project_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "PROJECTS_YAML_DIR", tmp_path)
    assert cli.load_project("nonexistent") is None


def test_load_project_parses_fields(monkeypatch, tmp_path):
    p = tmp_path / "agents.yaml"
    p.write_text(
        "project: agents\nstatus: active\nfocus: Test focus\n"
        "next_steps: [step1, step2]\nblockers: []\nopen_questions: [q1]\n"
        "updated_at: 2026-05-07\nupdated_by: jason\n"
    )
    monkeypatch.setattr(cli, "PROJECTS_YAML_DIR", tmp_path)
    proj = cli.load_project("agents")
    assert proj is not None
    assert proj.name == "agents"
    assert proj.status == "active"
    assert proj.focus == "Test focus"
    assert proj.next_steps == ["step1", "step2"]
    assert proj.blockers == []
    assert proj.open_questions == ["q1"]


def test_load_project_handles_missing_optional_fields(monkeypatch, tmp_path):
    p = tmp_path / "minimal.yaml"
    p.write_text("project: minimal\nstatus: paused\nfocus: foo\n")
    monkeypatch.setattr(cli, "PROJECTS_YAML_DIR", tmp_path)
    proj = cli.load_project("minimal")
    assert proj.next_steps == []
    assert proj.blockers == []


# ---------- decisions ----------

def test_load_decisions_filters_by_project_and_window(monkeypatch, tmp_path):
    (tmp_path / "D-001.yaml").write_text(
        "id: D-001\nproject: agents\ndate: 2026-04-01\ntitle: Old decision\n"
    )
    (tmp_path / "D-002.yaml").write_text(
        "id: D-002\nproject: agents\ndate: 2026-05-06\ntitle: Recent decision\n"
    )
    (tmp_path / "D-003.yaml").write_text(
        "id: D-003\nproject: other\ndate: 2026-05-06\ntitle: Other project\n"
    )
    monkeypatch.setattr(cli, "DECISIONS_DIR", tmp_path)
    # Window: last 7 days from 2026-05-07
    since = date(2026, 5, 1)
    out = cli.load_decisions("agents", since)
    titles = [d["title"] for d in out]
    assert "Recent decision" in titles
    assert "Old decision" not in titles
    assert "Other project" not in titles  # project filter
    # No window
    out_full = cli.load_decisions("agents", None)
    assert len(out_full) == 2


# ---------- captures ----------

def test_load_captures_returns_empty_when_db_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "KNOWLEDGE_DB_PATH", tmp_path / "missing.db")
    assert cli.load_captures(None) == []


def test_load_captures_reads_open_only(monkeypatch, tmp_path):
    db = tmp_path / "k.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE inbox (id INTEGER PRIMARY KEY, content TEXT, project TEXT, type TEXT, status TEXT);
        INSERT INTO inbox VALUES (1, 'open one', 'agents', 'idea', 'open');
        INSERT INTO inbox VALUES (2, 'closed one', 'agents', 'task', 'done');
        INSERT INTO inbox VALUES (3, 'flotilla one', 'flotilla', 'idea', 'open');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(cli, "KNOWLEDGE_DB_PATH", db)
    out = cli.load_captures(None)
    assert len(out) == 2
    assert all(c["type"] for c in out)
    out_agents = cli.load_captures("agents")
    assert len(out_agents) == 1
    assert out_agents[0]["content"] == "open one"


# ---------- ACTIONS.md overlay ----------

_ACTIONS_FIXTURE = """\
# Project ACTIONS

Next ID: **A-006**

## Open

| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
|----|-------|--------|-------|--------|--------|-----|-------|-------|
| A-001 | | Open one | Jason | open | 2026-05-01 | | | |
| A-002 | | Open two | Paul | wip | 2026-05-02 | | | |

## Recently Closed

| ID | Issue | Action | Owner | Closed | Files | Notes |
|----|-------|--------|-------|--------|-------|-------|
| A-003 | | Closed-recent | Jason | 2026-05-06 | | |
| A-004 | | Closed-old | Paul | 2026-04-01 | | |

## Archive

_(none)_
"""


def test_load_actions_includes_open_and_in_window_closed(monkeypatch, tmp_path):
    repo = tmp_path / "agents"
    repo.mkdir()
    (repo / "ACTIONS.md").write_text(_ACTIONS_FIXTURE)
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "PROJECTS_YAML_DIR", tmp_path)  # not used here, just kept consistent

    # Window: last 30 days from 2026-05-07
    since = date(2026, 5, 1)
    open_rows, closed_rows = cli.load_actions("agents", since, owner_filter=None)
    assert len(open_rows) == 2
    closed_ids = [r["ID"] for r in closed_rows]
    assert "A-003" in closed_ids        # closed 2026-05-06 → in window
    assert "A-004" not in closed_ids    # closed 2026-04-01 → out of window


def test_load_actions_owner_filter(monkeypatch, tmp_path):
    repo = tmp_path / "agents"
    repo.mkdir()
    (repo / "ACTIONS.md").write_text(_ACTIONS_FIXTURE)
    monkeypatch.setattr(cli, "HOME", tmp_path)
    open_rows, closed_rows = cli.load_actions("agents", since=None, owner_filter="paul")
    assert len(open_rows) == 1
    assert open_rows[0]["Owner"] == "Paul"
    assert all(r["Owner"].lower() == "paul" for r in closed_rows)


def test_load_actions_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "HOME", tmp_path)
    open_rows, closed_rows = cli.load_actions("nonexistent", since=None, owner_filter=None)
    assert open_rows == [] and closed_rows == []


# ---------- gh slug parsing ----------

def test_gh_slug_parses_https_url(monkeypatch, tmp_path):
    # Set up a fake repo
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    def fake_run(args, *a, **kw):
        import subprocess as _sp
        return _sp.CompletedProcess(args, 0, "https://github.com/jwj2002/agents.git\n", "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.gh_slug_for_repo(repo) == "jwj2002/agents"


def test_gh_slug_parses_ssh_url(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    def fake_run(args, *a, **kw):
        import subprocess as _sp
        return _sp.CompletedProcess(args, 0, "git@github.com:foo/bar.git\n", "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.gh_slug_for_repo(repo) == "foo/bar"


def test_gh_slug_returns_none_for_non_github(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    def fake_run(args, *a, **kw):
        import subprocess as _sp
        return _sp.CompletedProcess(args, 0, "git@gitlab.example.com:org/repo.git\n", "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.gh_slug_for_repo(repo) is None


def test_gh_slug_returns_none_for_non_git_dir(tmp_path):
    assert cli.gh_slug_for_repo(tmp_path) is None


# ---------- rendering ----------

def _build_populated_project() -> cli.Project:
    p = cli.Project(name="test", status="active", focus="Testing dashboard")
    p.next_steps = ["Step one"]
    p.blockers = ["Blocker A"]
    p.open_questions = ["Q1?"]
    p.actions_open = [{"ID": "A-001", "Owner": "Jason", "Action": "Test action", "Status": "open"}]
    p.actions_closed = [{"ID": "A-002", "Owner": "Jason", "Action": "Closed action", "Closed": "2026-05-06"}]
    p.issues_open = [{"number": 42, "title": "Open issue", "updatedAt": "2026-05-06T12:00:00Z"}]
    p.issues_closed = [{"number": 41, "title": "Closed issue", "closedAt": "2026-05-06T12:00:00Z"}]
    p.decisions = [{"id": "D-001", "date": "2026-05-06", "title": "Test decision"}]
    p.captures = [{"id": 1, "type": "idea", "content": "Capture content", "project": "test"}]
    return p


def test_terminal_render_contains_all_sections():
    p = _build_populated_project()
    out = cli.render_terminal_single(p, "weekly", None)
    assert "PROJECT: test" in out
    assert "ACTIVE" in out
    assert "Focus:" in out
    assert "Blockers:" in out
    assert "Open Questions:" in out
    assert "Next Steps:" in out
    assert "Actions (1 open, 1 closed-in-window)" in out
    assert "Test action" in out
    assert "✓ 2026-05-06" in out  # closed-row suffix preserved
    assert "Issues (1 open, 1 closed-in-window)" in out
    assert "Open issue" in out
    assert "Decisions in window (1)" in out
    assert "Captures (1 open)" in out
    assert "Capture content" in out
    assert "window: weekly" in out


def test_terminal_render_truncation_preserves_closed_suffix():
    p = cli.Project(name="t", status="active", focus="x")
    p.actions_closed = [{
        "ID": "A-001", "Owner": "Jason",
        "Action": "x" * 500,  # very long
        "Closed": "2026-05-06",
    }]
    out = cli.render_terminal_single(p, "daily", None)
    assert "✓ 2026-05-06" in out  # suffix must survive truncation
    assert "…" in out              # body should be ellipsized


def test_markdown_digest_stable_header():
    p = _build_populated_project()
    out = cli.render_markdown([p], "daily", "test", None)
    assert out.startswith("<!-- dashboard-digest v1 test daily ")
    assert "**Window:** daily" in out
    assert "## test (ACTIVE)" in out


def test_markdown_multi_uses_multi_marker():
    p = _build_populated_project()
    out = cli.render_markdown([p], "weekly", None, None)
    assert "<!-- dashboard-digest v1 multi weekly " in out


def test_markdown_owner_filter_appears_in_header():
    p = _build_populated_project()
    out = cli.render_markdown([p], "daily", "test", "Jason")
    assert "**Owner filter:** Jason" in out


# ---------- argparse / window math ----------

def test_window_since_daily_is_yesterday():
    today = date.today()
    assert cli.window_since("daily") == today - timedelta(days=1)
    assert cli.window_since("full") is None
    assert cli.window_since("weekly") == today - timedelta(days=7)
