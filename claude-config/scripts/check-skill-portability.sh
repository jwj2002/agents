#!/bin/bash
# check-skill-portability.sh — is a Claude skill safe to symlink into Codex?
#
# Usage: check-skill-portability.sh <path-to-SKILL.md>
#
# Exit 0  → portable: the skill body/frontmatter contains no Claude-only
#           harness constructs, so the SAME file can be symlinked into
#           ~/.codex/skills/<name> and read by Codex unchanged.
# Exit 1  → not portable: references a Claude-only construct that has no Codex
#           equivalent. The dual-installer skips it for Codex (Claude-only),
#           and prints the offending lines.
# Exit 2  → usage / file error.
#
# Rationale: Claude Code and Codex read an identical SKILL.md format, so a
# converter is unnecessary — a symlink shares one canonical file with zero
# drift. The ONLY thing that breaks a port is a body that assumes the Claude
# harness. We flag the unambiguous signals (tools, plan mode, MCP tool IDs,
# restrictive frontmatter) and deliberately do NOT flag prose mentions of
# slash commands like "/orchestrate", which are documentation, not coupling.
#
# Companion to codex-config/install.sh, which calls this per skill.

set -euo pipefail

skill="${1:-}"
if [ -z "$skill" ] || [ ! -f "$skill" ]; then
    echo "usage: $(basename "$0") <path-to-SKILL.md>" >&2
    exit 2
fi

# Strong, unambiguous Claude-harness signals. Keep this list conservative:
# a false positive needlessly denies Codex a working skill; a prose mention
# must never trip it. Add patterns only when a construct genuinely has no
# Codex equivalent.
hits=$(grep -EnI -i \
    -e '^[[:space:]]*allowed-tools:' \
    -e '^[[:space:]]*disable-model-invocation:' \
    -e '^[[:space:]]*context:[[:space:]]*fork' \
    -e 'mcp__[a-z0-9_]+' \
    -e '\bTask tool\b' -e '\bAgent tool\b' -e 'subagent_type' \
    -e 'ScheduleWakeup|EnterPlanMode|ExitPlanMode|TaskCreate|TaskUpdate' \
    "$skill" || true)

if [ -n "$hits" ]; then
    echo "$hits"
    exit 1
fi
exit 0
