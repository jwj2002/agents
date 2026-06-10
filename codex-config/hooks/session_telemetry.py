#!/usr/bin/env python3
"""Stop hook: append lightweight, derived Codex session telemetry."""

from __future__ import annotations

import os
from pathlib import Path

from hook_common import HOOK_EXCEPTIONS, add_repo_to_path, emit, fail_open, read_payload


def main() -> int:
    add_repo_to_path()
    try:
        from lib.agent_telemetry import append_event, build_event

        payload = read_payload()
        path = append_event(build_event(payload, "Stop", Path(os.getcwd())))
        emit("Stop", message=f"telemetry recorded: {path}")
    except HOOK_EXCEPTIONS:
        return fail_open()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
