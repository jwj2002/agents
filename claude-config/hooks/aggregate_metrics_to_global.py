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

    Injects ``project`` if the record does not already carry it. Bad lines are
    skipped silently.
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
                # Use existing project tag on re-aggregation; else derive it.
                record.setdefault("project", project_name)
                key = (record.get("issue"), record.get("date"), record.get("project"))
                seen[key] = record  # last wins
    except OSError:
        pass  # file vanished between glob and open — harmless


def aggregate(kind: str, source_dirs: list, global_dir: Path) -> int:
    """Merge all per-project JSONL files of *kind* into the global file.

    Returns the number of records written.
    """
    seen: dict = {}  # key=(issue, date, project) -> record

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

    Deduplicates against existing shard content by (issue, date, project) key
    so re-running is idempotent. Only genuinely new records are appended.
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

        # Load existing keys to dedup
        existing_keys: set = set()
        if shard_file.exists():
            try:
                with open(shard_file, encoding="utf-8") as fh:
                    for raw in fh:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            rec = json.loads(raw)
                            key = (
                                rec.get("issue"),
                                rec.get("date"),
                                rec.get("project"),
                            )
                            existing_keys.add(key)
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass  # treat as empty shard — safe to re-append all

        # Append only new records
        appended = 0
        with open(shard_file, "a", encoding="utf-8") as fh:
            for record in failures:
                key = (record.get("issue"), record.get("date"), record.get("project"))
                if key in existing_keys:
                    continue
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")
                existing_keys.add(key)  # prevent within-batch duplicates
                appended += 1

        return appended

    except OSError as exc:
        log(f"write_host_shard: failed (non-fatal): {exc}")
        return 0


def _collect_failures(source_dirs: list) -> list:
    """Collect all failure records from source dirs (with project enrichment).

    Used to feed write_host_shard() — mirrors the read side of aggregate()
    but returns records as a list rather than writing them.
    """
    seen: dict = {}
    for source_dir in sorted(source_dirs):
        file = source_dir / "failures.jsonl"
        if not file.exists():
            continue
        project_name = _derive_project(source_dir)
        _load_source(file, project_name, seen)
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
