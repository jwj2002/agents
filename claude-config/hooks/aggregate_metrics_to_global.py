#!/usr/bin/env python3
"""
Stop hook: aggregate per-project metrics/failures JSONL into global rollup.

After every session, merges:
  ~/agents/.claude/memory/{metrics,failures}.jsonl
  ~/projects/*/.claude/memory/{metrics,failures}.jsonl

into:
  ~/.claude/memory/{metrics,failures}.jsonl

Dedup key: (issue, date, project) — last record per key wins, matching the
append-overwrite semantics of flip_to_correction in state_manager.py.

Each record gains a `project` field derived from the repo root name if it
does not already carry one. Per-project source files are never modified.

Additionally writes per-host failure shards to:
  ~/agents/telemetry/<host>/failures.jsonl

Only failures (not metrics) are sharded — failures are the gate signal.
Sharding is idempotent: records already present (by issue, date, project key)
are not duplicated.

Always exits 0 (fail-open). Stdlib only.
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


def log(msg: str) -> None:
    """Append a timestamped line to ~/.claude/hooks.log."""
    try:
        log_path = Path.home() / ".claude" / "hooks.log"
        with open(log_path, "a") as fh:
            fh.write(
                f"[{datetime.now().isoformat()}] aggregate_metrics_global: {msg}\n"
            )
    except Exception:
        pass


def _event_id(issue, date: str, project: str, root_cause: str, details: str) -> str:
    """Stable content-hash for a failure record (M4 — mirrors state_manager._event_id).

    Duplicated here to keep this Stop hook stdlib-only (no sys.path manipulation).
    SHA-1 of pipe-delimited salient fields; collision-resistant enough for dedup.
    """
    payload = f"{issue}|{date}|{project}|{root_cause}|{details}"
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


def ensure_event_id(record: dict) -> dict:
    """Guarantee ``event_id`` is present on a failure record (M4 backward-compat).

    Records written before event_id was introduced lack the field.  This helper
    synthesises a stable hash from salient fields and injects it in-place,
    allowing deduplication to always key on ``event_id``.
    """
    if "event_id" in record:
        return record
    record["event_id"] = _event_id(
        issue=record.get("issue", 0),
        date=record.get("date", ""),
        project=record.get("project", ""),
        root_cause=record.get("root_cause", ""),
        details=record.get("details", ""),
    )
    return record


def normalize_record(record: dict) -> list:
    """Normalize a possibly-legacy compound failure record into canonical form (M5).

    Historical rows sometimes have the shape::

        {"type": "...", "issues": [1, 2], "root_causes": ["A", "B"], "date": "..."}

    rather than the canonical per-failure shape::

        {"issue": N, "root_cause": "...", "date": "...", ...}

    This helper expands a compound row into one record per (issue × root_cause)
    pair.  When the cartesian product is ambiguous (issues and root_causes lists
    differ in length and are both non-trivially sized), it emits a single
    normalized record with the first root_cause (or ``"LEGACY_COMPOUND"``).

    A synthesised ``recorded_at`` is derived from ``date+"T00:00:00Z"`` so the
    telemetry gate never treats these as perpetually-new after they have been
    consumed once.

    Normal (non-compound) records are returned in a single-element list
    unchanged.
    """
    # Fast path: already in canonical shape.
    if "issue" in record and "root_cause" in record:
        return [record]

    # Legacy compound shape detection.
    issues = record.get("issues") or []
    root_causes = record.get("root_causes") or []
    date = record.get("date", "2000-01-01")
    base_recorded_at = date + "T00:00:00Z"

    if not issues:
        # Has neither issue nor issues — synthesise a single stub record.
        stub = {
            "issue": 0,
            "date": date,
            "recorded_at": base_recorded_at,
            "root_cause": root_causes[0] if root_causes else "LEGACY_COMPOUND",
        }
        ensure_event_id(stub)
        return [stub]

    # Unambiguous expansion: 1 issue or 1 root_cause — simple cross-product.
    # Ambiguous: both lists have >1 element and different lengths → use first.
    if len(issues) > 1 and len(root_causes) > 1 and len(issues) != len(root_causes):
        single_rc = root_causes[0] if root_causes else "LEGACY_COMPOUND"
        out = {
            "issue": int(issues[0]),
            "date": date,
            "recorded_at": base_recorded_at,
            "root_cause": single_rc,
        }
        ensure_event_id(out)
        return [out]

    expanded = []
    for iss in issues:
        for rc in (root_causes or ["LEGACY_COMPOUND"]):
            rec = {
                "issue": int(iss),
                "date": date,
                "recorded_at": base_recorded_at,
                "root_cause": rc,
            }
            ensure_event_id(rec)
            expanded.append(rec)
    return expanded


def _derive_project(source_dir: Path) -> str:
    """Return the repo-root name for a given memory directory.

    Expected shapes:
      ~/agents/.claude/memory           → "agents"
      ~/projects/<name>/.claude/memory  → "<name>"

    Relies on source_dir.parent.parent.name being the repo root in both trees.
    """
    return source_dir.parent.parent.name


def _load_source(
    file: Path,
    project_name: str,
    seen: dict,
) -> None:
    """Read one JSONL file and merge records into *seen* (last record wins).

    Injects ``project`` if the record does not already carry it.  Normalizes
    legacy compound rows via ``normalize_record()`` (M5) and ensures every
    failure record has an ``event_id`` (M4).  Bad lines are skipped silently.

    Dedup key for failure records (M4): ``event_id`` — so two records with the
    same (issue, date, project) but *different* root_cause/details both survive
    in the local ``~/.claude/memory/`` view.  Metrics records (which have a
    ``status`` field) retain the legacy ``(issue, date, project)`` key because
    they don't have meaningful event_ids.
    """
    try:
        with open(file, encoding="utf-8") as fh:
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
                # Normalize legacy compound rows first (M5).
                # For metrics records (have "status" field), skip normalization.
                if "status" not in record:
                    records = normalize_record(record)
                else:
                    records = [record]
                for record in records:
                    # Use existing project tag on re-aggregation; else derive it.
                    record.setdefault("project", project_name)
                    if "status" not in record:
                        # Ensure event_id present (M4 backward-compat), then dedup
                        # by event_id so distinct root_causes for the same issue both
                        # survive (M4 local-merge fix).
                        ensure_event_id(record)
                        key = record["event_id"]
                    else:
                        # Metrics records: legacy (issue, date, project) key is fine.
                        key = (record.get("issue"), record.get("date"), record.get("project"))
                    seen[key] = record  # last wins
    except OSError:
        pass  # file vanished between glob and open — harmless


def aggregate(kind: str, source_dirs: list, global_dir: Path) -> int:
    """Merge all per-project JSONL files of *kind* into the global file.

    Returns the number of records written.
    """
    seen: dict = {}  # key=event_id (failures) or (issue,date,project) (metrics) -> record

    for source_dir in sorted(source_dirs):
        file = source_dir / f"{kind}.jsonl"
        if not file.exists():
            continue
        project_name = _derive_project(source_dir)
        _load_source(file, project_name, seen)

    global_dir.mkdir(parents=True, exist_ok=True)
    global_file = global_dir / f"{kind}.jsonl"

    # Sort output for deterministic, human-readable ordering.
    records = sorted(
        seen.values(),
        key=lambda r: (r.get("date", ""), str(r.get("issue", 0)), r.get("project", "")),
    )

    with open(global_file, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    return len(records)


def _get_host_name() -> str:
    """Read the canonical host name for this machine.

    Mirrors lib/project_resolver.get_host_name() — duplicated here to keep
    this hook stdlib-only (no sys.path manipulation required).
    """
    host_name_path = Path.home() / ".claude" / "host-name"
    try:
        text = host_name_path.read_text().strip()
        if text:
            return text
    except FileNotFoundError:
        pass
    import socket
    return (socket.gethostname() or "unknown").split(".")[0].lower()


def write_host_shard(failures: list, agents_root: Path) -> int:
    """Append new failure records to telemetry/<host>/failures.jsonl.

    Deduplicates against existing shard content by ``event_id`` (M4) so that
    two same-day same-issue failures with *different* root_cause both survive.
    Backward-compat: records without ``event_id`` have one synthesised by
    ``ensure_event_id()`` before the key comparison.

    Returns count of records appended. Fails open on IOError.

    Args:
        failures: List of failure record dicts (already enriched with project).
        agents_root: Path to the ~/agents repo root.

    Returns:
        Number of records appended (0 if all were already present).
    """
    if not failures:
        return 0

    try:
        host = _get_host_name()
        shard_dir = agents_root / "telemetry" / host
        shard_dir.mkdir(parents=True, exist_ok=True)
        shard_file = shard_dir / "failures.jsonl"

        # Load existing event_ids to dedup (M4)
        existing_ids: set = set()
        if shard_file.exists():
            try:
                with open(shard_file, encoding="utf-8") as fh:
                    for raw in fh:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            rec = json.loads(raw)
                            ensure_event_id(rec)
                            existing_ids.add(rec["event_id"])
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass  # treat as empty shard — safe to re-append all

        # Append only new records
        appended = 0
        with open(shard_file, "a", encoding="utf-8") as fh:
            for record in failures:
                ensure_event_id(record)
                eid = record["event_id"]
                if eid in existing_ids:
                    continue
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")
                existing_ids.add(eid)  # prevent within-batch duplicates
                appended += 1

        return appended

    except OSError as exc:
        log(f"write_host_shard: failed (non-fatal): {exc}")
        return 0


def _collect_failures(source_dirs: list) -> list:
    """Collect all failure records from source dirs (with project enrichment).

    Used to feed write_host_shard() — mirrors the read side of aggregate()
    but returns records as a list rather than writing them.

    Deduplicates by ``event_id`` (M4) so that two same-day same-issue failures
    with different root_cause are both preserved.  Normalizes legacy compound
    rows via ``normalize_record()`` (M5).  Backward-compat records without
    ``event_id`` have one synthesised by ``ensure_event_id()``.
    """
    seen: dict = {}  # event_id -> record (last wins within a source)
    for source_dir in sorted(source_dirs):
        file = source_dir / "failures.jsonl"
        if not file.exists():
            continue
        project_name = _derive_project(source_dir)
        try:
            with open(file, encoding="utf-8") as fh:
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
                    # Normalize legacy compound rows (M5)
                    records = normalize_record(record)
                    for rec in records:
                        rec.setdefault("project", project_name)
                        ensure_event_id(rec)
                        seen[rec["event_id"]] = rec  # last wins
        except OSError:
            pass
    return list(seen.values())


def main() -> int:
    try:
        # Drain stdin as expected by the Stop hook contract.
        _ = sys.stdin.read() if not sys.stdin.isatty() else ""

        home = Path.home()

        # Build source directory list (never include the global target itself).
        source_dirs: list[Path] = []

        agents_memory = home / "agents" / ".claude" / "memory"
        if agents_memory.exists():
            source_dirs.append(agents_memory)

        projects_root = home / "projects"
        if projects_root.exists():
            for candidate in projects_root.iterdir():
                mem = candidate / ".claude" / "memory"
                if mem.is_dir():
                    source_dirs.append(mem)

        global_dir = home / ".claude" / "memory"

        totals = {}
        for kind in ("metrics", "failures"):
            count = aggregate(kind, source_dirs, global_dir)
            totals[kind] = count

        # Write per-host failure shard to ~/agents/telemetry/<host>/
        # Failures are the gate signal; metrics (PASS records) are kept local.
        agents_root = home / "agents"
        if agents_root.is_dir():
            failures = _collect_failures(source_dirs)
            sharded = write_host_shard(failures, agents_root)
            log(
                f"done — metrics={totals['metrics']} failures={totals['failures']} "
                f"sources={len(source_dirs)} sharded={sharded}"
            )
        else:
            log(
                f"done — metrics={totals['metrics']} failures={totals['failures']} "
                f"sources={len(source_dirs)} shard=skip(no agents root)"
            )

    except Exception as exc:
        log(f"error (non-fatal): {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
