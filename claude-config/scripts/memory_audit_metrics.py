#!/usr/bin/env python3
"""memory_audit_metrics.py — weekly deterministic memory-recall trend.

Computes the *decisive* memory metrics (the ones the qualitative audit calls
out) from the LOCAL transcript store + memory store, and appends one dated row
to a trend log so the write:read ratio can be watched over time.

This is the cheap, deterministic half of the memory-health loop (run weekly by
launchd); the full qualitative audit (graded report) runs monthly via headless
claude. No LLM, no network — pure file scan.

Counts, over a rolling window (default 7 days):
  - memory_writes   : Write/Edit/MultiEdit/NotebookEdit on a */memory/*.md file
  - fact_reads      : Read on a */memory/ fact file (excludes MEMORY.md index)
  - recall_invocations : Bash commands invoking `memory recall` (the new read path)
  - sessions, sessions_with_recall (any fact_read or recall in the session)
And store-level (point-in-time):
  - total_facts, cold_facts_pct (fact files untouched >30d)

reads_total = fact_reads + recall_invocations; write:read ratio uses reads_total.

Trend log: ~/.claude/memory-trend.jsonl (local; never in the code repo).
Usage:  memory_audit_metrics.py [--days N] [--print-only]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
TREND_LOG = Path.home() / ".claude" / "memory-trend.jsonl"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
COLD_DAYS = 30
MEMORY_SEG = "/memory/"
INDEX_NAME = "MEMORY.md"


def _is_memory_md(path: str) -> bool:
    return MEMORY_SEG in path and path.endswith(".md")


def _is_fact_file(path: str) -> bool:
    return _is_memory_md(path) and not path.endswith("/" + INDEX_NAME)


def _iter_tool_uses(line_obj):
    """Yield (tool_name, input_dict) for every tool_use block in a transcript line."""
    msg = line_obj.get("message")
    if not isinstance(msg, dict):
        return
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield block.get("name", ""), block.get("input", {}) or {}


def _line_ts(line_obj) -> float | None:
    ts = line_obj.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def scan_transcripts(cutoff: float):
    writes = fact_reads = recalls = 0
    sessions = 0
    sessions_with_recall = 0
    if not PROJECTS_ROOT.is_dir():
        return writes, fact_reads, recalls, sessions, sessions_with_recall

    # Only parse transcripts touched within the window (+1d buffer) — a file not
    # modified in the window holds no in-window events.
    file_cutoff = cutoff - 86400
    for tpath in PROJECTS_ROOT.glob("*/*.jsonl"):
        if MEMORY_SEG in str(tpath):  # skip the memory store itself
            continue
        try:
            if tpath.stat().st_mtime < file_cutoff:
                continue
        except OSError:
            continue
        sessions += 1
        session_recalled = False
        try:
            with tpath.open(encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    ts = _line_ts(obj)
                    if ts is not None and ts < cutoff:
                        continue
                    for name, inp in _iter_tool_uses(obj):
                        if name in WRITE_TOOLS and _is_memory_md(str(inp.get("file_path", ""))):
                            writes += 1
                        elif name == "Read" and _is_fact_file(str(inp.get("file_path", ""))):
                            fact_reads += 1
                            session_recalled = True
                        elif name == "Bash" and "memory recall" in str(inp.get("command", "")):
                            recalls += 1
                            session_recalled = True
        except OSError:
            continue
        if session_recalled:
            sessions_with_recall += 1
    return writes, fact_reads, recalls, sessions, sessions_with_recall


def store_stats():
    total = cold = 0
    now = time.time()
    cold_cutoff = now - COLD_DAYS * 86400
    if not PROJECTS_ROOT.is_dir():
        return total, cold
    for fact in PROJECTS_ROOT.glob("*/memory/*.md"):
        if fact.name == INDEX_NAME:
            continue
        total += 1
        try:
            if fact.stat().st_mtime < cold_cutoff:
                cold += 1
        except OSError:
            pass
    return total, cold


def autoinject_stats(cutoff: float) -> tuple[int, int]:
    """(sessions auto-injected, facts injected) within the window, from the
    SessionStart hook's sidecar log (#365). Auto-recall is counted separately
    from manual recall so the trend can tell push from pull."""
    log = Path.home() / ".claude" / "memory-autoinject.jsonl"
    injections = facts = 0
    try:
        with log.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    ts = datetime.fromisoformat(rec["ts"]).timestamp()
                except (ValueError, KeyError, TypeError):
                    continue
                if ts >= cutoff:
                    injections += 1
                    facts += int(rec.get("facts_injected", 0))
    except OSError:
        pass
    return injections, facts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="memory_audit_metrics")
    ap.add_argument("--days", type=int, default=7, help="rolling window in days (default 7)")
    ap.add_argument("--print-only", action="store_true", help="print the row; do not append to the trend log")
    args = ap.parse_args(argv)

    cutoff = time.time() - args.days * 86400
    writes, fact_reads, recalls, sessions, sessions_with_recall = scan_transcripts(cutoff)
    total_facts, cold = store_stats()
    reads_total = fact_reads + recalls

    row = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "window_days": args.days,
        "total_facts": total_facts,
        "cold_facts_pct": round(100 * cold / total_facts, 1) if total_facts else 0.0,
        "memory_writes": writes,
        "fact_reads": fact_reads,
        "recall_invocations": recalls,
        "reads_total": reads_total,
        "write_read_ratio": (
            round(writes / reads_total, 2) if reads_total else (float(writes) if writes else 0.0)
        ),
        "sessions": sessions,
        "sessions_with_recall": sessions_with_recall,
        "active_recall_pct": round(100 * sessions_with_recall / sessions, 1) if sessions else 0.0,
    }
    auto_sessions, auto_facts = autoinject_stats(cutoff)
    row["auto_inject_sessions"] = auto_sessions
    row["auto_inject_facts"] = auto_facts

    print(json.dumps(row))
    if not args.print_only:
        try:
            with TREND_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        except OSError as e:
            print(f"warning: could not append to {TREND_LOG}: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
