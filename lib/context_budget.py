"""Context budget extraction for lifecycle hooks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

DEBOUNCE_INTERVAL = 10
WARN_THRESHOLD = 35.0
CRIT_THRESHOLD = 25.0
SEVERITY_ORDER = {"NONE": 0, "WARNING": 1, "CRITICAL": 2}


def percent_remaining(payload: dict[str, Any]) -> float | None:
    context_window = payload.get("context_window")
    if isinstance(context_window, dict):
        used = _number(context_window.get("used"))
        total = _number(context_window.get("total"))
        remaining = _number(context_window.get("remaining"))
        if total and remaining is not None:
            return max(0.0, min(100.0, (remaining / total) * 100.0))
        if total and used is not None:
            return max(0.0, min(100.0, ((total - used) / total) * 100.0))

    for key in ("percent_remaining", "context_percent_remaining"):
        value = _number(payload.get(key))
        if value is not None:
            return max(0.0, min(100.0, value))
    return None


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.rstrip("%"))
        except ValueError:
            return None
    return None


def severity_for(percent: float) -> str:
    if percent <= CRIT_THRESHOLD:
        return "CRITICAL"
    if percent <= WARN_THRESHOLD:
        return "WARNING"
    return "NONE"


def state_path(session_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)
    return Path(tempfile.gettempdir()) / f"codex-context-monitor-{safe or 'unknown'}.json"


def should_warn(payload: dict[str, Any]) -> tuple[str, float | None]:
    pct = percent_remaining(payload)
    if pct is None:
        return ("NONE", None)
    severity = severity_for(pct)
    if severity == "NONE":
        _save_state(payload, {"tool_call_count": 0, "last_severity": "NONE"})
        return ("NONE", pct)

    state = _load_state(payload)
    count = int(state.get("tool_call_count", 0)) + 1
    last = str(state.get("last_severity", "NONE"))
    escalated = SEVERITY_ORDER[severity] > SEVERITY_ORDER.get(last, 0)
    warn = escalated or count % DEBOUNCE_INTERVAL == 0
    state["tool_call_count"] = count
    if warn:
        state["last_severity"] = severity
    _save_state(payload, state)
    return (severity if warn else "NONE", pct)


def _load_state(payload: dict[str, Any]) -> dict[str, object]:
    path = state_path(str(payload.get("session_id") or "unknown"))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tool_call_count": 0, "last_severity": "NONE"}


def _save_state(payload: dict[str, Any], state: dict[str, object]) -> None:
    path = state_path(str(payload.get("session_id") or "unknown"))
    try:
        path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    except OSError:
        pass
