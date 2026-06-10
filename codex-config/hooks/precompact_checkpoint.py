#!/usr/bin/env python3
"""PreCompact hook: persist a compact resume checkpoint for Codex."""

from __future__ import annotations

import os
from pathlib import Path

from hook_common import HOOK_EXCEPTIONS, add_repo_to_path, emit, fail_open, read_payload


def main() -> int:
    add_repo_to_path()
    try:
        from lib.agent_state import write_codex_checkpoint

        payload = read_payload()
        path = write_codex_checkpoint(Path(os.getcwd()), payload)
        emit("PreCompact", message=f"checkpoint written: {path}")
    except HOOK_EXCEPTIONS:
        return fail_open()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
