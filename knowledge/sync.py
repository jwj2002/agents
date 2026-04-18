#!/usr/bin/env python3
"""Knowledge base sync: YAML <-> SQLite bidirectional synchronization.

Commands:
    python sync.py build   -- Rebuild SQLite DB from YAML files
    python sync.py export  -- Export new SQLite records to YAML files
    python sync.py sync   -- git pull -> export -> build -> git commit -> git push

Requires: Python 3.11+, PyYAML
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

logger = logging.getLogger("knowledge-sync")

# All paths relative to this script's directory
BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
DB_PATH = BASE_DIR / "knowledge.db"
PATTERNS_DIR = BASE_DIR / "patterns"
DECISIONS_DIR = BASE_DIR / "decisions"
LEARNING_RULES_DIR = BASE_DIR / "learning-rules"
VELOCITY_DIR = BASE_DIR / "velocity"
PROJECT_SUMMARIES_DIR = BASE_DIR / "project-summaries"
PROJECTS_DIR = BASE_DIR / "projects"
INDEX_PATH = DECISIONS_DIR / "index.yaml"

# Validation constants
VALID_STATUSES = {"draft", "pilot", "validated", "deprecated"}
VALID_TIERS = {"primary", "secondary"}
PATTERN_REQUIRED = {"id", "category", "name", "status", "tier"}
DECISION_REQUIRED = {"id", "topic", "title", "decision"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _init_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    sql = (schema_path or SCHEMA_PATH).read_text()
    conn.executescript(sql)


def _clear_tables(conn: sqlite3.Connection) -> None:
    """Delete all rows from data tables (preserves schema)."""
    for table in ("patterns", "decisions", "learning_rules", "velocity", "decisions_fts", "project_tracker"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def _json_dump(value) -> str | None:
    """Serialize a value to JSON string, or None if value is None/empty."""
    if value is None:
        return None
    return json.dumps(value)


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict | list | None:
    """Load a YAML file, returning None on parse errors."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        logger.warning("Malformed YAML in %s: %s", path, exc)
        return None
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Build: patterns
# ---------------------------------------------------------------------------

def _build_patterns(conn: sqlite3.Connection, patterns_dir: Path) -> int:
    count = 0
    if not patterns_dir.is_dir():
        logger.warning("Patterns directory not found: %s", patterns_dir)
        return count

    for path in sorted(patterns_dir.glob("*.yaml")):
        data = _load_yaml(path)
        if data is None:
            continue

        # Validate required fields
        missing = PATTERN_REQUIRED - set(data.keys())
        if missing:
            logger.warning("Skipping %s: missing required fields %s", path.name, missing)
            continue

        # Validate enum values
        if data["status"] not in VALID_STATUSES:
            logger.warning(
                "Skipping %s: invalid status '%s' (must be one of %s)",
                path.name, data["status"], VALID_STATUSES,
            )
            continue
        if data["tier"] not in VALID_TIERS:
            logger.warning(
                "Skipping %s: invalid tier '%s' (must be one of %s)",
                path.name, data["tier"], VALID_TIERS,
            )
            continue

        conn.execute(
            """INSERT OR REPLACE INTO patterns
               (id, category, name, status, tier, description,
                when_to_use, when_not_to_use, implementation,
                dependencies, tests, reference_project, reference_path,
                related_decisions, lifecycle, consecutive_successes,
                validated_count, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["id"],
                data["category"],
                data["name"],
                data["status"],
                data["tier"],
                data.get("description"),
                data.get("when_to_use"),
                data.get("when_not_to_use"),
                _json_dump(data.get("implementation")),
                _json_dump(data.get("dependencies")),
                _json_dump(data.get("tests")),
                data.get("reference_project"),
                data.get("reference_path"),
                _json_dump(data.get("related_decisions")),
                _json_dump(data.get("lifecycle")),
                data.get("consecutive_successes", 0),
                data.get("validated_count", 0),
                data.get("created_at"),
                data.get("updated_at"),
            ),
        )
        count += 1

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Build: decisions
# ---------------------------------------------------------------------------

def _build_decisions(conn: sqlite3.Connection, decisions_dir: Path) -> int:
    count = 0
    seen_ids: dict[str, str] = {}  # id -> filename

    if not decisions_dir.is_dir():
        logger.warning("Decisions directory not found: %s", decisions_dir)
        return count

    for path in sorted(decisions_dir.glob("*.yaml")):
        if path.name == "index.yaml":
            continue

        data = _load_yaml(path)
        if data is None:
            continue

        # Validate required fields
        missing = DECISION_REQUIRED - set(data.keys())
        if missing:
            logger.warning("Skipping %s: missing required fields %s", path.name, missing)
            continue

        did = data["id"]

        # Check duplicate IDs
        if did in seen_ids:
            logger.warning(
                "Duplicate decision ID '%s' in %s (first seen in %s)",
                did, path.name, seen_ids[did],
            )
            continue

        seen_ids[did] = path.name

        # Extract linked fields (nested under 'linked' key in YAML)
        linked = data.get("linked", {})

        conn.execute(
            """INSERT OR REPLACE INTO decisions
               (id, date, project, topic, title, context, decision,
                alternatives, reasoning, outcome, linked_patterns,
                linked_issues, linked_prs, related_decisions, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                did,
                data.get("date"),
                data.get("project"),
                data["topic"],
                data["title"],
                data.get("context"),
                data["decision"],
                _json_dump(data.get("alternatives")),
                data.get("reasoning"),
                data.get("outcome"),
                _json_dump(linked.get("patterns")),
                _json_dump(linked.get("issues")),
                _json_dump(linked.get("prs")),
                _json_dump(linked.get("related_decisions")),
                data.get("created_at"),
            ),
        )
        count += 1

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Build: index.yaml
# ---------------------------------------------------------------------------

def _rebuild_index(conn: sqlite3.Connection, decisions_dir: Path) -> None:
    """Regenerate decisions/index.yaml from the decisions table."""
    rows = conn.execute(
        "SELECT id, project, topic, title, date, linked_patterns FROM decisions ORDER BY id"
    ).fetchall()

    by_project: dict[str, list] = {}
    by_topic: dict[str, list] = {}
    by_pattern: dict[str, list] = {}

    for row in rows:
        did = row["id"]
        project = row["project"]
        topic = row["topic"]
        title = row["title"]
        date = row["date"]
        patterns = json.loads(row["linked_patterns"]) if row["linked_patterns"] else []

        if project:
            by_project.setdefault(project, []).append(
                {"id": did, "topic": topic, "title": title, "date": date}
            )

        if topic:
            by_topic.setdefault(topic, []).append(did)

        for pat in patterns:
            by_pattern.setdefault(pat, []).append(did)

    index = {
        "by_project": by_project,
        "by_topic": by_topic,
        "by_pattern": by_pattern,
    }

    decisions_dir.mkdir(parents=True, exist_ok=True)
    with open(decisions_dir / "index.yaml", "w") as f:
        yaml.dump(index, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Build: FTS
# ---------------------------------------------------------------------------

def _rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM decisions_fts")
    conn.execute(
        "INSERT INTO decisions_fts SELECT id, title, context, decision, reasoning FROM decisions"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Build: learning rules
# ---------------------------------------------------------------------------

def _build_learning_rules(conn: sqlite3.Connection, rules_dir: Path) -> int:
    count = 0
    if not rules_dir.is_dir():
        logger.warning("Learning rules directory not found: %s", rules_dir)
        return count

    for path in sorted(rules_dir.glob("*.yaml")):
        data = _load_yaml(path)
        if data is None:
            continue

        if not isinstance(data, dict) or "id" not in data or "rule" not in data:
            logger.warning("Skipping malformed learning rule: %s", path.name)
            continue

        conn.execute(
            """INSERT OR REPLACE INTO learning_rules
               (id, rule, source, confidence, applies_to, approved, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                data["id"],
                data["rule"],
                data.get("source"),
                data.get("confidence"),
                data.get("applies_to"),
                1 if data.get("approved") else 0,
                data.get("created_at"),
            ),
        )
        count += 1

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Build: velocity
# ---------------------------------------------------------------------------

def _build_velocity(conn: sqlite3.Connection, velocity_dir: Path) -> int:
    count = 0
    if not velocity_dir.is_dir():
        logger.warning("Velocity directory not found: %s", velocity_dir)
        return count

    for path in sorted(velocity_dir.glob("*.yaml")):
        data = _load_yaml(path)
        if data is None:
            continue

        if not isinstance(data, dict) or "id" not in data:
            logger.warning("Skipping malformed velocity entry: %s", path.name)
            continue

        conn.execute(
            """INSERT OR REPLACE INTO velocity
               (id, date, project, task_type, complexity, model,
                duration_seconds, cost_dollars, success, description)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                data["id"],
                data.get("date"),
                data.get("project"),
                data.get("task_type"),
                data.get("complexity"),
                data.get("model"),
                data.get("duration_seconds"),
                data.get("cost_dollars"),
                1 if data.get("success") else 0,
                data.get("description"),
            ),
        )
        count += 1

    conn.commit()
    return count


def _build_project_summaries(conn: sqlite3.Connection, summaries_dir: Path) -> int:
    count = 0
    if not summaries_dir.is_dir():
        return count

    for path in sorted(summaries_dir.glob("*.yaml")):
        data = _load_yaml(path)
        if data is None:
            continue

        if not isinstance(data, dict) or "project" not in data:
            logger.warning("Skipping malformed project summary: %s", path.name)
            continue

        conn.execute(
            """INSERT OR REPLACE INTO project_summaries
               (project, summary, updated_at, updated_by)
               VALUES (?,?,?,?)""",
            (
                data["project"],
                data.get("summary", ""),
                data.get("updated_at"),
                data.get("updated_by"),
            ),
        )
        count += 1

    conn.commit()
    return count


def _build_project_tracker(conn: sqlite3.Connection, projects_dir: Path) -> int:
    """Load project tracker YAML files into project_tracker table."""
    count = 0
    if not projects_dir.is_dir():
        return count

    for path in sorted(projects_dir.glob("*.yaml")):
        data = _load_yaml(path)
        if data is None:
            continue

        if not isinstance(data, dict) or "project" not in data:
            logger.warning("Skipping malformed project tracker: %s", path.name)
            continue

        conn.execute(
            """INSERT OR REPLACE INTO project_tracker
               (project, status, focus, next_steps, blockers, open_questions,
                specs, dependencies, updated_at, updated_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                data["project"],
                data.get("status", "active"),
                data.get("focus"),
                _json_dump(data.get("next_steps")),
                _json_dump(data.get("blockers")),
                _json_dump(data.get("open_questions")),
                _json_dump(data.get("specs")),
                _json_dump(data.get("dependencies")),
                data.get("updated_at"),
                data.get("updated_by"),
            ),
        )
        count += 1

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# build command
# ---------------------------------------------------------------------------

def cmd_build(
    db_path: Path | None = None,
    schema_path: Path | None = None,
    patterns_dir: Path | None = None,
    decisions_dir: Path | None = None,
    rules_dir: Path | None = None,
    velocity_dir: Path | None = None,
) -> dict[str, int]:
    """Build (or rebuild) knowledge.db from YAML files.

    Returns dict with counts: patterns, decisions, rules, velocity.
    """
    _db = db_path or DB_PATH
    _schema = schema_path or SCHEMA_PATH
    _patterns = patterns_dir or PATTERNS_DIR
    _decisions = decisions_dir or DECISIONS_DIR
    _rules = rules_dir or LEARNING_RULES_DIR
    _velocity = velocity_dir or VELOCITY_DIR

    conn = _connect(_db)
    try:
        _init_schema(conn, _schema)
        _clear_tables(conn)

        n_patterns = _build_patterns(conn, _patterns)
        n_decisions = _build_decisions(conn, _decisions)
        _rebuild_index(conn, _decisions)
        _rebuild_fts(conn)
        n_rules = _build_learning_rules(conn, _rules)
        n_velocity = _build_velocity(conn, _velocity)
        n_summaries = _build_project_summaries(conn, PROJECT_SUMMARIES_DIR)
        n_projects = _build_project_tracker(conn, PROJECTS_DIR)

        print(
            f"Built {_db.name}: "
            f"{n_patterns} patterns, {n_decisions} decisions, "
            f"{n_rules} rules, {n_velocity} velocity entries, "
            f"{n_summaries} project summaries, {n_projects} project tracker entries"
        )
        return {
            "patterns": n_patterns,
            "decisions": n_decisions,
            "rules": n_rules,
            "velocity": n_velocity,
            "projects": n_projects,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# export command
# ---------------------------------------------------------------------------

def cmd_export(
    db_path: Path | None = None,
    patterns_dir: Path | None = None,
    decisions_dir: Path | None = None,
    rules_dir: Path | None = None,
    velocity_dir: Path | None = None,
) -> None:
    """Export new SQLite records (created_at > last_export) to YAML files."""
    _db = db_path or DB_PATH
    _patterns = patterns_dir or PATTERNS_DIR
    _decisions = decisions_dir or DECISIONS_DIR
    _rules = rules_dir or LEARNING_RULES_DIR
    _velocity = velocity_dir or VELOCITY_DIR

    if not _db.exists():
        logger.warning("No database found at %s — nothing to export", _db)
        return

    conn = _connect(_db)
    try:
        # Get last export timestamp
        row = conn.execute(
            "SELECT value FROM _meta WHERE key = 'last_export'"
        ).fetchone()
        last_export = row["value"] if row else None

        # Export patterns
        if last_export:
            patterns = conn.execute(
                "SELECT * FROM patterns WHERE created_at > ?", (last_export,)
            ).fetchall()
        else:
            patterns = conn.execute("SELECT * FROM patterns").fetchall()

        _patterns.mkdir(parents=True, exist_ok=True)
        for p in patterns:
            _export_pattern(p, _patterns)

        # Export decisions
        if last_export:
            decisions = conn.execute(
                "SELECT * FROM decisions WHERE created_at > ?", (last_export,)
            ).fetchall()
        else:
            decisions = conn.execute("SELECT * FROM decisions").fetchall()

        _decisions.mkdir(parents=True, exist_ok=True)
        for d in decisions:
            _export_decision(d, _decisions)

        # Export learning rules
        if last_export:
            rules = conn.execute(
                "SELECT * FROM learning_rules WHERE created_at > ?", (last_export,)
            ).fetchall()
        else:
            rules = conn.execute("SELECT * FROM learning_rules").fetchall()

        _rules.mkdir(parents=True, exist_ok=True)
        for rule in rules:
            _export_learning_rule(rule, _rules)

        # Export velocity
        if last_export:
            velocity = conn.execute(
                "SELECT * FROM velocity WHERE date > ?", (last_export,)
            ).fetchall()
        else:
            velocity = conn.execute("SELECT * FROM velocity").fetchall()

        _velocity.mkdir(parents=True, exist_ok=True)
        for v in velocity:
            _export_velocity_entry(v, _velocity)

        # Update last_export timestamp
        now = _now_iso()
        conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('last_export', ?)",
            (now,),
        )
        conn.commit()

        exported = len(patterns) + len(decisions) + len(rules) + len(velocity)
        print(f"Exported {exported} records (last_export={now})")
    finally:
        conn.close()


def _export_pattern(row: sqlite3.Row, patterns_dir: Path) -> None:
    """Write a single pattern row to a YAML file."""
    data: dict = {}
    data["id"] = row["id"]
    data["category"] = row["category"]
    data["name"] = row["name"]
    data["status"] = row["status"]
    data["tier"] = row["tier"]

    for field in (
        "description", "when_to_use", "when_not_to_use",
    ):
        if row[field]:
            data[field] = row[field]

    for json_field in ("implementation", "dependencies", "tests", "lifecycle"):
        if row[json_field]:
            data[json_field] = json.loads(row[json_field])

    if row["reference_project"]:
        data["reference_project"] = row["reference_project"]
    if row["reference_path"]:
        data["reference_path"] = row["reference_path"]

    if row["related_decisions"]:
        data["related_decisions"] = json.loads(row["related_decisions"])
    else:
        data["related_decisions"] = []

    data["consecutive_successes"] = row["consecutive_successes"] or 0
    data["validated_count"] = row["validated_count"] or 0
    data["created_at"] = row["created_at"]
    data["updated_at"] = row["updated_at"]

    # Build filename from id: PAT-001 -> pat-001.yaml won't match existing
    # Use a slug: lowercase id with hyphens preserved
    slug = row["id"].lower()
    # Try to match an existing file by id
    existing = _find_existing_pattern_file(row["id"], patterns_dir)
    filename = existing.name if existing else f"{slug}.yaml"

    with open(patterns_dir / filename, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _find_existing_pattern_file(pattern_id: str, patterns_dir: Path) -> Path | None:
    """Find existing YAML file for a pattern by reading each file's id field."""
    for path in patterns_dir.glob("*.yaml"):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and data.get("id") == pattern_id:
                return path
        except (yaml.YAMLError, OSError):
            continue
    return None


def _export_decision(row: sqlite3.Row, decisions_dir: Path) -> None:
    """Write a single decision row to a YAML file."""
    data: dict = {}
    data["id"] = row["id"]
    if row["date"]:
        data["date"] = row["date"]
    if row["project"]:
        data["project"] = row["project"]
    data["topic"] = row["topic"]
    data["title"] = row["title"]
    if row["context"]:
        data["context"] = row["context"]
    data["decision"] = row["decision"]
    if row["alternatives"]:
        data["alternatives"] = json.loads(row["alternatives"])
    if row["reasoning"]:
        data["reasoning"] = row["reasoning"]
    if row["outcome"]:
        data["outcome"] = row["outcome"]

    linked: dict = {}
    if row["linked_patterns"]:
        linked["patterns"] = json.loads(row["linked_patterns"])
    if row["linked_issues"]:
        linked["issues"] = json.loads(row["linked_issues"])
    if row["linked_prs"]:
        linked["prs"] = json.loads(row["linked_prs"])
    if row["related_decisions"]:
        linked["related_decisions"] = json.loads(row["related_decisions"])
    if linked:
        data["linked"] = linked

    data["created_at"] = row["created_at"]

    filename = f"{row['id']}.yaml"
    with open(decisions_dir / filename, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _export_learning_rule(row: sqlite3.Row, rules_dir: Path) -> None:
    """Write a single learning rule to its own YAML file."""
    data = {
        "id": row["id"],
        "rule": row["rule"],
        "source": row["source"],
        "confidence": row["confidence"],
        "applies_to": row["applies_to"],
        "approved": bool(row["approved"]),
        "created_at": row["created_at"],
    }
    filename = f"{row['id']}.yaml"
    with open(rules_dir / filename, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _export_velocity_entry(row: sqlite3.Row, velocity_dir: Path) -> None:
    """Write a single velocity entry to its own YAML file."""
    data = {
        "id": row["id"],
        "date": row["date"],
        "project": row["project"],
        "task_type": row["task_type"],
        "complexity": row["complexity"],
        "model": row["model"],
        "duration_seconds": row["duration_seconds"],
        "cost_dollars": row["cost_dollars"],
        "success": bool(row["success"]),
        "description": row["description"],
    }
    filename = f"V-{row['id']:04d}.yaml" if isinstance(row["id"], int) else f"V-{row['id']}.yaml"
    with open(velocity_dir / filename, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# sync command
# ---------------------------------------------------------------------------

def cmd_sync() -> None:
    """Full sync: git pull -> export -> build -> git add -> git commit -> git push."""
    # Step 1: git pull --rebase
    result = subprocess.run(
        ["git", "pull", "--rebase"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("git pull --rebase failed: %s", result.stderr)
        print("ERROR: git pull failed. Resolve conflicts manually.", file=sys.stderr)
        sys.exit(1)
    print(f"git pull: {result.stdout.strip()}")

    # Step 2: export (before build to prevent data loss)
    cmd_export()

    # Step 3: build
    cmd_build()

    # Step 4: git add specific directories
    subprocess.run(
        [
            "git", "add",
            "knowledge/patterns/",
            "knowledge/decisions/",
            "knowledge/learning-rules/",
            "knowledge/velocity/",
            "knowledge/schema.sql",
        ],
        capture_output=True, text=True,
    )

    # Step 5: git commit (skip if nothing changed)
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if status.returncode == 0:
        print("Nothing changed — skipping commit")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    subprocess.run(
        ["git", "commit", "-m", f"knowledge sync: {now}"],
        capture_output=True, text=True,
    )

    # Step 6: git push
    result = subprocess.run(
        ["git", "push"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("git push failed: %s", result.stderr)
        print("ERROR: git push failed.", file=sys.stderr)
        sys.exit(1)
    print("Sync complete")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Knowledge base YAML <-> SQLite sync",
    )
    parser.add_argument(
        "command",
        choices=["build", "export", "sync"],
        help="Command to run",
    )
    args = parser.parse_args()

    if args.command == "build":
        cmd_build()
    elif args.command == "export":
        cmd_export()
    elif args.command == "sync":
        cmd_sync()


if __name__ == "__main__":
    main()
