#!/usr/bin/env python3
"""Stop hook: surface unfinished-work signals before Codex declares completion."""

from __future__ import annotations

import os
from pathlib import Path

from hook_common import HOOK_EXCEPTIONS, add_repo_to_path, emit, fail_open, read_payload


def main() -> int:
    add_repo_to_path()
    try:
        from lib.agent_completion import completion_warnings

        read_payload()
        warnings = completion_warnings(Path(os.getcwd()))
        if warnings:
            emit(
                "Stop",
                context=(
                    "Completion check found possible unfinished work: "
                    + " | ".join(warnings)
                ),
            )
    except HOOK_EXCEPTIONS:
        return fail_open()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
