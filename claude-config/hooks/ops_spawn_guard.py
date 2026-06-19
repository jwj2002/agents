#!/usr/bin/env python3
"""PreToolUse hook: bound ops-flavored agent spawns.

The mechanical backstop for the ops-hang failure mode (buddy
`feedback-ad-hoc-agent-hangs.md`): raw Agent/Task spawns on open-ended ops/data
work hang because they carry no termination condition + no done-oracle. Code
work is protected by `/orchestrate` (the test suite is a universal oracle); ops
work has no such pipeline, so this hook enforces the bound at the harness layer
instead of relying on a rule that is "loaded != followed".

Policy: an *ops-flavored* spawn MUST declare a bounded-execution contract in its
prompt:

    OPS-BOUNDED: timeout=<N>s oracle="<deterministic done-check>"

The `/ops` skill emits this automatically. A raw spawn that omits it is blocked
with an actionable message. This proves BOTH a timeout and a postcondition
oracle were declared before any live-infra agent runs.

A spawn is "ops-flavored" when EITHER:
  - subagent_type == "ops"  (the explicit prod-write worker), OR
  - the prompt/description contains a high-confidence prod-execution signal
    (ssh to a known host + mutation, systemctl start/restart, dbmate up,
    pg_dump/pg_restore/pg_basebackup, psql against $DATABASE_URL, crontab/
    launchctl install, secret rotation). The signal list is deliberately
    execution-oriented to keep false positives near zero — a code agent that
    merely *mentions* psql is not caught.

Exit 2 blocks the tool call (Anthropic hook spec); exit 0 allows. Fails OPEN on
any parse/internal error — this hook must never block legitimate work because of
its own bug.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

_log_file = Path.home() / ".claude" / "hooks.log"
try:
    _log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(_log_file),
        level=logging.WARNING,
        format="%(asctime)s [ops_spawn_guard] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
except OSError:
    pass  # logging is best-effort; never block on it

SPAWN_TOOLS = {"Agent", "Task"}

# The bounded-execution contract the prompt must carry. Requires an explicit
# integer-second timeout AND a non-empty oracle string. Case-insensitive on the
# label so OPS-BOUNDED / ops-bounded both pass.
OPS_BOUNDED_RE = re.compile(
    r"OPS-BOUNDED:\s*timeout=\s*\d+\s*s\s+oracle=\s*[\"']?\S",
    re.IGNORECASE,
)

# High-confidence prod-EXECUTION signals (not mere mentions). Each implies the
# agent will mutate or directly operate live infra.
PROD_EXEC_SIGNALS = [
    re.compile(r"\bssh\s+jns(?:-server)?\b"),  # the home server
    re.compile(r"\bsystemctl\s+(?:restart|start|stop|enable|disable)\b"),
    re.compile(r"\bdbmate\s+up\b"),
    re.compile(r"\bpg_dump\b"),
    re.compile(r"\bpg_restore\b"),
    re.compile(r"\bpg_basebackup\b"),
    re.compile(r"\bpsql\b[^\n]*\$?\{?DATABASE_URL"),  # psql against prod DSN
    re.compile(r"\bcrontab\s+-", re.IGNORECASE),
    re.compile(r"\blaunchctl\s+(?:load|bootstrap|enable)\b"),
    re.compile(r"\brotat\w*\s+(?:the\s+)?secret", re.IGNORECASE),
    re.compile(r"\bsupabase\b[^\n]*\b(?:db|migration)\b", re.IGNORECASE),
]


def _matched_signal(text: str) -> str | None:
    for pat in PROD_EXEC_SIGNALS:
        if pat.search(text):
            return pat.pattern
    return None


def is_ops_flavored(subagent_type: str, text: str) -> tuple[bool, str]:
    """Return (is_ops, reason). reason names why it was classified ops."""
    if subagent_type.strip().lower() == "ops":
        return True, "subagent_type=ops"
    sig = _matched_signal(text)
    if sig:
        return True, f"prod-execution signal /{sig}/"
    return False, ""


def deny(reason: str) -> None:
    """Block the spawn (exit 2 + stderr per Anthropic hook spec)."""
    logging.warning("BLOCKED: %s", reason)
    sys.stderr.write(
        "[ops_spawn_guard] Blocked an ops-flavored agent spawn that is not "
        "bounded.\n"
        f"  Why classified as ops: {reason}\n"
        "  Add a bounded-execution contract to the agent prompt:\n"
        '      OPS-BOUNDED: timeout=<N>s oracle="<deterministic done-check>"\n'
        '  e.g. OPS-BOUNDED: timeout=120s oracle="systemctl is-active '
        'buddy-server == active AND curl -sf localhost:17789/health"\n'
        "  Or run the task through the /ops skill, which emits this and wraps "
        "every blocking call in `timeout`.\n"
        "  If this is genuinely NOT an ops task, drop subagent_type=ops / "
        "rephrase the prod-execution command out of the prompt.\n"
    )
    sys.exit(2)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        logging.warning("could not parse stdin JSON: %s", e)
        return 0  # fail open

    tool_name = payload.get("tool_name", "")
    if tool_name not in SPAWN_TOOLS:
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    subagent_type = str(tool_input.get("subagent_type", "") or "")
    prompt = str(tool_input.get("prompt", "") or "")
    description = str(tool_input.get("description", "") or "")
    text = f"{description}\n{prompt}"

    ops, reason = is_ops_flavored(subagent_type, text)
    if not ops:
        return 0

    if OPS_BOUNDED_RE.search(text):
        return 0  # bounded — allow

    deny(reason)
    return 0  # unreachable (deny exits), but keep the contract explicit


if __name__ == "__main__":
    sys.exit(main())
