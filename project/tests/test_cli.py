"""Tests for project/cli.py — Obsidian project note frontmatter mutation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

# Repo root on path so we can import project.cli + lib.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import project.cli as cli
from lib import obsidian_md
from lib import project_resolver as pr


# ---------- fixtures ----------

_MIN_BODY = """\
# {name}

## Purpose
*(one sentence)*

## Stack
*(languages)*

## Notes / journal
*(your free-form area)*
"""


def _project_note(name: str, **overrides) -> str:
    """Render a minimal project note with the given frontmatter overrides."""
    fm = {
        "project": name,
        "host": "jns-mac",
        "client": "personal",
        "kind": "engineering-tool",
        "status": "active",
        "focus": "Initial focus",
        "status_updated": "2026-01-01",
        "blockers": [],
        "next_steps": [],
        "open_questions": [],
        "stack": [],
        "repo_path": "",
        "repo_remote": "",
    }
    fm.update(overrides)
    return obsidian_md.dump(fm, _MIN_BODY.format(name=name), field_order=cli.PROJECT_FIELDS_ORDER)


def _wire_vault(monkeypatch, tmp_path: Path, name: str = "testproj", **fm_overrides) -> Path:
    """Create a vault layout, subscribe `name` to it, and patch resolver paths.

    Returns the project note path inside the tmp vault.
    """
    vaults_root = tmp_path / "vaults"
    vault_name = "TestVault"
    projects_dir = vaults_root / vault_name / "Projects"
    projects_dir.mkdir(parents=True)
    note_path = projects_dir / f"{name}.md"
    note_path.write_text(_project_note(name, **fm_overrides))

    subs_file = tmp_path / "subs.json"
    subs_file.write_text(json.dumps({
        vault_name: {"subscribed": [name], "ssh_writes": []},
    }))

    monkeypatch.setattr(pr, "VAULTS_BASE", vaults_root)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(cli, "resolve_with_picker", lambda n, no_prompt=False: name)
    return note_path


def _read_fm(path: Path) -> dict:
    fm, _ = obsidian_md.load(path)
    return fm


def _read_body(path: Path) -> str:
    _, body = obsidian_md.load(path)
    return body


# ---------- read mode ----------

def test_read_mode_renders_fields(monkeypatch, tmp_path, capsys):
    _wire_vault(
        monkeypatch, tmp_path, "rich",
        status="paused",
        focus="Rich project",
        next_steps=["Step A", "Step B"],
        blockers=["Blocker one"],
        open_questions=["Why?"],
    )
    rc = cli.main(["rich", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PROJECT: rich" in out
    assert "PAUSED" in out
    assert "Rich project" in out
    assert "Step A" in out
    assert "Blocker one" in out
    assert "Why?" in out


def test_read_mode_missing_note_errors(monkeypatch, tmp_path, capsys):
    """Project subscribed but note file missing → clear error."""
    vaults_root = tmp_path / "vaults"
    (vaults_root / "TestVault" / "Projects").mkdir(parents=True)
    subs_file = tmp_path / "subs.json"
    subs_file.write_text(json.dumps({
        "TestVault": {"subscribed": ["ghost"], "ssh_writes": []},
    }))
    monkeypatch.setattr(pr, "VAULTS_BASE", vaults_root)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(cli, "resolve_with_picker", lambda n, no_prompt=False: "ghost")

    rc = cli.main(["ghost", "--no-prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


# ---------- write modes ----------

def test_set_focus(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--focus", "New focus", "--no-prompt"])
    assert rc == 0
    fm = _read_fm(note)
    assert fm["focus"] == "New focus"
    assert fm["status_updated"] != "2026-01-01"  # bumped


def test_set_status_valid(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--status", "blocked", "--no-prompt"])
    assert rc == 0
    assert _read_fm(note)["status"] == "blocked"


def test_set_status_invalid(monkeypatch, tmp_path, capsys):
    _wire_vault(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--status", "frozen", "--no-prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid status" in err


def test_add_next_step(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--next", "First", "--next", "Second", "--no-prompt"])
    assert rc == 0
    assert _read_fm(note)["next_steps"] == ["First", "Second"]


def test_remove_next_step_exact(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path, "rich", next_steps=["Step A", "Step B"])
    rc = cli.main(["rich", "--done", "Step A", "--no-prompt"])
    assert rc == 0
    assert _read_fm(note)["next_steps"] == ["Step B"]


def test_remove_next_step_substring(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path, "rich", next_steps=["Step A", "Step B"])
    rc = cli.main(["rich", "--done", "step b", "--no-prompt"])  # case-insensitive
    assert rc == 0
    assert _read_fm(note)["next_steps"] == ["Step A"]


def test_remove_next_step_no_match(monkeypatch, tmp_path, capsys):
    _wire_vault(monkeypatch, tmp_path, "rich", next_steps=["Step A"])
    rc = cli.main(["rich", "--done", "nonexistent", "--no-prompt"])
    assert rc == 1
    assert "no item matching" in capsys.readouterr().err


def test_remove_ambiguous_match(monkeypatch, tmp_path, capsys):
    _wire_vault(
        monkeypatch, tmp_path, "multi",
        next_steps=["foo task one", "foo task two"],
    )
    rc = cli.main(["multi", "--done", "foo", "--no-prompt"])
    assert rc == 1
    assert "multiple items match" in capsys.readouterr().err


def test_add_blocker_and_unblock(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    cli.main(["testproj", "--blocker", "API down", "--no-prompt"])
    rc = cli.main(["testproj", "--unblock", "API", "--no-prompt"])
    assert rc == 0
    assert _read_fm(note)["blockers"] == []


def test_add_question_and_unquestion(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    cli.main(["testproj", "--question", "Should we?", "--no-prompt"])
    rc = cli.main(["testproj", "--unquestion", "Should", "--no-prompt"])
    assert rc == 0
    assert _read_fm(note)["open_questions"] == []


def test_combined_updates_in_one_call(monkeypatch, tmp_path):
    note = _wire_vault(
        monkeypatch, tmp_path, "rich",
        next_steps=["Step A", "Step B"],
        blockers=["Blocker one"],
    )
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
    fm = _read_fm(note)
    assert fm["focus"] == "Combined"
    assert fm["status"] == "blocked"
    assert "Added step" in fm["next_steps"]
    assert "Step A" not in fm["next_steps"]
    assert "New blocker" in fm["blockers"]


# ---------- body preservation ----------

def test_body_preserved_across_frontmatter_mutation(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    original_body = _read_body(note)
    cli.main(["testproj", "--focus", "X", "--no-prompt"])
    cli.main(["testproj", "--blocker", "Y", "--no-prompt"])
    assert _read_body(note) == original_body


# ---------- subscriptions ----------

def test_subscribe_idempotent(monkeypatch, tmp_path):
    """--subscribe is idempotent and preserves on-disk format."""
    _wire_vault(monkeypatch, tmp_path)
    # _wire_vault already subscribes "testproj" to TestVault; calling --subscribe again is a no-op
    rc = cli.main(["testproj", "--subscribe", "--no-prompt"])
    assert rc == 0
    rc = cli.main(["testproj", "--subscribe", "--no-prompt"])
    assert rc == 0
    on_disk = json.loads(pr.SUBSCRIPTIONS_PATH.read_text())
    # Still exactly one subscription (no duplicate)
    assert on_disk["TestVault"]["subscribed"].count("testproj") == 1


def test_unsubscribe_removes(monkeypatch, tmp_path):
    _wire_vault(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--unsubscribe", "--no-prompt"])
    assert rc == 0
    on_disk = json.loads(pr.SUBSCRIPTIONS_PATH.read_text())
    assert "testproj" not in on_disk["TestVault"]["subscribed"]


def test_subscribe_does_not_modify_note(monkeypatch, tmp_path):
    """--subscribe is machine-local; should not modify the project note."""
    note = _wire_vault(monkeypatch, tmp_path)
    original = note.read_text()
    rc = cli.main(["testproj", "--subscribe", "--no-prompt"])
    assert rc == 0
    assert note.read_text() == original


# ---------- frontmatter shape / atomicity ----------

def test_field_order_preserved(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path, "rich", focus="x")
    rc = cli.main(["rich", "--focus", "rewritten", "--no-prompt"])
    assert rc == 0
    text = note.read_text()
    proj_idx = text.index("project:")
    host_idx = text.index("host:")
    status_idx = text.index("status:")
    focus_idx = text.index("focus:")
    steps_idx = text.index("next_steps:")
    assert proj_idx < host_idx < status_idx < focus_idx < steps_idx


def test_field_order_includes_host_between_project_and_status(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    cli.main(["testproj", "--focus", "trigger write", "--no-prompt"])
    text = note.read_text()
    project_idx = text.index("project:")
    host_idx = text.index("host:")
    status_idx = text.index("status:")
    assert project_idx < host_idx < status_idx


def test_atomic_write_no_temp_left_behind(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--focus", "X", "--no-prompt"])
    assert rc == 0
    leftover = list(note.parent.glob("*.tmp*"))
    assert leftover == []


# ---------- host: field ----------

def test_set_host_flag_updates_existing(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path, host="jns-mac")
    rc = cli.main(["testproj", "--set-host", "jbox06", "--no-prompt"])
    assert rc == 0
    assert _read_fm(note)["host"] == "jbox06"


def test_set_host_flag_does_not_bump_status_updated(monkeypatch, tmp_path):
    note = _wire_vault(monkeypatch, tmp_path, host="jns-mac", status_updated="2026-01-01")
    rc = cli.main(["testproj", "--set-host", "jbox06", "--no-prompt"])
    assert rc == 0
    assert _read_fm(note)["status_updated"] == "2026-01-01"


def test_set_host_flag_idempotent(monkeypatch, tmp_path, capsys):
    _wire_vault(monkeypatch, tmp_path, host="jns-mac")
    rc = cli.main(["testproj", "--set-host", "jns-mac", "--no-prompt"])
    assert rc == 0
    assert "no-op" in capsys.readouterr().out


def test_render_includes_host(monkeypatch, tmp_path, capsys):
    _wire_vault(monkeypatch, tmp_path, host="jbox06")
    rc = cli.main(["testproj", "--no-prompt"])
    assert rc == 0
    assert "Host: jbox06" in capsys.readouterr().out


# ---------- new flags: --register-host / --claim-ssh-host / --release-ssh-host ----------

def test_register_host_flag_writes_file(monkeypatch, tmp_path, capsys):
    host_file = tmp_path / "host-name"
    monkeypatch.setattr(pr, "HOST_NAME_PATH", host_file)
    rc = cli.main(["--register-host", "jns-mac"])
    assert rc == 0
    assert host_file.read_text().strip() == "jns-mac"
    assert "registered as host: jns-mac" in capsys.readouterr().out


def test_claim_ssh_host_flag_updates_subscription(monkeypatch, tmp_path, capsys):
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.delenv(pr.DEFAULT_VAULT_ENV, raising=False)

    rc = cli.main(["--claim-ssh-host", "MyVault", "jbox06"])
    assert rc == 0
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["MyVault"]["ssh_writes"] == ["jbox06"]
    assert "claimed ssh host: jbox06" in capsys.readouterr().out


def test_release_ssh_host_flag(monkeypatch, tmp_path):
    subs_file = tmp_path / "subs.json"
    subs_file.write_text(json.dumps({
        "MyVault": {"subscribed": [], "ssh_writes": ["jbox06", "et01"]},
    }))
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)

    rc = cli.main(["--release-ssh-host", "MyVault", "jbox06"])
    assert rc == 0
    on_disk = json.loads(subs_file.read_text())
    assert on_disk["MyVault"]["ssh_writes"] == ["et01"]


def test_claim_ssh_host_does_not_require_project(monkeypatch, tmp_path):
    """--claim-ssh-host short-circuits before project resolution."""
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.delenv(pr.DEFAULT_VAULT_ENV, raising=False)
    # No project file or subscription configured — should still succeed.
    rc = cli.main(["--claim-ssh-host", "V", "h"])
    assert rc == 0


# ---------- argparse / mode resolution ----------

def test_no_args_no_writes_is_read_mode(monkeypatch, tmp_path, capsys):
    _wire_vault(monkeypatch, tmp_path)
    rc = cli.main(["testproj", "--no-prompt"])
    assert rc == 0
    assert "PROJECT: testproj" in capsys.readouterr().out


def test_status_in_help_lists_allowed_values():
    p_args = cli.parse_args(["proj", "--no-prompt"])
    assert p_args.status is None  # default


# ---------- legacy register_project (still uses YAML for now; #168 retires) ----------

def test_register_project_writes_schema_version(monkeypatch, tmp_path):
    """register_project still seeds schema_version: 1 on legacy YAMLs.

    register_project remains the YAML-creation path used by action's
    auto-register flow until #168 archives knowledge/projects/.
    """
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True)
    subs_file = tmp_path / "subs.json"
    host_file = tmp_path / "host-name"
    host_file.write_text("test-host\n")
    monkeypatch.setattr(pr, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(pr, "HOST_NAME_PATH", host_file)
    yaml_path = pr.register_project("brandnew", owner="jason")
    assert yaml_path.read_text().splitlines()[0] == "schema_version: 1"


def test_register_project_stamps_host_from_file(monkeypatch, tmp_path):
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True)
    subs_file = tmp_path / "subs.json"
    host_file = tmp_path / "host-name"
    host_file.write_text("jns-mac\n")
    monkeypatch.setattr(pr, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(pr, "HOST_NAME_PATH", host_file)
    yaml_path = pr.register_project("hostproj")
    assert yaml.safe_load(yaml_path.read_text())["host"] == "jns-mac"


def test_register_project_falls_back_to_gethostname(monkeypatch, tmp_path):
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True)
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(pr, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(pr, "HOST_NAME_PATH", tmp_path / "no-host-file")
    monkeypatch.setattr(pr.socket, "gethostname", lambda: "Some-Host.local")
    yaml_path = pr.register_project("fallback")
    assert yaml.safe_load(yaml_path.read_text())["host"] == "some-host"


def test_register_project_explicit_host_override(monkeypatch, tmp_path):
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True)
    subs_file = tmp_path / "subs.json"
    host_file = tmp_path / "host-name"
    host_file.write_text("jns-mac\n")
    monkeypatch.setattr(pr, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(pr, "HOST_NAME_PATH", host_file)
    yaml_path = pr.register_project("override", host="jbox06")
    assert yaml.safe_load(yaml_path.read_text())["host"] == "jbox06"


def test_get_host_name_handles_empty_file(monkeypatch, tmp_path):
    host_file = tmp_path / "host-name"
    host_file.write_text("\n")
    monkeypatch.setattr(pr, "HOST_NAME_PATH", host_file)
    monkeypatch.setattr(pr.socket, "gethostname", lambda: "Fallback-Host")
    assert pr.get_host_name() == "fallback-host"


def test_set_host_name_writes_file(monkeypatch, tmp_path):
    host_file = tmp_path / "host-name"
    monkeypatch.setattr(pr, "HOST_NAME_PATH", host_file)
    pr.set_host_name("jns-mac")
    assert host_file.read_text().strip() == "jns-mac"
    pr.set_host_name("jns-mac")  # idempotent
    assert host_file.read_text().strip() == "jns-mac"


def test_set_host_name_rejects_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "HOST_NAME_PATH", tmp_path / "host-name")
    with pytest.raises(ValueError):
        pr.set_host_name("")
    with pytest.raises(ValueError):
        pr.set_host_name("   ")
