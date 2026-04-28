#!/usr/bin/env python3
"""
Validate paths-glob frontmatter on rules files.

For each .md file in claude-config/rules/, parse its YAML frontmatter
and report:
  - whether `paths:` is set
  - the value (always-load vs scoped)
  - any malformed YAML

Run: python3 scripts/validate-paths-globs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)


REPO = Path(__file__).resolve().parent.parent
RULES_DIR = REPO / "rules"


def parse_frontmatter(path: Path) -> dict | None:
    """Return frontmatter dict, or None if no frontmatter found."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    fm_text = text[4:end]
    try:
        return yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        return {"_error": str(e)}


def classify(paths) -> str:
    if paths is None:
        return "ALWAYS-LOAD (no paths frontmatter — equivalent to all sessions)"
    if isinstance(paths, str):
        return f"SCOPED (single glob: {paths})"
    if isinstance(paths, list):
        if paths == ["**"]:
            return "ALWAYS-LOAD (explicit `[\"**\"]`)"
        return f"SCOPED ({len(paths)} globs: {paths})"
    return f"INVALID type: {type(paths).__name__}"


def main() -> int:
    if not RULES_DIR.is_dir():
        print(f"error: rules dir not found at {RULES_DIR}", file=sys.stderr)
        return 1

    total = 0
    scoped = 0
    always = 0
    issues = 0

    for rule in sorted(RULES_DIR.glob("*.md")):
        total += 1
        fm = parse_frontmatter(rule)
        if fm is None:
            print(f"  {rule.name:40} NO FRONTMATTER (always-load)")
            always += 1
            continue
        if "_error" in fm:
            print(f"  {rule.name:40} MALFORMED YAML: {fm['_error']}")
            issues += 1
            continue
        paths = fm.get("paths")
        verdict = classify(paths)
        print(f"  {rule.name:40} {verdict}")
        if "ALWAYS" in verdict:
            always += 1
        elif "SCOPED" in verdict:
            scoped += 1
        else:
            issues += 1

    print()
    print(f"Total rules: {total}")
    print(f"  Scoped:      {scoped}")
    print(f"  Always-load: {always}")
    if issues:
        print(f"  Issues:      {issues}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
