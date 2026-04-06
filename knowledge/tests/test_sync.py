"""Tests for knowledge/sync.py."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Ensure the knowledge package is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sync import (
    DB_PATH,
    _connect,
    _init_schema,
    _now_iso,
    cmd_build,
    cmd_export,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent  # knowledge/


def _seed_dir(tmp_path: Path) -> Path:
    """Copy seed YAML + schema into a temp directory structure."""
    dest = tmp_path / "knowledge"
    dest.mkdir()

    # Copy schema
    shutil.copy(FIXTURES_DIR / "schema.sql", dest / "schema.sql")

    # Copy patterns
    pat_dir = dest / "patterns"
    pat_dir.mkdir()
    for f in (FIXTURES_DIR / "patterns").glob("*.yaml"):
        shutil.copy(f, pat_dir / f.name)

    # Copy decisions
    dec_dir = dest / "decisions"
    dec_dir.mkdir()
    for f in (FIXTURES_DIR / "decisions").glob("*.yaml"):
        if f.name != "index.yaml":
            shutil.copy(f, dec_dir / f.name)

    # Copy learning rules (individual files)
    lr_dir = dest / "learning-rules"
    lr_dir.mkdir()
    for f in (FIXTURES_DIR / "learning-rules").glob("*.yaml"):
        shutil.copy(f, lr_dir / f.name)

    # Copy velocity (individual files)
    vel_dir = dest / "velocity"
    vel_dir.mkdir()
    for f in (FIXTURES_DIR / "velocity").glob("*.yaml"):
        shutil.copy(f, vel_dir / f.name)

    return dest


def _build_paths(base: Path) -> dict:
    """Return keyword arguments for cmd_build pointing at temp dir."""
    return dict(
        db_path=base / "knowledge.db",
        schema_path=base / "schema.sql",
        patterns_dir=base / "patterns",
        decisions_dir=base / "decisions",
        rules_dir=base / "learning-rules",
        velocity_dir=base / "velocity",
    )


# -----------------------------------------------------------------------
# test_build_creates_db
# -----------------------------------------------------------------------

def test_build_creates_db(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)
    counts = cmd_build(**paths)

    db = paths["db_path"]
    assert db.exists()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    # Verify row counts match what's on disk
    n_patterns = conn.execute("SELECT COUNT(*) as c FROM patterns").fetchone()["c"]
    n_decisions = conn.execute("SELECT COUNT(*) as c FROM decisions").fetchone()["c"]
    n_rules = conn.execute("SELECT COUNT(*) as c FROM learning_rules").fetchone()["c"]
    n_velocity = conn.execute("SELECT COUNT(*) as c FROM velocity").fetchone()["c"]

    assert n_patterns == counts["patterns"]
    assert n_decisions == counts["decisions"]
    assert n_rules == counts["rules"]
    assert n_velocity == counts["velocity"]

    # Verify we got realistic counts from seed data
    assert n_patterns >= 1
    assert n_decisions >= 1
    assert n_rules >= 1
    assert n_velocity >= 1

    conn.close()


# -----------------------------------------------------------------------
# test_build_validates_required_fields
# -----------------------------------------------------------------------

def test_build_validates_required_fields(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    # Write a pattern missing 'tier'
    bad_pattern = base / "patterns" / "bad-missing-tier.yaml"
    bad_pattern.write_text(yaml.dump({
        "id": "PAT-BAD",
        "category": "test",
        "name": "Bad pattern",
        "status": "draft",
        # missing 'tier'
    }))

    counts = cmd_build(**paths)

    conn = sqlite3.connect(str(paths["db_path"]))
    row = conn.execute("SELECT * FROM patterns WHERE id = 'PAT-BAD'").fetchone()
    assert row is None, "Pattern missing required field should be skipped"
    conn.close()


# -----------------------------------------------------------------------
# test_build_validates_enum_values
# -----------------------------------------------------------------------

def test_build_validates_enum_values(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    # Write pattern with invalid status
    bad = base / "patterns" / "bad-status.yaml"
    bad.write_text(yaml.dump({
        "id": "PAT-BADSTATUS",
        "category": "test",
        "name": "Bad status",
        "status": "invalid_status",
        "tier": "primary",
    }))

    # Write pattern with invalid tier
    bad2 = base / "patterns" / "bad-tier.yaml"
    bad2.write_text(yaml.dump({
        "id": "PAT-BADTIER",
        "category": "test",
        "name": "Bad tier",
        "status": "draft",
        "tier": "tertiary",
    }))

    counts = cmd_build(**paths)

    conn = sqlite3.connect(str(paths["db_path"]))
    row1 = conn.execute("SELECT * FROM patterns WHERE id = 'PAT-BADSTATUS'").fetchone()
    row2 = conn.execute("SELECT * FROM patterns WHERE id = 'PAT-BADTIER'").fetchone()
    assert row1 is None, "Pattern with invalid status should be skipped"
    assert row2 is None, "Pattern with invalid tier should be skipped"
    conn.close()


# -----------------------------------------------------------------------
# test_build_detects_duplicate_ids
# -----------------------------------------------------------------------

def test_build_detects_duplicate_ids(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    # Create a duplicate decision with same ID as D-015
    dup = base / "decisions" / "D-015-dup.yaml"
    dup.write_text(yaml.dump({
        "id": "D-015",
        "topic": "duplicate",
        "title": "Duplicate decision",
        "decision": "This is a duplicate",
        "created_at": "2026-04-06",
    }))

    counts = cmd_build(**paths)

    conn = sqlite3.connect(str(paths["db_path"]))
    conn.row_factory = sqlite3.Row
    # Only one D-015 should exist (the first one alphabetically)
    rows = conn.execute("SELECT COUNT(*) as c FROM decisions WHERE id = 'D-015'").fetchone()
    assert rows["c"] == 1
    conn.close()


# -----------------------------------------------------------------------
# test_build_regenerates_index
# -----------------------------------------------------------------------

def test_build_regenerates_index(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    # Remove any existing index
    index_path = base / "decisions" / "index.yaml"
    if index_path.exists():
        index_path.unlink()

    cmd_build(**paths)

    assert index_path.exists(), "index.yaml should be regenerated"

    with open(index_path) as f:
        index = yaml.safe_load(f)

    assert "by_project" in index
    assert "by_topic" in index
    assert "by_pattern" in index

    # Verify all decision IDs appear somewhere
    conn = sqlite3.connect(str(paths["db_path"]))
    all_ids = {
        row[0] for row in conn.execute("SELECT id FROM decisions").fetchall()
    }
    conn.close()

    # Every decision with a project should appear in by_project
    index_ids = set()
    for project, entries in index["by_project"].items():
        for entry in entries:
            index_ids.add(entry["id"])

    # All decisions with projects should be indexed
    assert index_ids == all_ids or index_ids.issubset(all_ids)


# -----------------------------------------------------------------------
# test_build_populates_fts
# -----------------------------------------------------------------------

def test_build_populates_fts(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    cmd_build(**paths)

    conn = sqlite3.connect(str(paths["db_path"]))

    # Search for a term we know exists in the seed decisions
    results = conn.execute(
        "SELECT id FROM decisions_fts WHERE decisions_fts MATCH 'JWT'"
    ).fetchall()
    assert len(results) >= 1, "FTS should find 'JWT' in decisions"

    # Search for another term
    results = conn.execute(
        "SELECT id FROM decisions_fts WHERE decisions_fts MATCH 'Redis'"
    ).fetchall()
    assert len(results) >= 1, "FTS should find 'Redis' in decisions"

    conn.close()


# -----------------------------------------------------------------------
# test_export_writes_new_records
# -----------------------------------------------------------------------

def test_export_writes_new_records(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    cmd_build(**paths)

    # Insert a new decision directly into SQLite
    conn = sqlite3.connect(str(paths["db_path"]))
    conn.execute(
        """INSERT INTO decisions
           (id, topic, title, decision, project, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("D-999", "test", "Test export", "Export this decision", "testproject", _now_iso()),
    )
    conn.commit()
    conn.close()

    # Export with no last_export set -> should export all
    cmd_export(
        db_path=paths["db_path"],
        patterns_dir=paths["patterns_dir"],
        decisions_dir=paths["decisions_dir"],
        rules_dir=paths["rules_dir"],
        velocity_dir=paths["velocity_dir"],
    )

    exported = base / "decisions" / "D-999.yaml"
    assert exported.exists(), "New decision should be exported to YAML"

    with open(exported) as f:
        data = yaml.safe_load(f)
    assert data["id"] == "D-999"
    assert data["title"] == "Test export"


# -----------------------------------------------------------------------
# test_export_skips_old_records
# -----------------------------------------------------------------------

def test_export_skips_old_records(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    cmd_build(**paths)

    # Set last_export to now
    conn = sqlite3.connect(str(paths["db_path"]))
    conn.execute(
        "INSERT OR REPLACE INTO _meta (key, value) VALUES ('last_export', ?)",
        (_now_iso(),),
    )
    # Insert a decision with old created_at (before last_export)
    conn.execute(
        """INSERT INTO decisions
           (id, topic, title, decision, project, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("D-OLD", "test", "Old decision", "Should not export", "testproject", "2020-01-01"),
    )
    conn.commit()
    conn.close()

    # Remove any existing D-OLD.yaml to be sure
    old_file = base / "decisions" / "D-OLD.yaml"
    if old_file.exists():
        old_file.unlink()

    cmd_export(
        db_path=paths["db_path"],
        patterns_dir=paths["patterns_dir"],
        decisions_dir=paths["decisions_dir"],
        rules_dir=paths["rules_dir"],
        velocity_dir=paths["velocity_dir"],
    )

    assert not old_file.exists(), "Old record should not be exported"


# -----------------------------------------------------------------------
# test_export_updates_meta_timestamp
# -----------------------------------------------------------------------

def test_export_updates_meta_timestamp(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    cmd_build(**paths)

    cmd_export(
        db_path=paths["db_path"],
        patterns_dir=paths["patterns_dir"],
        decisions_dir=paths["decisions_dir"],
        rules_dir=paths["rules_dir"],
        velocity_dir=paths["velocity_dir"],
    )

    conn = sqlite3.connect(str(paths["db_path"]))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT value FROM _meta WHERE key = 'last_export'").fetchone()
    assert row is not None, "_meta.last_export should be set after export"
    assert len(row["value"]) > 0
    conn.close()


# -----------------------------------------------------------------------
# test_sync_order_export_before_build
# -----------------------------------------------------------------------

def test_sync_order_export_before_build(tmp_path: Path) -> None:
    """Verify that SQLite-only records survive a sync cycle.

    Simulates: insert a record into SQLite -> sync (export then build).
    The record should appear as a YAML file after export, and survive
    the subsequent build (which reads from YAML).
    """
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    # Initial build
    cmd_build(**paths)

    # Insert a SQLite-only decision
    conn = sqlite3.connect(str(paths["db_path"]))
    conn.execute(
        """INSERT INTO decisions
           (id, topic, title, decision, project, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("D-SQLITE", "test", "SQLite-only", "Created in DB only", "testproject", _now_iso()),
    )
    conn.commit()
    conn.close()

    # Simulate sync: export first, then build
    cmd_export(
        db_path=paths["db_path"],
        patterns_dir=paths["patterns_dir"],
        decisions_dir=paths["decisions_dir"],
        rules_dir=paths["rules_dir"],
        velocity_dir=paths["velocity_dir"],
    )

    # Verify YAML was written
    yaml_file = base / "decisions" / "D-SQLITE.yaml"
    assert yaml_file.exists(), "Export should write SQLite-only record to YAML"

    # Now rebuild (simulating the build step of sync)
    cmd_build(**paths)

    # Verify the record survived the rebuild
    conn = sqlite3.connect(str(paths["db_path"]))
    row = conn.execute("SELECT * FROM decisions WHERE id = 'D-SQLITE'").fetchone()
    assert row is not None, "SQLite-only record should survive export->build cycle"
    conn.close()


# -----------------------------------------------------------------------
# test_export_idempotent
# -----------------------------------------------------------------------

def test_export_idempotent(tmp_path: Path) -> None:
    """Verify export -> build -> export -> build produces stable file counts."""
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    # First cycle
    cmd_build(**paths)
    cmd_export(
        db_path=paths["db_path"],
        patterns_dir=paths["patterns_dir"],
        decisions_dir=paths["decisions_dir"],
        rules_dir=paths["rules_dir"],
        velocity_dir=paths["velocity_dir"],
    )

    # Count files after first export
    vel_count_1 = len(list((base / "velocity").glob("*.yaml")))
    lr_count_1 = len(list((base / "learning-rules").glob("*.yaml")))

    # Second cycle
    cmd_build(**paths)
    cmd_export(
        db_path=paths["db_path"],
        patterns_dir=paths["patterns_dir"],
        decisions_dir=paths["decisions_dir"],
        rules_dir=paths["rules_dir"],
        velocity_dir=paths["velocity_dir"],
    )

    vel_count_2 = len(list((base / "velocity").glob("*.yaml")))
    lr_count_2 = len(list((base / "learning-rules").glob("*.yaml")))

    assert vel_count_1 == vel_count_2, f"Velocity files grew: {vel_count_1} -> {vel_count_2}"
    assert lr_count_1 == lr_count_2, f"Learning rule files grew: {lr_count_1} -> {lr_count_2}"

    # Third cycle for good measure
    cmd_build(**paths)
    vel_count_3 = len(list((base / "velocity").glob("*.yaml")))
    assert vel_count_2 == vel_count_3, f"Velocity files grew after rebuild: {vel_count_2} -> {vel_count_3}"


# -----------------------------------------------------------------------
# test_malformed_yaml_skipped
# -----------------------------------------------------------------------

def test_malformed_yaml_skipped(tmp_path: Path) -> None:
    base = _seed_dir(tmp_path)
    paths = _build_paths(base)

    # Write malformed YAML
    bad = base / "patterns" / "malformed.yaml"
    bad.write_text("{{{{not valid yaml: [")

    # Build should not crash
    counts = cmd_build(**paths)

    # Should still have loaded the valid patterns
    assert counts["patterns"] >= 1
