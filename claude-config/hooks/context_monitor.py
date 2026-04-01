#!/usr/bin/env python3
"""
Context monitor hook (PostToolUse):
Warns when context window is running low.
- WARNING at <=35% remaining
- CRITICAL at <=25% remaining
- Debounced to avoid spam (every 10 tool calls)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

DEBOUNCE_INTERVAL = 10
WARN_THRESHOLD = 35  # percent remaining
CRIT_THRESHOLD = 25  # percent remaining


def log(msg: str) -> None:
    """Log to hooks.log for debugging."""
    log_path = os.path.expanduser("~/.claude/hooks.log")
    try:
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] context_monitor: {msg}\n")
    except Exception:
        pass


def state_path(session_id: str) -> str:
    """Return temp file path for tracking state per session."""
    safe_id = session_id.replace("/", "_").replace("\\", "_")
    return f"/tmp/claude-ctx-monitor-{safe_id}.json"


def load_state(path: str) -> dict:
    """Load persisted state from temp file."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        return {"tool_call_count": 0, "last_severity": "NONE"}


def save_state(path: str, state: dict) -> None:
    """Persist state to temp file."""
    try:
        with open(path, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def get_severity(pct_remaining: float) -> str:
    """Determine severity level from remaining context percentage."""
    if pct_remaining <= CRIT_THRESHOLD:
        return "CRITICAL"
    elif pct_remaining <= WARN_THRESHOLD:
        return "WARNING"
    return "NONE"


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    session_id = hook_input.get("session_id", "unknown")
    sp = state_path(session_id)
    state = load_state(sp)

    # Increment tool call count
    state["tool_call_count"] = state.get("tool_call_count", 0) + 1
    count = state["tool_call_count"]
    last_severity = state.get("last_severity", "NONE")

    # Extract context usage — look for percentage fields in hook input
    # PostToolUse hook input may contain context_window_remaining or similar
    pct_remaining = None

    # Try multiple possible field paths
    if "context_window" in hook_input:
        cw = hook_input["context_window"]
        if isinstance(cw, dict):
            used = cw.get("used", 0)
            total = cw.get("total", 0)
            if total > 0:
                pct_remaining = ((total - used) / total) * 100

    if pct_remaining is None and "percent_remaining" in hook_input:
        pct_remaining = hook_input["percent_remaining"]

    if pct_remaining is None and "context_percent_remaining" in hook_input:
        pct_remaining = hook_input["context_percent_remaining"]

    # If we can't determine context usage, stay silent
    if pct_remaining is None:
        save_state(sp, state)
        sys.exit(0)

    severity = get_severity(pct_remaining)

    # Determine whether to emit a warning
    should_warn = False

    if severity == "NONE":
        state["last_severity"] = "NONE"
        save_state(sp, state)
        sys.exit(0)

    # Escalation bypasses debounce
    severity_order = {"NONE": 0, "WARNING": 1, "CRITICAL": 2}
    escalated = severity_order.get(severity, 0) > severity_order.get(last_severity, 0)

    if escalated:
        should_warn = True
    elif count % DEBOUNCE_INTERVAL == 0:
        should_warn = True

    if should_warn:
        pct_str = f"{pct_remaining:.0f}%"

        if severity == "CRITICAL":
            msg = (
                f"[context_monitor] CRITICAL: Only {pct_str} context remaining. "
                f"Wrap up current work or compact now to free context."
            )
        else:
            msg = (
                f"[context_monitor] WARNING: {pct_str} context remaining. "
                f"Avoid starting new complex work — finish current task first."
            )

        print(msg)
        log(f"{severity} ({pct_str} remaining, call #{count})")
        state["last_severity"] = severity

    save_state(sp, state)
    sys.exit(0)


if __name__ == "__main__":
    main()
