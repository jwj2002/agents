#!/usr/bin/env python3
"""PostToolUse hook: warn when Codex context headroom gets low."""

from __future__ import annotations

from hook_common import HOOK_EXCEPTIONS, add_repo_to_path, emit, fail_open, read_payload


def main() -> int:
    add_repo_to_path()
    try:
        from lib.context_budget import should_warn

        payload = read_payload()
        severity, pct = should_warn(payload)
        if severity != "NONE" and pct is not None:
            emit(
                "PostToolUse",
                context=(
                    f"Context headroom is {pct:.0f}% ({severity}). Finish the current "
                    "task or compact before starting new complex work."
                ),
            )
    except HOOK_EXCEPTIONS:
        return fail_open()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
