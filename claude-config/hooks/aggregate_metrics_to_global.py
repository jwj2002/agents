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

        log(
            f"done — metrics={totals['metrics']} failures={totals['failures']} "
            f"sources={len(source_dirs)}"
        )

    except Exception as exc:
        log(f"error (non-fatal): {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
