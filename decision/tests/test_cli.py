"""Tests for decision/cli.py — Obsidian decision-record mutation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import decision.cli as cli
from lib import obsidian_md
from lib import project_resolver as pr


# ---------- fixtures ----------

def _decision_md(decision_id: str, **overrides) -> str:
    """Render a minimal decision MD with the given frontmatter overrides."""
    fm = {
        "schema_version": 1,
        "id": decision_id,
        "date": "2026-01-01",
        "project": "testproj",
        "topic": "architecture",
        "title": f"{decision_id} title",
        "status": "proposed",
        "linked": {k: [] for k in cli.LINKED_FIELDS_ORDER},
        "created_at": "2026-01-01",
    }
    fm.update(overrides)
    body = (
        f"# {decision_id} — {fm['title']}\n\n"
        "## Context\nctx text\n\n"
        "## Decision\ndec text\n\n"
        "## Alternatives considered\n- A: y\n- B: z\n\n"
        "## Reasoning\nreas text\n\n"
        "## Outcome\n*(filled in later)*\n\n"
        "## Linked\n- Patterns: \n- PRs: \n- Issues: \n- Related decisions: \n"
    )
    return obsidian_md.dump(fm, body, field_order=cli.DECISION_FIELDS_ORDER)


def _wire_vaults(
    monkeypatch,
    tmp_path: Path,
    *,
    project: str = "testproj",
    decisions: dict[str, dict] | None = None,
    multi_vault: bool = False,
) -> dict[str, Path]:
    """Set up a vault layout with optional pre-existing decision files.

    Pass ``_vault`` in a decision's overrides dict to place it in a non-default
    vault (only takes effect when ``multi_vault=True``).

    Returns a dict mapping decision_id → its path on disk.
    """
    vaults_root = tmp_path / "vaults"
    main_vault = "TestVault"
    main_decisions = vaults_root / main_vault / "Decisions"
    main_decisions.mkdir(parents=True)

    paths: dict[str, Path] = {}
    if decisions:
        for did, overrides in decisions.items():
            target_dir = main_decisions
            if multi_vault and overrides.get("_vault"):
                target_dir = vaults_root / overrides["_vault"] / "Decisions"
                target_dir.mkdir(parents=True, exist_ok=True)
                overrides = {k: v for k, v in overrides.items() if k != "_vault"}
            path = target_dir / f"{did}.md"
            path.write_text(_decision_md(did, **overrides))
            paths[did] = path

    subs = {main_vault: {"subscribed": [project], "ssh_writes": []}}
    if multi_vault:
        subs["OtherVault"] = {"subscribed": ["other-proj"], "ssh_writes": []}
    subs_file = tmp_path / "subs.json"
    subs_file.write_text(json.dumps(subs))

    monkeypatch.setattr(pr, "VAULTS_BASE", vaults_root)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(cli, "resolve_with_picker", lambda n, no_prompt=False: project)
    return paths


def _read_fm(path: Path) -> dict:
    fm, _ = obsidian_md.load(path)
    return fm


def _read_body(path: Path) -> str:
    _, body = obsidian_md.load(path)
    return body


# ---------- view ----------

def test_view_renders_madr_sections(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {"title": "Use JWT"}})
    rc = cli.main(["D-042"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DECISION D-042" in out
    assert "Title:    Use JWT" in out
    assert "Context:" in out
    assert "ctx text" in out
    assert "dec text" in out
    assert "reas text" in out


def test_view_missing_errors(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path)
    rc = cli.main(["D-999"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_view_invalid_id_errors(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path)
    rc = cli.main(["bogus"])
    assert rc == 1
    assert "expected form D-NNN" in capsys.readouterr().err


# ---------- list ----------

def test_list_all(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path, decisions={
        "D-001": {"date": "2026-01-01"},
        "D-002": {"date": "2026-02-01"},
    })
    rc = cli.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-001" in out
    assert "D-002" in out
    # newest first
    assert out.index("D-002") < out.index("D-001")


def test_list_filter_by_project(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path, decisions={
        "D-001": {"project": "alpha"},
        "D-002": {"project": "beta"},
    })
    rc = cli.main(["--list", "--project", "alpha"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-001" in out
    assert "D-002" not in out


def test_list_filter_by_topic(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path, decisions={
        "D-001": {"topic": "auth"},
        "D-002": {"topic": "database"},
    })
    rc = cli.main(["--list", "--topic", "auth"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-001" in out
    assert "D-002" not in out


def test_list_empty(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path)
    rc = cli.main(["--list"])
    assert rc == 0
    assert "no decisions match" in capsys.readouterr().out


def test_list_aggregates_across_vaults(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path, multi_vault=True, decisions={
        "D-001": {},
        "D-002": {"_vault": "OtherVault"},
    })
    rc = cli.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "D-001" in out
    assert "D-002" in out


# ---------- new ----------

def test_new_assigns_next_id(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={
        "D-001": {}, "D-002": {}, "D-005": {},
    })
    rc = cli.main([
        "--new", "--title", "Next one",
        "--project", "testproj", "--topic", "architecture",
        "--decision", "do this", "--no-prompt",
    ])
    assert rc == 0
    new_path = paths["D-001"].parent / "D-006.md"
    assert new_path.exists()
    assert _read_fm(new_path)["id"] == "D-006"


def test_new_no_existing_files_assigns_d001(monkeypatch, tmp_path):
    _wire_vaults(monkeypatch, tmp_path)
    rc = cli.main([
        "--new", "--title", "First",
        "--project", "testproj", "--topic", "architecture",
        "--decision", "do this", "--no-prompt",
    ])
    assert rc == 0
    out_path = tmp_path / "vaults" / "TestVault" / "Decisions" / "D-001.md"
    assert out_path.exists()


def test_new_renders_madr_body_sections(monkeypatch, tmp_path):
    _wire_vaults(monkeypatch, tmp_path)
    rc = cli.main([
        "--new", "--title", "MADR test",
        "--project", "testproj", "--topic", "architecture",
        "--context", "the why",
        "--decision", "the what",
        "--reasoning", "the because",
        "--no-prompt",
    ])
    assert rc == 0
    out_path = tmp_path / "vaults" / "TestVault" / "Decisions" / "D-001.md"
    body = _read_body(out_path)
    assert obsidian_md.get_section(body, "Context").strip() == "the why"
    assert obsidian_md.get_section(body, "Decision").strip() == "the what"
    assert obsidian_md.get_section(body, "Reasoning").strip() == "the because"
    assert "filled in later" in obsidian_md.get_section(body, "Outcome")
    assert obsidian_md.has_section(body, "Alternatives considered")
    assert obsidian_md.has_section(body, "Linked")


def test_new_requires_title_and_decision(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path)
    rc = cli.main(["--new", "--title", "X", "--no-prompt"])
    assert rc == 1
    assert "requires --title and --decision" in capsys.readouterr().err


def test_new_no_prompt_requires_topic(monkeypatch, tmp_path, capsys):
    _wire_vaults(monkeypatch, tmp_path)
    rc = cli.main([
        "--new", "--title", "X", "--decision", "Y",
        "--project", "testproj", "--no-prompt",
    ])
    assert rc == 1
    assert "--topic required" in capsys.readouterr().err


def test_new_atomic_no_temp_left(monkeypatch, tmp_path):
    _wire_vaults(monkeypatch, tmp_path)
    cli.main([
        "--new", "--title", "X", "--decision", "Y",
        "--project", "testproj", "--topic", "architecture",
        "--no-prompt",
    ])
    decisions_dir = tmp_path / "vaults" / "TestVault" / "Decisions"
    assert not list(decisions_dir.glob("*.tmp*"))


def test_next_id_scans_across_vaults(monkeypatch, tmp_path):
    """Cross-vault uniqueness — counter advances past max in any vault."""
    _wire_vaults(monkeypatch, tmp_path, multi_vault=True, decisions={
        "D-005": {},
        "D-100": {"_vault": "OtherVault"},
    })
    assert cli.next_id() == "D-101"


# ---------- update ----------

def test_update_outcome_writes_to_body_section(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    rc = cli.main(["D-042", "--outcome", "Shipped 2026-05-01"])
    assert rc == 0
    body = _read_body(paths["D-042"])
    assert obsidian_md.get_section(body, "Outcome") == "Shipped 2026-05-01"


def test_update_add_pattern(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    rc = cli.main(["D-042", "--add-pattern", "pat-X"])
    assert rc == 0
    fm = _read_fm(paths["D-042"])
    assert "pat-X" in fm["linked"]["patterns"]


def test_update_add_pr_normalizes_hash(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    cli.main(["D-042", "--add-pr", "147"])
    cli.main(["D-042", "--add-pr", "#148"])
    prs = _read_fm(paths["D-042"])["linked"]["prs"]
    assert "#147" in prs
    assert "#148" in prs


def test_update_add_issue_keeps_hash(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    cli.main(["D-042", "--add-issue", "#42"])
    assert "#42" in _read_fm(paths["D-042"])["linked"]["issues"]


def test_update_add_related(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    cli.main(["D-042", "--add-related", "D-091"])
    assert "D-091" in _read_fm(paths["D-042"])["linked"]["related_decisions"]


def test_update_idempotent_on_dup(monkeypatch, tmp_path, capsys):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    cli.main(["D-042", "--add-pattern", "pat-X"])
    capsys.readouterr()
    rc = cli.main(["D-042", "--add-pattern", "pat-X"])
    assert rc == 0
    assert "no changes" in capsys.readouterr().out
    patterns = _read_fm(paths["D-042"])["linked"]["patterns"]
    assert patterns.count("pat-X") == 1


# ---------- frontmatter shape ----------

def test_field_order_preserved(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    cli.main(["D-042", "--add-pattern", "pat-X"])
    text = paths["D-042"].read_text()
    indices = [text.index(f"{k}:") for k in cli.DECISION_FIELDS_ORDER]
    assert indices == sorted(indices), "frontmatter field order broken"


def test_body_preserved_across_frontmatter_mutation(monkeypatch, tmp_path):
    paths = _wire_vaults(monkeypatch, tmp_path, decisions={"D-042": {}})
    original_body = _read_body(paths["D-042"])
    cli.main(["D-042", "--add-pattern", "pat-Y"])
    cli.main(["D-042", "--add-pr", "9"])
    assert _read_body(paths["D-042"]) == original_body


# ---------- argparse ----------

def test_parse_args_defaults():
    args = cli.parse_args(["D-042"])
    assert args.id == "D-042"
    assert args.list is False
    assert args.new is False
    assert args.outcome is None
