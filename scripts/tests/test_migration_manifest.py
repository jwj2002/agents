"""Tests for scripts/migration-manifest.py (#165)."""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest


# Load the hyphen-named script as a module so we can test its functions.
_SCRIPT = Path(__file__).resolve().parent.parent / "migration-manifest.py"
_spec = importlib.util.spec_from_file_location("migration_manifest", _SCRIPT)
mm = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mm)


# ---------- fixtures ----------

_FULL_PROJECT_YAML = """\
schema_version: 1
project: testproj
host: jns-mac
status: active
focus: Some focus statement
next_steps:
  - first step
  - second step
blockers: []
open_questions:
  - a question
specs: []
dependencies: []
updated_at: 2026-05-08
updated_by: jason
"""

_PARTIAL_PROJECT_YAML = """\
project: minimal
status: active
focus: just the basics
"""

_DECISION_YAML = """\
schema_version: 1
id: D-001
date: '2026-01-01'
project: testproj
topic: architecture
title: A test decision
context: ctx
decision: dec
"""


@pytest.fixture
def fixture_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Create temp projects/ and decisions/ dirs with sample YAMLs."""
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "testproj.yaml").write_text(_FULL_PROJECT_YAML)
    (projects / "minimal.yaml").write_text(_PARTIAL_PROJECT_YAML)

    decisions = tmp_path / "decisions"
    decisions.mkdir()
    (decisions / "D-001.yaml").write_text(_DECISION_YAML)
    (decisions / "D-002.yaml").write_text(_DECISION_YAML.replace("D-001", "D-002"))

    return projects, decisions


# ---------- happy path ----------

def test_render_includes_every_project_and_decision(fixture_dirs):
    projects_dir, decisions_dir = fixture_dirs
    projects = mm.load_project_yamls(projects_dir)
    decisions = mm.load_decision_yamls(decisions_dir)
    out = mm.render_manifest(projects, decisions, dt.date(2026, 5, 8))

    assert "Path B Migration Manifest — 2026-05-08" in out
    assert "## Projects (2)" in out
    assert "## Decisions (2 — archive-only)" in out
    assert "`testproj.yaml` → `<vault>/Projects/testproj.md`" in out
    assert "`minimal.yaml` → `<vault>/Projects/minimal.md`" in out
    assert "`D-001.yaml`" in out
    assert "`D-002.yaml`" in out


def test_field_mapping_renders_correctly(fixture_dirs):
    projects_dir, _ = fixture_dirs
    projects = mm.load_project_yamls(projects_dir)
    out = mm.render_manifest(projects, [], dt.date(2026, 5, 8))

    # 1:1 fields
    assert "| `project` | `project` |" in out
    assert "| `host` | `host` |" in out
    # Renamed field
    assert "| `updated_at` | `status_updated` |" in out
    assert "renamed → `status_updated`" in out
    # Dropped fields
    assert "| `schema_version` | — |" in out
    assert "| `updated_by` | — |" in out
    assert "**dropped** (no destination)" in out


def test_destination_only_fields_listed_per_project(fixture_dirs):
    projects_dir, _ = fixture_dirs
    projects = mm.load_project_yamls(projects_dir)
    out = mm.render_manifest(projects, [], dt.date(2026, 5, 8))

    # Each project section should mention every destination-only field.
    for field in mm.DESTINATION_ONLY_FIELDS:
        # At least once per project (2 projects → at least 2 occurrences)
        assert out.count(f"- `{field}`") >= 2


# ---------- idempotency ----------

def test_idempotent_same_date(fixture_dirs):
    projects_dir, decisions_dir = fixture_dirs
    projects = mm.load_project_yamls(projects_dir)
    decisions = mm.load_decision_yamls(decisions_dir)
    a = mm.render_manifest(projects, decisions, dt.date(2026, 5, 8))
    b = mm.render_manifest(projects, decisions, dt.date(2026, 5, 8))
    assert a == b


# ---------- error handling ----------

def test_malformed_yaml_errors_clearly(tmp_path: Path):
    projects = tmp_path / "projects"
    projects.mkdir()
    bad = projects / "broken.yaml"
    bad.write_text("project: testproj\n  bad: indent: here\n: : :\n")

    with pytest.raises(mm.ManifestError, match="broken.yaml"):
        mm.load_project_yamls(projects)


def test_missing_directory_errors(tmp_path: Path):
    with pytest.raises(mm.ManifestError, match="not found"):
        mm.load_project_yamls(tmp_path / "does-not-exist")


def test_top_level_non_mapping_rejected(tmp_path: Path):
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "list.yaml").write_text("- just\n- a\n- list\n")
    with pytest.raises(mm.ManifestError, match="expected mapping"):
        mm.load_project_yamls(projects)


# ---------- reviewer-action signal ----------

def test_unknown_source_field_flagged(tmp_path: Path):
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "weird.yaml").write_text(
        "project: weird\nstatus: active\nfocus: x\nmystery_field: surprise\n"
    )
    out = mm.render_manifest(
        mm.load_project_yamls(projects), [], dt.date(2026, 5, 8)
    )
    assert "⚠ Unknown source fields" in out
    assert "mystery_field" in out
    assert "surprise" in out


# ---------- end-to-end via main() ----------

def test_main_writes_output_file(fixture_dirs, tmp_path: Path):
    projects_dir, decisions_dir = fixture_dirs
    output = tmp_path / "manifest.md"
    rc = mm.main([
        "--projects-dir", str(projects_dir),
        "--decisions-dir", str(decisions_dir),
        "--output", str(output),
        "--date", "2026-05-08",
    ])
    assert rc == 0
    assert output.exists()
    assert "Path B Migration Manifest — 2026-05-08" in output.read_text()


def test_main_returns_nonzero_on_error(tmp_path: Path):
    rc = mm.main([
        "--projects-dir", str(tmp_path / "missing"),
        "--decisions-dir", str(tmp_path / "missing"),
        "--output", str(tmp_path / "out.md"),
        "--date", "2026-05-08",
    ])
    assert rc == 2
