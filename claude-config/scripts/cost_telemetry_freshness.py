"""Cost-telemetry freshness watchdog (cost-telemetry-v0 §D6).

The dead-man's-switch for the usage collector — deliberately ~tiny (NOT the elaborate watchdog.py).
It keys off the collector's `last_success` in `cost-telemetry.state`, NOT shard mtime alone: a
successful run that wrote zero new rows must NOT false-alarm (its `usage.jsonl` mtime is old but the
collector is healthy). Missing shard or missing state is independently alarming.

Meant to run from the SessionStart hook (so a stalled collector is noticed) AND as `--check`.
NOTE: wiring it into SessionStart is part of the deferred activation/smoke test — this module only
provides the check + CLI; it is not registered as a hook here.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE = Path.home() / ".claude" / "telemetry"
DEFAULT_LOG = Path.home() / ".claude" / "logs" / "cost-telemetry.log"
STATE_FILENAME = "cost-telemetry.state"
SHARD_FILENAME = "usage.jsonl"
FRESHNESS_SLA_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def check(
    base_dir, *, sla_days: int = FRESHNESS_SLA_DAYS, now: datetime | None = None
) -> tuple[bool, str]:
    """Return (stale, reason). stale=True ⇒ a warning should fire. Never raises."""
    now = now or _now()
    base = Path(base_dir)
    state_path = base / STATE_FILENAME
    shard_path = base / SHARD_FILENAME

    if not state_path.exists():
        return True, "collector has never run (no cost-telemetry.state)"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        last_success = state.get("last_success") if isinstance(state, dict) else None
    except (json.JSONDecodeError, OSError, ValueError):
        return True, "cost-telemetry.state unreadable"
    if not last_success:
        return True, "no successful collection recorded (last_success missing)"
    try:
        ts = datetime.fromisoformat(str(last_success))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return True, f"last_success unparseable: {last_success!r}"

    age_days = (now - ts).total_seconds() / 86400.0
    if age_days > sla_days:
        return (
            True,
            f"stale: last successful collection {age_days:.1f}d ago (SLA {sla_days}d)",
        )
    # Healthy run, but the shard itself must exist (a missing shard after a 'success' is alarming).
    if not shard_path.exists():
        return True, "usage.jsonl missing despite a recent successful run"
    return False, f"fresh: last success {age_days:.1f}d ago"


def _log(log_path, msg: str) -> None:
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(log_path).open("a", encoding="utf-8") as fh:
            fh.write(f"{_now().isoformat()} [freshness] {msg}\n")
    except OSError:
        pass  # logging must never break the hook


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cost-telemetry freshness watchdog")
    ap.add_argument("--base", default=str(DEFAULT_BASE))
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    ap.add_argument("--sla-days", type=int, default=FRESHNESS_SLA_DAYS)
    ap.add_argument(
        "--check", action="store_true", help="print status regardless of freshness"
    )
    args = ap.parse_args(argv)

    stale, reason = check(args.base, sla_days=args.sla_days)
    if stale:
        _log(args.log, reason)
        print(f"⚠ cost-telemetry {reason}", file=sys.stderr)
    elif args.check:
        print(f"cost-telemetry {reason}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
