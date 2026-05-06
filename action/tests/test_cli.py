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
    """Returns a sorted list of stems from knowledge/projects/*.yaml."""
    projects = cli.list_known_projects()
    assert isinstance(projects, list)
    assert projects == sorted(projects), "list must be sorted"
    assert len(projects) > 0, "must find at least one project"
    # All items known at time of writing; spot-check a few
    assert "agents" in projects
    assert "buddy" in projects


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
    """--project typo + isatty=False → ActionError with known projects listed."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    (tmp_path / "alpha.yaml").write_text("")
    args = _args(project="typo-project")
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert 'unknown project "typo-project"' in str(e)
        assert "alpha" in str(e)


def test_resolve_cwd_projects_subdir(monkeypatch, tmp_path):
    """cwd = ~/projects/buddy/subdir → resolve_project returns 'buddy'."""
    buddy_sub = tmp_path / "projects" / "buddy" / "subdir"
    buddy_sub.mkdir(parents=True)
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.chdir(buddy_sub)
    args = _args()
    result = cli.resolve_project(args)
    assert result == "buddy"
