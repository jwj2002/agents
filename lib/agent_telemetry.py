"""Secret-safe Codex hook telemetry."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.agent_state import issue_refs_from_payload


def telemetry_path(home: Path | None = None) -> Path:
    home = home or Path.home()
    return home / ".codex" / "telemetry" / "session-events.jsonl"


def build_event(payload: dict[str, Any], event: str, cwd: Path) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "session_id": payload.get("session_id") or payload.get("thread_id"),
        "cwd": str(cwd),
        "branch": _branch_name(cwd),
        "issue_refs": issue_refs_from_payload(payload),
        "model": payload.get("model"),
        "host": socket.gethostname(),
    }


def append_event(event: dict[str, Any], home: Path | None = None) -> Path:
    path = telemetry_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        fh.flush()
    return path


def _branch_name(cwd: Path) -> str | None:
    try:
        from lib.agent_completion import run

        result = run(["git", "branch", "--show-current"], cwd, timeout=3)
    except ImportError:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout
