#!/usr/bin/env python3
"""
Telemetry gate-check for the /learn automation loop.

Exits 0 (gate TRIPPED — /learn should run) when:
  - count(failures with recorded_at > last_learn_at) >= threshold, OR
  - (now - last_learn_at) > fallback_days (time-ceiling, even if count < threshold)

Exits 1 (gate NOT tripped — /learn should skip).

Flags:
  --verbose             Print count, watermark, and trip reason to stdout.
  --threshold N         Override default threshold (default: 5, env: LEARN_GATE_THRESHOLD).
  --fallback-days N     Override the time-ceiling fallback in days (default: 3).
  --print-watermark     Print last_learn_at from _state.json and exit 0 (no gate check).
  --count-only          Print new failure count and exit 0 (no gate check).

Stdlib only. No LLM, no network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso_utc(ts: str) -> datetime:
    """Parse ISO-8601 UTC string to an aware datetime.

    Handles:
      "2026-05-29T14:23:45Z"    (Z suffix — from this codebase)
      "2026-05-29T14:23:45+00:00"  (numeric UTC offset)
      "2026-05-29"              (date-only — treated as midnight UTC)
    """
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except ValueError:
        pass
    # Date-only fallback: treat as midnight UTC
    try:
        return datetime(
            *[int(x) for x in ts.split("T")[0].split("-")],
            tzinfo=timezone.utc,
        )
    except Exception:
        # Return epoch so malformed timestamps don't block learning.
        return datetime(2000, 1, 1, tzinfo=timezone.utc)


def _record_timestamp(record: dict) -> datetime:
    """Extract the sortable timestamp from a failure record.

    New records (post-#203) carry ``recorded_at``.
    Old records carry only ``date`` (YYYY-MM-DD string) and are treated as
    midnight UTC on that date for backward compatibility.
    """
    if "recorded_at" in record:
        return _parse_iso_utc(record["recorded_at"])
    # Backward-compat fallback: date + "T00:00:00Z"
    date_str = record.get("date", "2000-01-01")
    return _parse_iso_utc(date_str + "T00:00:00Z")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_watermark(state_path: Path) -> datetime:
    """Read last_learn_at from _state.json.

    Returns the epoch (2000-01-01 UTC) on missing file or malformed JSON so
    that the gate always trips on a fresh repo (fail-open toward learning).
    """
    epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
    if not state_path.exists():
        return epoch
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        raw = data.get("last_learn_at", "")
        if not raw:
            return epoch
        return _parse_iso_utc(raw)
    except Exception:
        return epoch


def count_new_failures(telemetry_root: Path, since: datetime) -> int:
    """Count failure records across all host shards where timestamp > since.

    Reads ``telemetry/<host>/failures.jsonl`` for every host subdirectory.
    Records without ``recorded_at`` fall back to ``date+"T00:00:00Z"``.
    Returns 0 if the telemetry root does not exist.
    """
    if not telemetry_root.exists():
        return 0

    count = 0
    for host_dir in telemetry_root.iterdir():
        if not host_dir.is_dir():
            continue
        shard = host_dir / "failures.jsonl"
        if not shard.exists():
            continue
        try:
            with open(shard, encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        record = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    ts = _record_timestamp(record)
                    if ts > since:
                        count += 1
        except OSError:
            pass  # shard vanished — skip

    return count


def check_gate(
    agents_root: Path,
    threshold: int = 5,
    fallback_days: int = 3,
    verbose: bool = False,
) -> bool:
    """Return True if /learn should run.

    Trip conditions (evaluated in order):
    1. time-ceiling: now - last_learn_at > fallback_days  (regardless of count)
    2. volume:       new_count >= threshold

    The threshold is read from the LEARN_GATE_THRESHOLD env var if set,
    overriding the ``threshold`` argument.  The fallback_days check runs
    independently — a low-failure period still gets periodic learning.

    Args:
        agents_root: Path to the ~/agents repo root.
        threshold:   Minimum new failures required to trip the gate.
        fallback_days: Maximum days since last learn before forcing a run.
        verbose:     If True, print reason to stdout.

    Returns:
        True if gate is tripped (caller should run /learn).
    """
    # Allow threshold override via env var.
    env_threshold = os.environ.get("LEARN_GATE_THRESHOLD", "").strip()
    if env_threshold.isdigit():
        threshold = int(env_threshold)

    state_path = agents_root / "telemetry" / "_state.json"
    telemetry_root = agents_root / "telemetry"

    watermark = load_watermark(state_path)
    now = datetime.now(timezone.utc)
    days_since = (now - watermark).total_seconds() / 86400
    new_count = count_new_failures(telemetry_root, watermark)

    # Trip condition 1: time ceiling
    if days_since > fallback_days:
        if verbose:
            print(
                f"gate TRIPPED (time-ceiling): {days_since:.1f} days since last learn "
                f"(>{fallback_days}d), {new_count} new failure(s), "
                f"watermark={watermark.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
        return True

    # Trip condition 2: volume threshold
    if new_count >= threshold:
        if verbose:
            print(
                f"gate TRIPPED (volume): {new_count} new failure(s) >= threshold {threshold}, "
                f"watermark={watermark.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
        return True

    if verbose:
        print(
            f"gate not tripped: {new_count} new failure(s) < threshold {threshold}, "
            f"{days_since:.1f} days since last learn (<={fallback_days}d), "
            f"watermark={watermark.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate check for /learn automation. Exits 0 if gate tripped, 1 if not.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print count and reason to stdout.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Minimum new failures to trip gate (default: 5, env: LEARN_GATE_THRESHOLD).",
    )
    parser.add_argument(
        "--fallback-days",
        type=int,
        default=3,
        dest="fallback_days",
        help="Days-since-last-learn ceiling to force a run (default: 3).",
    )
    parser.add_argument(
        "--print-watermark",
        action="store_true",
        dest="print_watermark",
        help="Print last_learn_at and exit 0 (no gate check).",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        dest="count_only",
        help="Print new failure count and exit 0 (no gate check).",
    )
    parser.add_argument(
        "--agents-root",
        type=Path,
        default=Path.home() / "agents",
        dest="agents_root",
        help="Path to agents repo root (default: ~/agents).",
    )
    args = parser.parse_args()

    agents_root: Path = args.agents_root

    if args.print_watermark:
        state_path = agents_root / "telemetry" / "_state.json"
        wm = load_watermark(state_path)
        print(wm.strftime("%Y-%m-%dT%H:%M:%SZ"))
        return 0

    if args.count_only:
        state_path = agents_root / "telemetry" / "_state.json"
        wm = load_watermark(state_path)
        n = count_new_failures(agents_root / "telemetry", wm)
        print(str(n))
        return 0

    tripped = check_gate(
        agents_root=agents_root,
        threshold=args.threshold,
        fallback_days=args.fallback_days,
        verbose=args.verbose,
    )
    return 0 if tripped else 1


if __name__ == "__main__":
    sys.exit(main())
