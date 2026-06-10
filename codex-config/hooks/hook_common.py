#!/usr/bin/env python3
"""Common helpers for Codex lifecycle hook wrappers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HOOK_EXCEPTIONS = (ImportError, OSError, RuntimeError, TypeError, ValueError)


def add_repo_to_path() -> Path:
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    return repo


def read_payload() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def emit(event: str, *, message: str | None = None, context: str | None = None) -> None:
    payload: dict[str, Any] = {"event": event}
    if message:
        payload["message"] = message
    if context:
        payload["additional_context"] = context
    print(json.dumps(payload, sort_keys=True))


def fail_open() -> int:
    return 0
