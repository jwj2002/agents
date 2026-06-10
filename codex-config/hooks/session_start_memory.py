#!/usr/bin/env python3
"""SessionStart hook: inject bounded, verify-first memory context."""

from __future__ import annotations

import os
from pathlib import Path

from hook_common import HOOK_EXCEPTIONS, add_repo_to_path, emit, fail_open, read_payload


def main() -> int:
    add_repo_to_path()
    try:
        from lib.agent_memory import render_codex_memory_context

        read_payload()
        context = render_codex_memory_context(Path(os.getcwd()))
        if context:
            emit("SessionStart", context=context)
    except HOOK_EXCEPTIONS:
        return fail_open()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
