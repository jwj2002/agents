#!/usr/bin/env python3
"""
Claude Code SessionStart hook: Load approved learning rules from knowledge base.
Reads YAML files from ~/agents/knowledge/learning-rules/ (no MCP/SQLite dependency).
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(0)  # No PyYAML, skip silently

RULES_DIR = Path.home() / "agents" / "knowledge" / "learning-rules"


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

    if not rules:
        return

    print("## Restored Context\n\n### Learning Rules (auto-loaded)\n\n" + "\n".join(rules))


if __name__ == "__main__":
    main()
