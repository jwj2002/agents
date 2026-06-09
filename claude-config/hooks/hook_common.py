"""Shared stdlib-only helpers for the hook scripts (#369).

These were copy-pasted across state_manager.py, capture_session_telemetry.py
and aggregate_metrics_to_global.py; a drift in timestamp precision between
copies would corrupt the /learn watermark invariant. One definition, three
importers — hooks in this directory import siblings without sys.path work
(the script's own dir is always on sys.path), and external callers already
insert ~/.claude/hooks.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with **microsecond** precision.

    Returns strings like ``"2026-05-29T14:23:45.123456Z"``.  Used as
    ``recorded_at`` on every new metrics/failure record so the telemetry
    gate can compare records across machines using a sortable timestamp.

    Watermark invariant (strict ``>``)
    ----------------------------------
    The /learn watermark is advanced to the **max consumed ``recorded_at``**
    in the snapshot — never to wall-clock ``now()``.  After that advance,
    any record whose ``recorded_at`` equals the watermark was, by definition,
    already consumed and is correctly excluded by the ``> watermark`` filter.
    Any record stamped *after* the snapshot (``recorded_at > consumed_max``)
    is still counted on the next run.  Microsecond precision makes collisions
    between concurrent records on the same machine extremely unlikely, and the
    strict ``>`` gate handles any equality case correctly.
    """
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def get_host_name() -> str:
    """Read the canonical host name for this machine.

    Mirrors lib/project_resolver.get_host_name() — duplicated at the hooks
    layer (once, here) to keep hooks stdlib-only.
    """
    host_name_path = Path.home() / ".claude" / "host-name"
    try:
        text = host_name_path.read_text(encoding="utf-8").strip()
        if text:
            return text
    except FileNotFoundError:
        pass
    import socket
    return (socket.gethostname() or "unknown").split(".")[0].lower()


def append_jsonl_fsync(target: Path, record: dict) -> None:
    """Append one JSON line to target; fsync for durability."""
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
