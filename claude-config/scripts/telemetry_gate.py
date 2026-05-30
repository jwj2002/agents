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
import hashlib
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
# Legacy-record normalization (M5)
# ---------------------------------------------------------------------------

def _normalize_record(record: dict) -> list:
    """Normalize a possibly-legacy compound failure record into canonical form.

    Historical rows sometimes have the shape::

        {"type": "...", "issues": [1, 2], "root_causes": ["A", "B"], "date": "..."}

    This helper expands them into one canonical record per (issue × root_cause)
    pair, or emits a single stub when expansion is ambiguous.  A synthesised
    ``recorded_at`` derived from ``date+"T00:00:00Z"`` ensures these rows
    never appear perpetually-new after their max ``recorded_at`` is consumed.

    Normal (canonical) records are returned in a single-element list unchanged.
    """
    # Fast path: already canonical.
    if "issue" in record and "root_cause" in record:
        return [record]

    issues = record.get("issues") or []
    root_causes = record.get("root_causes") or []
    date = record.get("date", "2000-01-01")
    base_recorded_at = date + "T00:00:00Z"

    if not issues:
        stub = {
            "issue": 0,
            "date": date,
            "recorded_at": base_recorded_at,
            "root_cause": root_causes[0] if root_causes else "LEGACY_COMPOUND",
        }
        return [stub]

    # Ambiguous multi-list expansion → use first of each.
    if len(issues) > 1 and len(root_causes) > 1 and len(issues) != len(root_causes):
        return [{
            "issue": int(issues[0]),
            "date": date,
            "recorded_at": base_recorded_at,
            "root_cause": root_causes[0] if root_causes else "LEGACY_COMPOUND",
        }]

    expanded = []
    for iss in issues:
        for rc in (root_causes or ["LEGACY_COMPOUND"]):
            expanded.append({
                "issue": int(iss),
                "date": date,
                "recorded_at": base_recorded_at,
                "root_cause": rc,
            })
    return expanded


def _event_id(issue, date: str, project: str, root_cause: str, details: str) -> str:
    """Stable content-hash for dedup (M4 — mirrors state_manager._event_id)."""
    payload = f"{issue}|{date}|{project}|{root_cause}|{details}"
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


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


def _iter_shard_records(telemetry_root: Path):
    """Yield normalized failure records from all host shards (M5).

    Iterates every ``telemetry/<host>/failures.jsonl``.  Legacy compound rows
    are expanded via ``_normalize_record()`` so they never appear perpetually-new.
    Malformed lines and vanished shards are silently skipped (fail-open).
    """
    if not telemetry_root.exists():
        return
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
                    for normalized in _normalize_record(record):
                        yield normalized
        except OSError:
            pass  # shard vanished — skip


def count_new_failures(telemetry_root: Path, since: datetime) -> int:
    """Count failure records across all host shards where timestamp > since.

    Reads ``telemetry/<host>/failures.jsonl`` for every host subdirectory.
    Normalizes legacy compound rows (M5).
    Records without ``recorded_at`` fall back to ``date+"T00:00:00Z"``.
    Returns 0 if the telemetry root does not exist.
    """
    count = 0
    for record in _iter_shard_records(telemetry_root):
        ts = _record_timestamp(record)
        if ts > since:
            count += 1
    return count


def compute_consumed_max(telemetry_root: Path, since: datetime) -> datetime | None:
    """Return the maximum ``recorded_at`` of all failure records with ts > since (B2).

    Used by /learn Step 6.6 to advance the watermark to **max consumed
    recorded_at** rather than wall-clock now().  This guarantees any record
    stamped after the snapshot (``recorded_at > consumed_max``) is still
    counted on the next run.

    Returns ``None`` if there are no new records (gate not tripped by volume).
    """
    consumed_max: datetime | None = None
    for record in _iter_shard_records(telemetry_root):
        ts = _record_timestamp(record)
        if ts > since:
            if consumed_max is None or ts > consumed_max:
                consumed_max = ts
    return consumed_max


def compute_consumed_max_from_snapshot(snapshot_file: Path) -> datetime | None:
    """Return the maximum ``recorded_at`` across all records in a snapshot file (B2).

    This is the snapshot-safe variant of ``compute_consumed_max``: it computes
    the watermark from the **already-materialized union snapshot** (``UNION_FILE``
    from /learn Step 0d) rather than re-scanning the live ``telemetry/`` directory.

    Because the snapshot was taken at a fixed moment, any record appended to the
    live telemetry dir AFTER the snapshot was created is NOT reflected here — which
    is precisely the B2 invariant: the watermark advances only to the max
    ``recorded_at`` of the records that were actually analyzed, never further.

    Normalizes legacy compound rows (M5) so their synthesised ``recorded_at``
    (``date+"T00:00:00Z"``) is included in the max.

    Returns ``None`` if the snapshot is empty or does not exist.
    """
    consumed_max: datetime | None = None
    if not snapshot_file.exists():
        return None
    try:
        with open(snapshot_file, encoding="utf-8") as fh:
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
                for normalized in _normalize_record(record):
                    ts = _record_timestamp(normalized)
                    if consumed_max is None or ts > consumed_max:
                        consumed_max = ts
    except OSError:
        pass
    return consumed_max


def write_watermark_monotonic(
    state_path: Path,
    consumed_max: datetime,
    host: str,
) -> bool:
    """Write last_learn_at = max(existing, consumed_max) atomically (M7).

    Monotonicity guarantee: re-reads the current _state.json immediately before
    writing (post-rebase) and refuses to move the watermark backward.  Uses
    temp+rename for POSIX atomicity.

    Args:
        state_path: Path to telemetry/_state.json.
        consumed_max: Max ``recorded_at`` from the consumed snapshot (B2).
        host: Canonical hostname for ``last_learn_host`` field.

    Returns:
        True if the watermark was advanced; False if the existing watermark was
        already >= consumed_max (no write performed — no-op).
    """
    # Re-read current watermark immediately before write (M7 monotonicity).
    existing = load_watermark(state_path)
    # Never move backward.
    if existing >= consumed_max:
        return False

    new_ts = consumed_max.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    state: dict = {
        "last_learn_at": new_ts,
        "last_learn_host": host,
        "version": 1,
    }
    # Preserve any extra fields from the existing file.
    if state_path.exists():
        try:
            existing_data = json.loads(state_path.read_text(encoding="utf-8"))
            for k, v in existing_data.items():
                if k not in state:
                    state[k] = v
        except Exception:
            pass

    tmp = state_path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        tmp.rename(state_path)  # atomic on APFS / ext4
        return True
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


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
        "--compute-consumed-max",
        action="store_true",
        dest="compute_consumed_max",
        help=(
            "Print max recorded_at of new failures (consumed_max for B2 watermark) "
            "and exit 0.  Prints empty string if no new failures.  "
            "When --snapshot FILE is also given, computes from the snapshot file "
            "rather than the live telemetry/ dir (B2 safe variant)."
        ),
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        dest="snapshot",
        help=(
            "Path to a materialized union snapshot JSONL file.  "
            "When provided with --compute-consumed-max, computes consumed_max "
            "from the snapshot rows rather than re-scanning the live telemetry/ dir. "
            "Ensures the watermark reflects only records that were analyzed — "
            "not any record appended after the snapshot was taken (B2)."
        ),
    )
    parser.add_argument(
        "--write-watermark",
        metavar="CONSUMED_MAX",
        dest="write_watermark",
        help=(
            "Advance last_learn_at to max(existing, CONSUMED_MAX) atomically (M7 "
            "monotonic write).  CONSUMED_MAX must be an ISO-8601 UTC string.  "
            "Exits 0 on success; exits 2 if watermark is already >= CONSUMED_MAX "
            "(no-op — not an error in practice, just informational)."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        dest="host",
        help="Host name for --write-watermark (default: auto-detected).",
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

    if args.compute_consumed_max:
        if args.snapshot is not None:
            # B2 safe variant: compute from the already-materialized snapshot so
            # that records appended to the live telemetry/ dir after the snapshot
            # was taken do NOT influence the watermark.
            cmax = compute_consumed_max_from_snapshot(args.snapshot)
        else:
            # Legacy path: scan the live telemetry/ dir (only new records since wm).
            state_path = agents_root / "telemetry" / "_state.json"
            wm = load_watermark(state_path)
            cmax = compute_consumed_max(agents_root / "telemetry", wm)
        if cmax is not None:
            # Microsecond precision (M3): format as YYYY-MM-DDTHH:MM:SS.ffffffZ
            print(cmax.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z")
        else:
            print("")
        return 0

    if args.write_watermark:
        import socket
        state_path = agents_root / "telemetry" / "_state.json"
        try:
            consumed_max = _parse_iso_utc(args.write_watermark)
        except Exception as exc:
            print(f"ERROR: could not parse CONSUMED_MAX={args.write_watermark!r}: {exc}", file=sys.stderr)
            return 1
        host = args.host or (socket.gethostname() or "unknown").split(".")[0].lower()
        try:
            advanced = write_watermark_monotonic(state_path, consumed_max, host)
        except OSError as exc:
            print(f"ERROR: could not write watermark: {exc}", file=sys.stderr)
            return 1
        if not advanced:
            print(f"no-op: existing watermark >= {args.write_watermark}", file=sys.stderr)
            return 2  # non-zero but not an error; caller can ignore
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
