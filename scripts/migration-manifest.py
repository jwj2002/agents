#!/usr/bin/env python3
"""migration-manifest.py — pre-flight dry-run for Path B migration.

Reads:
  - <repo>/knowledge/projects/*.yaml   (project trackers)
  - <repo>/knowledge/decisions/*.yaml  (decision records — archive-only)

Writes:
  - <repo>/_archived/migration-manifest-<YYYY-MM-DD>.md

The manifest is the centerpiece for PR review (Codex Finding 5 mitigation).
Reviewers inspect every YAML→Obsidian field mapping BEFORE merge to catch
bad mappings before they're applied. Decisions are archive-only — listed
for verification, not converted.

Idempotent: re-running on the same source for the same date produces
identical output.

Usage:
    python3 scripts/migration-manifest.py
    python3 scripts/migration-manifest.py --date 2026-05-08      # pin date
    python3 scripts/migration-manifest.py --output /tmp/m.md     # override
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml


# Source schema (knowledge/projects/*.yaml) → destination schema
# (Obsidian project note frontmatter, manually-edited half only).
#
# Pulse-managed fields (last_commit_at, commits_7d, etc.) are NOT migrated
# — they live in per-host sidecars at <vault>/Projects/_pulse/<project>--<host>.md
# (added in response to Codex Finding 3, single-writer-per-host design).
PROJECT_FIELD_MAPPING: dict[str, str | None] = {
    "schema_version": None,         # Obsidian doesn't version frontmatter
    "project": "project",
    "host": "host",
    "status": "status",
    "focus": "focus",
    "next_steps": "next_steps",
    "blockers": "blockers",
    "open_questions": "open_questions",
    "specs": None,                  # No Obsidian destination — review per project
    "dependencies": None,           # No Obsidian destination — review per project
    "updated_at": "status_updated", # Renamed to align with new semantics
    "updated_by": None,             # Obsidian doesn't track per-field author
}

# Frontmatter fields that exist in the new schema but not in the source.
# Per spec §11 step 4: auto-populated from <repo>/CLAUDE.md where possible;
# otherwise require manual setting after the one-shot migration runs.
DESTINATION_ONLY_FIELDS: list[str] = [
    "client",        # personal | vital | tillamook | ...
    "kind",          # personal | client-work | engineering-tool | archive
    "stack",
    "repo_path",
    "repo_remote",
]


class ManifestError(Exception):
    """Raised when source YAMLs are missing or malformed."""


def load_project_yamls(projects_dir: Path) -> list[tuple[Path, dict]]:
    """Load every .yaml file in projects_dir and return [(path, data), ...]."""
    if not projects_dir.is_dir():
        raise ManifestError(f"projects directory not found: {projects_dir}")
    out: list[tuple[Path, dict]] = []
    for path in sorted(projects_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise ManifestError(f"malformed YAML in {path.name}: {e}") from e
        if not isinstance(data, dict):
            raise ManifestError(
                f"{path.name}: expected mapping at top level, got {type(data).__name__}"
            )
        out.append((path, data))
    return out


def load_decision_yamls(decisions_dir: Path) -> list[Path]:
    """Return sorted list of D-*.yaml files in decisions_dir.

    Decisions are archive-only per spec §11 step 5 — no field mapping needed.
    """
    if not decisions_dir.is_dir():
        raise ManifestError(f"decisions directory not found: {decisions_dir}")
    return sorted(p for p in decisions_dir.glob("D-*.yaml"))


def render_value(value: object) -> str:
    """Compact one-line rendering of a YAML value for table cells."""
    if value is None:
        return "_(null)_"
    if isinstance(value, list):
        if not value:
            return "_(empty list)_"
        return f"_(list, {len(value)} items)_"
    text = str(value).replace("\n", " ").strip()
    if len(text) > 60:
        text = text[:57] + "..."
    return text.replace("|", "\\|")


def render_project_section(name: str, data: dict) -> list[str]:
    """Render a single project's mapping table + warning blocks."""
    lines = [f"### `{name}.yaml` → `<vault>/Projects/{name}.md`", ""]

    lines.append("| Source field | Destination field | Source value | Notes |")
    lines.append("|---|---|---|---|")
    for src, dest in PROJECT_FIELD_MAPPING.items():
        if src not in data:
            continue
        value = render_value(data[src])
        if dest is None:
            note = "**dropped** (no destination)"
            dest_label = "—"
        elif dest != src:
            note = f"renamed → `{dest}`"
            dest_label = f"`{dest}`"
        else:
            note = "1:1"
            dest_label = f"`{dest}`"
        lines.append(f"| `{src}` | {dest_label} | {value} | {note} |")
    lines.append("")

    unknown = [k for k in data.keys() if k not in PROJECT_FIELD_MAPPING]
    if unknown:
        lines.append("**⚠ Unknown source fields (not in mapping table — REVIEWER ACTION):**")
        for k in unknown:
            lines.append(f"- `{k}`: {render_value(data[k])}")
        lines.append("")

    lines.append("**Destination-only fields (require manual setting after migration):**")
    for field in DESTINATION_ONLY_FIELDS:
        lines.append(f"- `{field}`")
    lines.append("")

    return lines


def render_manifest(
    projects: list[tuple[Path, dict]],
    decisions: list[Path],
    today: dt.date,
) -> str:
    """Build the full manifest markdown."""
    lines = [
        f"# Path B Migration Manifest — {today.isoformat()}",
        "",
        "Pre-flight dry-run for the Path B implementation PR (umbrella issue #170).",
        "Generated by `~/agents/scripts/migration-manifest.py`. Idempotent: re-running",
        "on the same source for the same date produces identical output.",
        "",
        "**Source**: `~/agents/knowledge/projects/*.yaml`, `~/agents/knowledge/decisions/*.yaml`",
        "**Destination**: `<vault>/Projects/<name>.md` frontmatter (projects),",
        "`_archived/decisions-pre-pathb/` (decisions — archive-only, no conversion)",
        "",
        "Reviewers: inspect each project's mapping table and act on any",
        "`⚠ Unknown source fields` BEFORE merging the implementation PR.",
        "",
        "---",
        "",
        f"## Projects ({len(projects)})",
        "",
    ]

    for path, data in projects:
        lines.extend(render_project_section(path.stem, data))
        lines.append("---")
        lines.append("")

    lines.extend([
        f"## Decisions ({len(decisions)} — archive-only)",
        "",
        "These YAML files will be moved to `_archived/decisions-pre-pathb/`",
        "without conversion. New decisions going forward will be created directly",
        "in Obsidian (`<vault>/Decisions/D-NNN.md`) via the reshaped `decision/cli.py`.",
        "",
        "| File | Title |",
        "|---|---|",
    ])
    for path in decisions:
        try:
            data = yaml.safe_load(path.read_text())
            title = (
                data.get("title", "_(no title)_")
                if isinstance(data, dict)
                else "_(unparseable)_"
            )
        except yaml.YAMLError:
            title = "_(unparseable)_"
        lines.append(f"| `{path.name}` | {render_value(title)} |")
    lines.append("")

    mapped = sum(1 for v in PROJECT_FIELD_MAPPING.values() if v is not None)
    dropped = len(PROJECT_FIELD_MAPPING) - mapped
    lines.extend([
        "---",
        "",
        "## Summary",
        "",
        f"- **{len(projects)} projects** mapped: "
        f"{mapped} fields preserved, {dropped} dropped per project (where present)",
        f"- **{len(decisions)} decisions** archived (no conversion)",
        f"- **{len(DESTINATION_ONLY_FIELDS)} destination-only fields per project** "
        "require manual setting: "
        + ", ".join(f"`{f}`" for f in DESTINATION_ONLY_FIELDS),
        "",
        f"Generated: {today.isoformat()}",
        "",
    ])

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Pre-flight dry-run for Path B migration."
    )
    parser.add_argument(
        "--projects-dir", type=Path,
        default=repo_root / "knowledge" / "projects",
        help="Source project YAML directory (default: <repo>/knowledge/projects)",
    )
    parser.add_argument(
        "--decisions-dir", type=Path,
        default=repo_root / "knowledge" / "decisions",
        help="Source decision YAML directory (default: <repo>/knowledge/decisions)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output path (default: <repo>/_archived/migration-manifest-<date>.md)",
    )
    parser.add_argument(
        "--date", type=dt.date.fromisoformat, default=None,
        help="Pin date (YYYY-MM-DD) — primarily for testing idempotency",
    )
    args = parser.parse_args(argv)

    today = args.date or dt.date.today()
    output = args.output or (
        repo_root / "_archived" / f"migration-manifest-{today.isoformat()}.md"
    )

    try:
        projects = load_project_yamls(args.projects_dir)
        decisions = load_decision_yamls(args.decisions_dir)
    except ManifestError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    manifest = render_manifest(projects, decisions, today)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(manifest)
    print(f"wrote {output} ({len(projects)} projects, {len(decisions)} decisions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
