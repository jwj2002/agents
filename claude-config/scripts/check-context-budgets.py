#!/usr/bin/env python3
"""
Enforce context budgets (issue #384).

Two budgets, both measured in lines:

  1. CLAUDE.md         — the always-loaded system-prompt orientation file.
  2. Always-load rules — the sum of every rules/*.md that loads on EVERY
     session. A rule is always-load when its frontmatter `paths:` is
     exactly `["**"]`, OR when it has no `paths:` key at all (per
     validate-paths-globs.py: "no paths frontmatter == all sessions").

Scoped rules (a narrow `paths:` glob list) are NOT counted toward the
always-load sum — they only load when a matching file is in context.

Exit 0 with a per-check summary on pass; exit 1 with a GitHub-Actions
`::error::` annotation per breach. Defaults: CLAUDE.md <=200, rules <=450.

Run: python3 claude-config/scripts/check-context-budgets.py
     [--claude-budget N] [--rules-budget N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)


DEFAULT_CLAUDE_BUDGET = 200
DEFAULT_RULES_BUDGET = 450

REPO = Path(__file__).resolve().parent.parent  # claude-config/
CLAUDE_MD = REPO / "CLAUDE.md"
RULES_DIR = REPO / "rules"


def parse_frontmatter(path: Path) -> dict | None:
    """Return the YAML frontmatter dict, or None if there is no frontmatter.

    Mirrors validate-paths-globs.py so the two checkers agree on what
    counts as a rule's frontmatter.
    """
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


def is_always_load(path: Path) -> bool:
    """True when this rule loads on EVERY session.

    Always-load == no frontmatter, no `paths:` key, or `paths == ["**"]`.
    A malformed-frontmatter file is treated as always-load (conservative:
    it would load until fixed) — validate-paths-globs.py flags it as an
    issue separately.
    """
    fm = parse_frontmatter(path)
    if fm is None:
        return True
    if "_error" in fm:
        return True
    paths = fm.get("paths")
    if paths is None:
        return True
    return paths == ["**"]


def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def check(
    claude_md: Path,
    rules_dir: Path,
    claude_budget: int,
    rules_budget: int,
) -> int:
    breaches = 0

    # Check 1 — CLAUDE.md.
    if not claude_md.is_file():
        print(f"::error::{claude_md} not found", file=sys.stderr)
        breaches += 1
    else:
        claude_lines = count_lines(claude_md)
        if claude_lines > claude_budget:
            print(
                f"::error::{claude_md.name} {claude_lines} lines "
                f"exceeds budget {claude_budget}"
            )
            breaches += 1
        else:
            print(f"OK: {claude_md.name} {claude_lines}/{claude_budget} lines")

    # Check 2 — always-load rules sum.
    if not rules_dir.is_dir():
        print(f"::error::rules dir not found at {rules_dir}", file=sys.stderr)
        breaches += 1
    else:
        always_total = 0
        counted: list[tuple[str, int]] = []
        for rule in sorted(rules_dir.glob("*.md")):
            if is_always_load(rule):
                n = count_lines(rule)
                always_total += n
                counted.append((rule.name, n))
        if always_total > rules_budget:
            print(
                f"::error::always-load rules total {always_total} lines "
                f"exceeds budget {rules_budget}"
            )
            for name, n in counted:
                print(f"    {name}: {n}")
            breaches += 1
        else:
            print(
                f"OK: always-load rules {always_total}/{rules_budget} lines "
                f"across {len(counted)} files"
            )

    return 1 if breaches else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce context budgets (#384)")
    parser.add_argument("--claude-budget", type=int, default=DEFAULT_CLAUDE_BUDGET)
    parser.add_argument("--rules-budget", type=int, default=DEFAULT_RULES_BUDGET)
    parser.add_argument(
        "--claude-md", type=Path, default=CLAUDE_MD, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--rules-dir", type=Path, default=RULES_DIR, help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    return check(args.claude_md, args.rules_dir, args.claude_budget, args.rules_budget)


if __name__ == "__main__":
    sys.exit(main())
