#!/usr/bin/env python3
"""
Claude Code SessionStart hook: Load approved learning rules from knowledge base.
Reads YAML files directly (no MCP/SQLite dependency — runs before MCP connects).
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(0)  # No PyYAML, skip silently

RULES_DIR = Path.home() / "agents" / "knowledge" / "learning-rules"
PATTERNS_FULL_CAP = 800  # ~12K chars; prevents unbounded context growth


def load_patterns_full() -> "str | None":
    """Return content of patterns-full.md if present, else None.

    Searches: ~/.claude/memory/patterns-full.md
    Capped at PATTERNS_FULL_CAP lines to avoid bloating SessionStart context.
    Fail-open: returns None on any error or missing file.
    """
    candidate = Path.home() / ".claude" / "memory" / "patterns-full.md"
    if not candidate.exists():
        return None
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
        if len(lines) > PATTERNS_FULL_CAP:
            lines = lines[:PATTERNS_FULL_CAP]
            lines.append(
                f"\n... [truncated at {PATTERNS_FULL_CAP} lines — see full file] ..."
            )
        return "\n".join(lines)
    except Exception:
        return None


def load_approved_rules():
    if not RULES_DIR.exists():
        return []

    rules = []
    for f in sorted(RULES_DIR.glob("*.yaml")):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
            if data and data.get("approved"):
                rules.append(f"- {data['id']}: {data['rule']}")
        except Exception:
            continue
    return rules


def main():
    rules = load_approved_rules()
    patterns = load_patterns_full()

    if not rules and not patterns:
        return

    if rules:
        print("## Restored Context\n\n### Learning Rules (auto-loaded)\n\n" + "\n".join(rules))

    if patterns:
        print("\n## Applied Patterns (patterns-full.md)\n")
        print(patterns)


if __name__ == "__main__":
    main()
