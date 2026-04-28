#!/usr/bin/env python3
"""Migrate pattern IDs from PAT-NNN to pat-<filename-stem> slugs.

Four passes:
  1. Rewrite `id:` field in each knowledge/patterns/*.yaml.
  2. Rewrite in-line prose `PAT-NNN` references inside pattern YAML bodies.
  3. Rewrite `linked_patterns:` arrays / `patterns:` arrays in
     knowledge/decisions/*.yaml (handles flow form `[PAT-001]` and block form
     `- PAT-001` items).
  4. Add `legacy_id: PAT-NNN` to each pattern YAML (idempotent insert).

All rewrites are line-regex based: the YAML files are NOT parsed-and-redumped, so
formatting, comments, key order, and quoting style are preserved exactly.

Idempotent: a second run produces zero changes after the first run completes.

Stdlib-only at import time except for PyYAML, which is already a project
requirement (see knowledge/sync.py).

Usage:
    python3 scripts/migrate-pattern-ids-to-slugs.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
PATTERNS_DIR = REPO / "knowledge" / "patterns"
DECISIONS_DIR = REPO / "knowledge" / "decisions"

# Matches the canonical PAT-NNN token: `PAT-` + 1+ digits, on a word boundary.
PAT_TOKEN = re.compile(r"\bPAT-(\d+)\b")
# Matches a top-level `id: PAT-NNN` line (any indent, optional quotes).
ID_LINE = re.compile(r"^(\s*id:\s*)['\"]?(PAT-\d+)['\"]?\s*$")
# Matches a `linked_patterns:` flow-list line: `linked_patterns: [PAT-001]`.
# Group 3 captures the trailing `]` only; trailing whitespace/newline is preserved
# separately so we don't accidentally double-newline empty lists.
LINKED_FLOW = re.compile(r"^(\s*linked_patterns:\s*\[)([^\]]*)(\])(\s*)$")
# Matches a `patterns:` flow-list line (used inside decisions' `linked:` block).
PATTERNS_FLOW = re.compile(r"^(\s*patterns:\s*\[)([^\]]*)(\])(\s*)$")
# Matches a YAML block-list child item: `  - PAT-001`.
LINKED_BLOCK_ITEM = re.compile(r"^(\s*-\s*)['\"]?(PAT-\d+)['\"]?\s*$")


def build_slug_map() -> dict[str, str]:
    """Walk patterns/*.yaml; return {PAT-NNN: pat-<stem>} for not-yet-migrated files.

    Already-migrated files (where current `id` already equals the slug form) are
    skipped silently — this is what makes pass-by-pass logic idempotent.
    """
    pat_to_slug: dict[str, str] = {}
    slug_seen: set[str] = set()
    for path in sorted(PATTERNS_DIR.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        old_id = data.get("id")
        if not old_id:
            sys.exit(f"FATAL: {path.name} has no id field")
        slug = f"pat-{path.stem}"
        if slug in slug_seen:
            sys.exit(f"FATAL: duplicate slug derivation for {path.name}: {slug}")
        slug_seen.add(slug)
        # Allow already-migrated files (id already equals slug) — idempotent path.
        if old_id == slug:
            continue
        if old_id in pat_to_slug:
            sys.exit(
                f"FATAL: duplicate pre-migration id {old_id} (also in earlier file)"
            )
        pat_to_slug[old_id] = slug
    return pat_to_slug


def rewrite_lines(path: Path, transform, dry_run: bool) -> int:
    """Read path, apply `transform(line) -> line` to each line, write back.

    Returns the number of lines changed. No write performed if 0 changes.
    """
    original = path.read_text().splitlines(keepends=True)
    rewritten = [transform(line) for line in original]
    changes = sum(1 for a, b in zip(original, rewritten) if a != b)
    if changes and not dry_run:
        path.write_text("".join(rewritten))
    return changes


def pass1_pattern_ids(slug_map: dict[str, str], dry_run: bool) -> int:
    """Rewrite the top-level `id:` line in each pattern YAML."""
    total = 0
    for path in sorted(PATTERNS_DIR.glob("*.yaml")):
        slug = f"pat-{path.stem}"

        def tx(line: str, _slug=slug) -> str:
            m = ID_LINE.match(line)
            if m and m.group(2).startswith("PAT-"):
                return f"{m.group(1)}{_slug}\n"
            return line

        total += rewrite_lines(path, tx, dry_run)
    return total


def pass2_inline_prose(slug_map: dict[str, str], dry_run: bool) -> int:
    """Replace every `PAT-NNN` token inside pattern YAML bodies with its slug.

    Only runs on lines that are NOT the top-level `id:` line (already handled
    in pass 1). Substitutions use the slug_map; unknown PAT-NNN tokens are
    left as-is and reported on stderr.
    """
    total = 0
    unknown: set[str] = set()
    for path in sorted(PATTERNS_DIR.glob("*.yaml")):

        def tx(line: str) -> str:
            if ID_LINE.match(line):
                return line  # handled in pass 1
            # `legacy_id:` lines intentionally hold the PAT-NNN value — leave alone.
            if line.lstrip().startswith("legacy_id:"):
                return line

            def repl(m: re.Match) -> str:
                token = m.group(0)
                if token in slug_map:
                    return slug_map[token]
                unknown.add(token)
                return token

            return PAT_TOKEN.sub(repl, line)

        total += rewrite_lines(path, tx, dry_run)
    if unknown:
        print(
            f"WARN: unresolved tokens in pattern bodies: {sorted(unknown)}",
            file=sys.stderr,
        )
    return total


def pass3_decisions(slug_map: dict[str, str], dry_run: bool) -> int:
    """Rewrite `linked_patterns:` / `patterns:` references in decisions.

    Handles three shapes seen in knowledge/decisions/*.yaml:
      a) `linked_patterns: [PAT-001]`            (flow, top-level)
      b) `  patterns: [PAT-002, PAT-091]`        (flow, nested under `linked:`)
      c) block lists with `- PAT-001` children   (the actual format in this repo)
    """

    def sub_token(text: str) -> str:
        def repl(m: re.Match) -> str:
            return slug_map.get(m.group(0), m.group(0))

        return PAT_TOKEN.sub(repl, text)

    total = 0
    for path in sorted(DECISIONS_DIR.glob("*.yaml")):
        if path.name == "index.yaml":
            continue  # auto-regen by _rebuild_index after the next sync build

        def tx(line: str) -> str:
            for rx in (LINKED_FLOW, PATTERNS_FLOW):
                m = rx.match(line)
                if m:
                    body = sub_token(m.group(2))
                    return f"{m.group(1)}{body}{m.group(3)}{m.group(4)}"
            m = LINKED_BLOCK_ITEM.match(line)
            if m and m.group(2) in slug_map:
                return f"{m.group(1)}{slug_map[m.group(2)]}\n"
            return line

        total += rewrite_lines(path, tx, dry_run)
    return total


def pass4_legacy_id(slug_map: dict[str, str], dry_run: bool) -> int:
    """Insert `legacy_id: PAT-NNN` immediately after the `id:` line.

    Idempotent: skipped if a `legacy_id:` line already follows the id line.
    """
    inverse = {v: k for k, v in slug_map.items()}
    total = 0
    for path in sorted(PATTERNS_DIR.glob("*.yaml")):
        slug = f"pat-{path.stem}"
        legacy = inverse.get(slug)
        if not legacy:
            continue
        lines = path.read_text().splitlines(keepends=True)
        out: list[str] = []
        inserted = False
        for i, line in enumerate(lines):
            out.append(line)
            if not inserted and line.startswith("id:"):
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if not next_line.lstrip().startswith("legacy_id:"):
                    out.append(f"legacy_id: {legacy}\n")
                inserted = True
        if "".join(out) != "".join(lines):
            total += 1
            if not dry_run:
                path.write_text("".join(out))
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    slug_map = build_slug_map()
    print(
        f"Built slug map: {len(slug_map)} mappings"
        f" ({'migration needed' if slug_map else 'fully migrated'})"
    )

    p1 = pass1_pattern_ids(slug_map, args.dry_run)
    p2 = pass2_inline_prose(slug_map, args.dry_run)
    p3 = pass3_decisions(slug_map, args.dry_run)
    p4 = pass4_legacy_id(slug_map, args.dry_run)

    verb = "would change" if args.dry_run else "changed"
    print(f"Pass 1 (pattern ids):     {verb} {p1} lines")
    print(f"Pass 2 (inline prose):    {verb} {p2} lines")
    print(f"Pass 3 (decisions):       {verb} {p3} lines")
    print(f"Pass 4 (legacy_id):       {verb} {p4} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
