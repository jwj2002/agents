"""Tests for action/cli.py — project picker and resolution logic."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure action package is importable without an action/__init__.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import action.cli as cli


# ---------- helpers ----------

def _args(**kwargs) -> argparse.Namespace:
    """Build a minimal Namespace with defaults for fields used by resolution logic."""
    defaults = {"project": None, "no_prompt": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------- list_known_projects ----------

def test_list_known_projects():
    """Returns a sorted non-empty list filtered by subscriptions (or all if no subs)."""
    projects = cli.list_known_projects()
    assert isinstance(projects, list)
    assert projects == sorted(projects), "list must be sorted"
    assert len(projects) > 0, "must find at least one project"
    # 'agents' is always subscribed on this machine
    assert "agents" in projects


def test_list_known_projects_tmp(tmp_path, monkeypatch):
    """list_known_projects uses KNOWLEDGE_PROJECTS_DIR, which can be overridden."""
    (tmp_path / "alpha.yaml").write_text("")
    (tmp_path / "gamma.yaml").write_text("")
    (tmp_path / "beta.yaml").write_text("")
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    result = cli.list_known_projects()
    assert result == ["alpha", "beta", "gamma"]


# ---------- resolve_project (existing, unchanged) ----------

def test_resolve_project_cwd_agents(monkeypatch):
    """cwd = ~/agents → resolves to 'agents' without touching the picker."""
    monkeypatch.chdir(cli.HOME / "agents")
    args = _args()
    assert cli.resolve_project(args) == "agents"


def test_resolve_project_explicit_known(monkeypatch):
    """--project supplied directly bypasses cwd logic (existing behavior)."""
    args = _args(project="agents")
    # resolve_project just returns it — no validation against known list
    assert cli.resolve_project(args) == "agents"


# ---------- _interactive_pick ----------

def test_interactive_pick_valid(monkeypatch):
    """Input '2' selects second candidate."""
    monkeypatch.setattr("builtins.input", lambda _: "2")
    result = cli._interactive_pick(["alpha", "beta", "gamma"], "Pick one:")
    assert result == "beta"


def test_interactive_pick_out_of_range_then_valid(monkeypatch):
    """Two bad inputs (out of range, non-numeric) then valid → returns project."""
    responses = iter(["99", "abc", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    result = cli._interactive_pick(["alpha", "beta"], "Pick one:")
    assert result == "alpha"


def test_interactive_pick_exhausted(monkeypatch):
    """Three consecutive bad inputs → ActionError."""
    monkeypatch.setattr("builtins.input", lambda _: "99")
    try:
        cli._interactive_pick(["alpha", "beta"], "Pick one:")
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert "aborted" in str(e) or "invalid" in str(e)


def test_interactive_pick_blank(monkeypatch):
    """Blank input → ActionError immediately."""
    monkeypatch.setattr("builtins.input", lambda _: "")
    try:
        cli._interactive_pick(["alpha", "beta"], "Pick one:")
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert "cancelled" in str(e)


def test_interactive_pick_ctrl_c(monkeypatch):
    """EOFError from input → ActionError (Ctrl-C / EOF behaviour)."""
    def raise_eof(_):
        raise EOFError
    monkeypatch.setattr("builtins.input", raise_eof)
    try:
        cli._interactive_pick(["alpha", "beta"], "Pick one:")
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert "cancelled" in str(e)


# ---------- resolve_project_with_picker ----------

def test_no_prompt_skips_picker_even_with_tty(monkeypatch, tmp_path):
    """isatty=True but --no-prompt → hard error (no picker)."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    (tmp_path / "alpha.yaml").write_text("")
    # cwd not in any known project dir, no --project
    monkeypatch.chdir(tmp_path)
    args = _args(no_prompt=True)
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert "no project resolved" in str(e)


def test_non_tty_skips_picker(monkeypatch, tmp_path):
    """isatty=False, no --no-prompt → hard error (no picker)."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    (tmp_path / "alpha.yaml").write_text("")
    monkeypatch.chdir(tmp_path)
    args = _args()
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert "no project resolved" in str(e)


def test_unknown_project_with_tty(monkeypatch, tmp_path):
    """--project typo + isatty=True → picker fires, returns selected project."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    (tmp_path / "alpha.yaml").write_text("")
    (tmp_path / "beta.yaml").write_text("")
    monkeypatch.setattr("builtins.input", lambda _: "1")
    args = _args(project="typo-project")
    result = cli.resolve_project_with_picker(args)
    assert result == "alpha"


def test_unknown_project_without_tty(monkeypatch, tmp_path):
    """--project typo + isatty=False + no disk dir → ActionError with Rule 3 message."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    # Redirect HOME so project_dir_exists("typo-project") → False
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(cli, "HOME", fake_home)
    # Also redirect SUBSCRIPTIONS_PATH so read_subscriptions returns []
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", tmp_path / "subs.json")
    (tmp_path / "alpha.yaml").write_text("")
    args = _args(project="typo-project")
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert 'unknown project "typo-project"' in str(e)
        assert "not registered" in str(e)


def test_resolve_cwd_projects_subdir(monkeypatch, tmp_path):
    """cwd = ~/projects/buddy/subdir → resolve_project returns 'buddy'."""
    buddy_sub = tmp_path / "projects" / "buddy" / "subdir"
    buddy_sub.mkdir(parents=True)
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.chdir(buddy_sub)
    args = _args()
    result = cli.resolve_project(args)
    assert result == "buddy"


# ---------- project_dir_exists ----------

def test_project_dir_exists_agents(monkeypatch, tmp_path):
    """project_dir_exists('agents') returns True when HOME/agents/ exists."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setattr(cli, "HOME", tmp_path)
    assert cli.project_dir_exists("agents") is True


def test_project_dir_exists_regular(monkeypatch, tmp_path):
    """project_dir_exists('foo') returns True when HOME/projects/foo/ exists."""
    (tmp_path / "projects" / "foo").mkdir(parents=True)
    monkeypatch.setattr(cli, "HOME", tmp_path)
    assert cli.project_dir_exists("foo") is True


def test_project_dir_exists_missing(monkeypatch, tmp_path):
    """project_dir_exists('bar') returns False when HOME/projects/bar/ does not exist."""
    monkeypatch.setattr(cli, "HOME", tmp_path)
    assert cli.project_dir_exists("bar") is False


# ---------- read_subscriptions ----------

def test_read_subscriptions_normal(monkeypatch, tmp_path):
    """Valid JSON with subscribed list → returns list of strings."""
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["agents", "paul-jason"]}')
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    result = cli.read_subscriptions()
    assert result == ["agents", "paul-jason"]


def test_read_subscriptions_missing_file(monkeypatch, tmp_path):
    """Missing subscriptions file → returns []."""
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", tmp_path / "nonexistent.json")
    assert cli.read_subscriptions() == []


def test_read_subscriptions_empty_array(monkeypatch, tmp_path):
    """subscribed: [] → returns []."""
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": []}')
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    assert cli.read_subscriptions() == []


# ---------- add_subscription ----------

def test_add_subscription_creates_file(monkeypatch, tmp_path):
    """add_subscription creates file if absent and writes [name]."""
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    cli.add_subscription("sweetprocess")
    import json as _json
    data = _json.loads(subs_file.read_text())
    assert data["subscribed"] == ["sweetprocess"]


def test_add_subscription_appends(monkeypatch, tmp_path):
    """add_subscription appends to existing list and does not duplicate."""
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["agents"]}')
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    cli.add_subscription("sweetprocess")
    cli.add_subscription("sweetprocess")  # second call must not duplicate
    import json as _json
    data = _json.loads(subs_file.read_text())
    assert data["subscribed"] == ["agents", "sweetprocess"]


# ---------- register_project ----------

def test_register_project_creates_yaml(monkeypatch, tmp_path):
    """register_project writes correct yaml defaults and calls add_subscription."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)

    result_path = cli.register_project("myproj")

    assert result_path == projects_dir / "myproj.yaml"
    content = result_path.read_text()
    assert "project: myproj" in content
    assert "status: active" in content
    assert 'focus: ""' in content
    assert 'updated_at: "' in content  # must be quoted
    assert "updated_by: jason" in content

    import json as _json
    subs = _json.loads(subs_file.read_text())
    assert "myproj" in subs["subscribed"]


def test_register_project_already_exists(monkeypatch, tmp_path):
    """register_project raises FileExistsError if yaml already exists."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "existing.yaml").write_text("project: existing\n")
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    try:
        cli.register_project("existing")
        assert False, "should have raised FileExistsError"
    except FileExistsError:
        pass


# ---------- list_known_projects with subscriptions ----------

def test_list_known_projects_filters_subs(monkeypatch, tmp_path):
    """list_known_projects returns only registered+subscribed projects."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    for name in ["alpha", "beta", "gamma"]:
        (projects_dir / f"{name}.yaml").write_text("")
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["alpha", "gamma"]}')
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    result = cli.list_known_projects()
    assert result == ["alpha", "gamma"]


def test_list_known_projects_empty_subs_fallback(monkeypatch, tmp_path):
    """list_known_projects returns all registered when subscriptions are empty."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    for name in ["alpha", "beta"]:
        (projects_dir / f"{name}.yaml").write_text("")
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": []}')
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    result = cli.list_known_projects()
    assert result == ["alpha", "beta"]


# ---------- auto-register on resolve ----------

def test_auto_register_on_resolve(monkeypatch, tmp_path, capsys):
    """resolve_project_with_picker auto-registers when disk dir exists for unknown project."""
    # Setup: HOME with projects/newproj dir, knowledge/projects dir, subs file
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (tmp_path / "projects" / "newproj").mkdir()
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    subs_file = tmp_path / "subs.json"

    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", knowledge_dir)
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)

    args = _args(project="newproj", no_prompt=True)
    result = cli.resolve_project_with_picker(args)

    assert result == "newproj"
    captured = capsys.readouterr()
    assert 'registered new project "newproj"' in captured.out
    assert (knowledge_dir / "newproj.yaml").exists()


def test_no_disk_dir_no_tty_error_message(monkeypatch, tmp_path):
    """No disk dir, not tty → ActionError with Rule 3 text."""
    projects_dir = tmp_path / "knowledge"
    projects_dir.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["agents"]}')

    monkeypatch.setattr(cli, "HOME", fake_home)
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)

    args = _args(project="ghostproject", no_prompt=True)
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        msg = str(e)
        assert "not registered" in msg
        assert "no repo at" in msg
        assert "Subscribed on this machine:" in msg
