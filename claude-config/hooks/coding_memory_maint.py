#!/usr/bin/env python3
"""SessionStart hook: cross-platform daily coding-memory maintenance.

Runs `ingest` + safe `doctor --prune-expired` at most once per day, in the
BACKGROUND, ONLY where the personal store is configured (residency gate — work
machines aren't). Never blocks or fails session start (fail-open). Works on
macOS / WSL / Linux with no per-OS scheduler (cron/launchd/systemd).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path(os.path.expanduser("~/.coding_memory.env"))
STAMP = Path(os.path.expanduser("~/.claude/.coding-memory-maint-stamp"))
WRAPPER = Path(
    os.path.expanduser("~/agents/claude-config/scripts/coding-memory-maint.sh")
)


def _config_ok(path: Path = CONFIG) -> bool:
    """Is the personal store configured here? Residency gate: a work machine whose
    config doesn't point at the personal store (or has none) never runs maintenance."""
    if not path.exists():
        return False
    txt = path.read_text(errors="replace")
    return "CODING_MEMORY_SSH=" in txt or "DATABASE_URL=" in txt


def _due(stamp_path: Path, today: str) -> bool:
    if not stamp_path.exists():
        return True
    d = (
        datetime.fromtimestamp(stamp_path.stat().st_mtime, tz=timezone.utc)
        .date()
        .isoformat()
    )
    return d != today


def _spawn(wrapper: Path) -> None:
    subprocess.Popen(  # detached, fully backgrounded; never waited on
        ["/bin/bash", str(wrapper)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def maybe_run(
    stamp_path=STAMP, today=None, config_ok=None, spawn_fn=_spawn, wrapper=WRAPPER
) -> bool:
    """Spawn daily maintenance if configured + due. Returns True if it spawned."""
    today = today or datetime.now(timezone.utc).date().isoformat()
    ok = _config_ok() if config_ok is None else config_ok
    if not ok or not _due(stamp_path, today):
        return False
    spawn_fn(wrapper)
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.touch()
    return True


def main() -> int:
    try:
        maybe_run()
    except Exception:  # fail-open: maintenance must never break session start
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
