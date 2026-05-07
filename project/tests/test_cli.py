"""Tests for project/cli.py — view/update project YAML."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

# Repo root on path so we can import project.cli + lib.project_resolver
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import project.cli as cli


# ---------- fixtures ----------

_MIN_YAML = """\
project: testproj
status: active
focus: Initial focus
next_steps: []
blockers: []
open_questions: []
specs: []
dependencies: []
updated_at: '2026-01-01'
updated_by: jason
"""


_RICH_YAML = """\
project: rich
status: paused
focus: Rich project
next_steps:
  - Step A
  - Step B
blockers:
  - Blocker one
open_questions:
  - Why?
specs: []
dependencies: []
updated_at: '2026-01-01'
updated_by: jason
"""


def _patch_resolver(monkeypatch, tmp_path: Path, name: str = "testproj", yaml_content: str = _MIN_YAML):
    """Wire resolve_with_picker + YAML path to a tmp project. Returns the YAML path."""
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True)
    yaml_path = projects_dir / f"{name}.yaml"
    yaml_path.write_text(yaml_content)
    subs_file = tmp_path / "subs.json"

    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    # Resolve_with_picker delegates to lib; just stub it to return the name.
    monkeypatch.setattr(cli, "resolve_with_picker", lambda n, no_prompt=False: name)
    monkeypatch.setattr(cli, "project_yaml_path", lambda n: yaml_path)
    return yaml_path


# ---------- read mode ----------

def test_read_mode_renders_fields(monkeypatch, tmp_path, capsys):
    _patch_resolver(monkeypatch, tmp_path, "rich", _RICH_YAML)
    rc = cli.main(["rich", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PROJECT: rich" in out
    assert "PAUSED" in out
    assert "Rich project" in out
    assert "Step A" in out
    assert "Blocker one" in out
    assert "Why?" in out


def test_read_mode_missing_yaml_errors(monkeypatch, tmp_path, capsys):
    name = "ghost"
    monkeypatch.setattr(cli, "resolve_with_picker", lambda n, no_prompt=False: name)
    monkeypatch.setattr(cli, "project_yaml_path", lambda n: tmp_path / f"{n}.yaml")
    rc = cli.main(["ghost", "--no-prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


# ---------- write modes ----------

def test_set_focus(monkeypatch, tmp_path, capsys):
    yaml_path = _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--focus", "New focus", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["focus"] == "New focus"
    assert data["updated_at"] != "2026-01-01"  # bumped


def test_set_status_valid(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--status", "blocked", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["status"] == "blocked"


def test_set_status_invalid(monkeypatch, tmp_path, capsys):
    _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--status", "frozen", "--no-prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid status" in err


def test_add_next_step(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--next", "First step", "--next", "Second step", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["next_steps"] == ["First step", "Second step"]


def test_remove_next_step_exact(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path, "rich", _RICH_YAML)
    rc = cli.main(["rich", "--done", "Step A", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["next_steps"] == ["Step B"]


def test_remove_next_step_substring(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path, "rich", _RICH_YAML)
    rc = cli.main(["rich", "--done", "step b", "--no-prompt"])  # case-insensitive substring
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["next_steps"] == ["Step A"]


def test_remove_next_step_no_match(monkeypatch, tmp_path, capsys):
    _patch_resolver(monkeypatch, tmp_path, "rich", _RICH_YAML)
    rc = cli.main(["rich", "--done", "nonexistent", "--no-prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no item matching" in err


def test_remove_ambiguous_match(monkeypatch, tmp_path, capsys):
    multi_yaml = """\
project: multi
status: active
focus: ''
next_steps:
  - foo task one
  - foo task two
blockers: []
open_questions: []
specs: []
dependencies: []
updated_at: '2026-01-01'
updated_by: jason
"""
    _patch_resolver(monkeypatch, tmp_path, "multi", multi_yaml)
    rc = cli.main(["multi", "--done", "foo", "--no-prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "multiple items match" in err


def test_add_blocker_and_unblock(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--blocker", "API down", "--no-prompt"])
    assert rc == 0
    rc = cli.main(["testproj", "--unblock", "API", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["blockers"] == []


def test_add_question_and_unquestion(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--question", "Should we?", "--no-prompt"])
    assert rc == 0
    rc = cli.main(["testproj", "--unquestion", "Should", "--no-prompt"])
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["open_questions"] == []


def test_combined_updates_in_one_call(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path, "rich", _RICH_YAML)
    rc = cli.main([
        "rich",
        "--focus", "Combined",
        "--status", "blocked",
        "--next", "Added step",
        "--done", "Step A",
        "--blocker", "New blocker",
        "--no-prompt",
    ])
    assert rc == 0
    data = yaml.safe_load(yaml_path.read_text())
    assert data["focus"] == "Combined"
    assert data["status"] == "blocked"
    assert "Added step" in data["next_steps"]
    assert "Step A" not in data["next_steps"]
    assert "New blocker" in data["blockers"]


# ---------- subscriptions ----------

def test_subscribe_idempotent(monkeypatch, tmp_path):
    _patch_resolver(monkeypatch, tmp_path)
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    rc = cli.main(["testproj", "--subscribe", "--no-prompt"])
    assert rc == 0
    rc = cli.main(["testproj", "--subscribe", "--no-prompt"])  # second call no-ops
    assert rc == 0
    data = json.loads(subs_file.read_text())
    assert data["subscribed"] == ["testproj"]


def test_unsubscribe_removes(monkeypatch, tmp_path):
    _patch_resolver(monkeypatch, tmp_path)
    subs_file = tmp_path / "subs.json"
    subs_file.write_text(json.dumps({"subscribed": ["testproj", "other"]}))
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    rc = cli.main(["testproj", "--unsubscribe", "--no-prompt"])
    assert rc == 0
    data = json.loads(subs_file.read_text())
    assert "testproj" not in data["subscribed"]
    assert "other" in data["subscribed"]


def test_subscribe_does_not_bump_updated_at(monkeypatch, tmp_path):
    """--subscribe is machine-local; should not modify the project YAML."""
    yaml_path = _patch_resolver(monkeypatch, tmp_path)
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    original_text = yaml_path.read_text()
    rc = cli.main(["testproj", "--subscribe", "--no-prompt"])
    assert rc == 0
    assert yaml_path.read_text() == original_text


# ---------- YAML round-trip safety ----------

def test_field_order_preserved(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path, "rich", _RICH_YAML)
    rc = cli.main(["rich", "--focus", "rewritten", "--no-prompt"])
    assert rc == 0
    text = yaml_path.read_text()
    # Field order: project comes before status, before focus, before next_steps...
    proj_idx = text.index("project:")
    status_idx = text.index("status:")
    focus_idx = text.index("focus:")
    steps_idx = text.index("next_steps:")
    assert proj_idx < status_idx < focus_idx < steps_idx


def test_atomic_write_no_temp_left_behind(monkeypatch, tmp_path):
    yaml_path = _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--focus", "X", "--no-prompt"])
    assert rc == 0
    leftover = list(yaml_path.parent.glob("*.tmp*"))
    assert leftover == []


# ---------- argparse / mode resolution ----------

def test_no_args_no_writes_is_read_mode(monkeypatch, tmp_path, capsys):
    _patch_resolver(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PROJECT: testproj" in out


def test_status_in_help_lists_allowed_values():
    """argparse --help should mention the allowed statuses."""
    p_args = cli.parse_args(["proj", "--no-prompt"])
    assert p_args.status is None  # default
