#!/usr/bin/env python3
"""decision — view, list, create, and update entries in knowledge/decisions/.

Closes the writer-gap surfaced in `specs/knowledge-surfaces.md` (A-019). Before
this CLI, the decisions/ surface was hand-edit-only, and at the user's rate of
real architectural decisions that meant the surface was decaying into a
graveyard. This CLI gives it a writer that matches the
action/dashboard/project/review-session pattern.

## Schema

Canonical form (matches D-042 family). Old D-098-style records that put
`linked_patterns`, `linked_issues`, `linked_prs`, `related_decisions` at the
top level are read transparently and normalized to the nested form on write.

    schema_version: 1
    id: D-NNN
    date: YYYY-MM-DD
    project: <name>
    topic: <category>
    title: <short>
    context: <multiline>
    decision: <multiline>
    alternatives: []
    reasoning: <multiline>
    outcome: <multiline | null>
    linked:
      patterns: []
      issues: []
      prs: []
      related_decisions: []
    created_at: YYYY-MM-DD

## Index

`knowledge/decisions/index.yaml` maintains three views:
  by_project.<name>: [{id, topic, title, date}, ...]
  by_topic.<topic>: [<id>, ...]
  by_pattern.<pat-id>: [<id>, ...]

Update on every `--new` (all three views) and on `--add-pattern` (by_pattern only).

## Modes

  decision D-042                            # read one
  decision --list [--project X] [--topic Y] # list all / filtered
  decision --new --title "..." --decision "..." [--project X] [--topic Y] \\
           [--context "..."] [--reasoning "..."]
  decision D-042 --outcome "..."            # fill outcome later
  decision D-042 --add-pattern pat-X        # append to linked.patterns + by_pattern index
  decision D-042 --add-pr 147               # append to linked.prs
  decision D-042 --add-issue 148            # append to linked.issues
  decision D-042 --add-related D-091        # append to linked.related_decisions

This CLI does NOT auto-commit; print suggested git command after writes.
Consistent with #141 / #143 precedent.

Alias: `alias decision='python3 ~/agents/decision/cli.py'`
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml

# Repo root for lib imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import project_resolver  # noqa: E402
from lib.project_resolver import (  # noqa: E402
    ProjectResolutionError,
    resolve_with_picker,
)

HOME = Path.home()
DECISIONS_DIR = HOME / "agents" / "knowledge" / "decisions"
INDEX_PATH = DECISIONS_DIR / "index.yaml"

ALLOWED_TOPICS = (
    "auth", "database", "api", "frontend", "infrastructure",
    "workflow", "testing", "observability",
    "orchestration", "philosophy", "architecture", "export",
)

DECISION_FIELDS_ORDER = [
    "schema_version", "id", "date", "project", "topic", "title",
    "context", "decision", "alternatives", "reasoning", "outcome",
    "linked", "created_at",
]
LINKED_FIELDS_ORDER = ["patterns", "issues", "prs", "related_decisions"]


class DecisionError(Exception):
    """User-facing error → stderr + exit 1."""


# ---------- YAML I/O ----------

def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _dump_yaml(data: dict, field_order: list[str]) -> str:
    ordered: dict = {}
    for k in field_order:
        if k in data:
            ordered[k] = data[k]
    for k, v in data.items():
        if k not in ordered:
            ordered[k] = v
    return yaml.safe_dump(
        ordered, sort_keys=False, default_flow_style=False,
        allow_unicode=True, width=80,
    )


def load_decision(path: Path) -> dict:
    if not path.exists():
        raise DecisionError(f"decision YAML not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise DecisionError(f"{path}: top-level YAML must be a mapping")
    return _normalize_schema(data)


def _normalize_schema(data: dict) -> dict:
    """Fold old flat linked_* / related_decisions top-level keys into linked: nested.

    Idempotent — calling it on already-normalized data returns the data unchanged.
    """
    if "linked" not in data:
        data["linked"] = {}
    linked = data["linked"]
    if not isinstance(linked, dict):
        linked = {}
    for old, new in (
        ("linked_patterns", "patterns"),
        ("linked_issues", "issues"),
        ("linked_prs", "prs"),
        ("related_decisions", "related_decisions"),
    ):
        if old in data:
            value = data.pop(old)
            if value:  # skip empty/None
                linked.setdefault(new, [])
                if isinstance(value, list):
                    for item in value:
                        if item not in linked[new]:
                            linked[new].append(item)
    for k in LINKED_FIELDS_ORDER:
        linked.setdefault(k, [])
    data["linked"] = linked
    return data


def write_decision(path: Path, data: dict) -> None:
    data = _normalize_schema(data)
    if isinstance(data.get("linked"), dict):
        data["linked"] = {k: data["linked"].get(k, []) for k in LINKED_FIELDS_ORDER}
    text = _dump_yaml(data, DECISION_FIELDS_ORDER)
    _atomic_write(path, text)


# ---------- ID assignment ----------

def list_existing_ids() -> list[str]:
    if not DECISIONS_DIR.exists():
        return []
    ids = []
    for p in DECISIONS_DIR.glob("D-*.yaml"):
        m = re.match(r"^D-(\d+)$", p.stem)
        if m:
            ids.append(p.stem)
    return sorted(ids)


def next_id() -> str:
    """Return the next D-NNN id (max + 1, zero-padded to 3 digits minimum)."""
    existing = list_existing_ids()
    max_n = 0
    for did in existing:
        try:
            n = int(did.split("-", 1)[1])
            max_n = max(max_n, n)
        except (ValueError, IndexError):
            continue
    return f"D-{max_n + 1:03d}"


def decision_path(decision_id: str) -> Path:
    return DECISIONS_DIR / f"{decision_id}.yaml"


# ---------- index management ----------

def load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"by_project": {}, "by_topic": {}, "by_pattern": {}}
    data = yaml.safe_load(INDEX_PATH.read_text()) or {}
    if not isinstance(data, dict):
        return {"by_project": {}, "by_topic": {}, "by_pattern": {}}
    for k in ("by_project", "by_topic", "by_pattern"):
        if not isinstance(data.get(k), dict):
            data[k] = {}
    return data


def write_index(data: dict) -> None:
    text = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False,
        allow_unicode=True, width=80,
    )
    _atomic_write(INDEX_PATH, text)


def _index_add_to_project(idx: dict, decision: dict) -> None:
    proj = decision["project"]
    entries = idx.setdefault("by_project", {}).setdefault(proj, [])
    if any(e.get("id") == decision["id"] for e in entries):
        return
    entries.append({
        "id": decision["id"],
        "topic": decision.get("topic", ""),
        "title": decision.get("title", ""),
        "date": decision.get("date", ""),
    })


def _index_add_to_topic(idx: dict, decision: dict) -> None:
    topic = decision.get("topic")
    if not topic:
        return
    ids = idx.setdefault("by_topic", {}).setdefault(topic, [])
    if decision["id"] not in ids:
        ids.append(decision["id"])


def _index_add_to_pattern(idx: dict, decision_id: str, pattern: str) -> None:
    ids = idx.setdefault("by_pattern", {}).setdefault(pattern, [])
    if decision_id not in ids:
        ids.append(decision_id)


def update_index_for_new(decision: dict) -> None:
    idx = load_index()
    _index_add_to_project(idx, decision)
    _index_add_to_topic(idx, decision)
    for pat in decision.get("linked", {}).get("patterns", []) or []:
        _index_add_to_pattern(idx, decision["id"], pat)
    write_index(idx)


def update_index_for_pattern(decision_id: str, pattern: str) -> None:
    idx = load_index()
    _index_add_to_pattern(idx, decision_id, pattern)
    write_index(idx)


# ---------- create ----------

def today_iso() -> str:
    return date.today().isoformat()


def pick_topic(no_prompt: bool) -> str:
    if no_prompt:
        raise DecisionError(
            f"--topic required in --no-prompt mode (allowed: {', '.join(ALLOWED_TOPICS)})"
        )
    if not sys.stdin.isatty():
        raise DecisionError("cannot prompt for topic: stdin is not a TTY")
    print("Select topic:")
    for i, t in enumerate(ALLOWED_TOPICS, 1):
        print(f"  {i}) {t}")
    print(f"  {len(ALLOWED_TOPICS) + 1}) (other — type your own)")
    for _ in range(3):
        try:
            raw = input(f"Choose [1-{len(ALLOWED_TOPICS) + 1}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise DecisionError("topic selection cancelled")
        try:
            n = int(raw)
        except ValueError:
            print("  invalid — enter a number")
            continue
        if 1 <= n <= len(ALLOWED_TOPICS):
            return ALLOWED_TOPICS[n - 1]
        if n == len(ALLOWED_TOPICS) + 1:
            try:
                custom = input("Enter custom topic: ").strip()
            except (EOFError, KeyboardInterrupt):
                raise DecisionError("topic selection cancelled")
            if custom:
                return custom
            print("  empty — try again")
            continue
        print("  out of range")
    raise DecisionError("too many invalid topic selections")


def create_decision(args: argparse.Namespace) -> dict:
    project = resolve_with_picker(args.project, no_prompt=args.no_prompt)
    topic = args.topic
    if topic is None:
        topic = pick_topic(args.no_prompt)
    today = today_iso()
    decision = {
        "schema_version": 1,
        "id": next_id(),
        "date": today,
        "project": project,
        "topic": topic,
        "title": args.title,
        "context": args.context or "",
        "decision": args.decide_text,
        "alternatives": [],
        "reasoning": args.reasoning or "",
        "outcome": None,
        "linked": {k: [] for k in LINKED_FIELDS_ORDER},
        "created_at": today,
    }
    return decision


# ---------- update ----------

def apply_update(data: dict, args: argparse.Namespace) -> list[str]:
    """Mutate `data` based on update flags. Returns human-readable change list."""
    changes: list[str] = []
    linked = data["linked"]

    if args.outcome is not None:
        old = data.get("outcome")
        data["outcome"] = args.outcome
        if old != args.outcome:
            changes.append(f"outcome → {args.outcome!r}")

    for pat in (args.add_pattern or []):
        if pat not in linked["patterns"]:
            linked["patterns"].append(pat)
            changes.append(f"+linked.pattern: {pat}")

    for issue in (args.add_issue or []):
        normalized = issue if issue.startswith("#") else f"#{issue}"
        if normalized not in linked["issues"]:
            linked["issues"].append(normalized)
            changes.append(f"+linked.issue: {normalized}")

    for pr in (args.add_pr or []):
        normalized = pr if pr.startswith("#") else f"#{pr}"
        if normalized not in linked["prs"]:
            linked["prs"].append(normalized)
            changes.append(f"+linked.pr: {normalized}")

    for rd in (args.add_related or []):
        if rd not in linked["related_decisions"]:
            linked["related_decisions"].append(rd)
            changes.append(f"+linked.related: {rd}")

    return changes


# ---------- rendering ----------

def _term_width() -> int:
    return shutil.get_terminal_size((90, 24)).columns


def _truncate(s: str, w: int) -> str:
    return s if len(s) <= w else s[: w - 1] + "…"


def render_decision(data: dict) -> str:
    width = max(70, min(_term_width(), 110))
    lines = [
        f"DECISION {data.get('id', '?')}",
        "─" * width,
        f"Project:  {data.get('project', '?')}    Topic: {data.get('topic', '?')}    Date: {data.get('date', '?')}",
        "",
        f"Title:    {data.get('title', '?')}",
    ]
    for field in ("context", "decision", "reasoning", "outcome"):
        val = (data.get(field) or "").strip() if isinstance(data.get(field), str) else ""
        if val or field == "outcome":
            label = field.capitalize() + ":"
            label = label.ljust(10)
            shown = val if val else "(none yet)"
            lines.append("")
            lines.append(f"{label}{shown}")
    alts = data.get("alternatives") or []
    if alts:
        lines.append("")
        lines.append("Alternatives:")
        for alt in alts:
            if isinstance(alt, dict):
                lines.append(f"  - {alt.get('option', '?')}: {alt.get('rejected_because', '?')}")
            else:
                lines.append(f"  - {alt}")
    linked = data.get("linked") or {}
    has_links = any(linked.get(k) for k in LINKED_FIELDS_ORDER)
    if has_links:
        lines.append("")
        lines.append("Linked:")
        for k in LINKED_FIELDS_ORDER:
            items = linked.get(k) or []
            if items:
                lines.append(f"  {k}: {', '.join(str(x) for x in items)}")
    return "\n".join(lines).rstrip() + "\n"


def render_list(decisions: list[dict]) -> str:
    if not decisions:
        return "no decisions match\n"
    width = max(70, min(_term_width(), 110))
    title_w = max(10, width - 32)
    lines = [
        f"{'ID':<7} {'PROJECT':<12} {'TOPIC':<14} {'DATE':<11} TITLE",
        "─" * width,
    ]
    for d in decisions:
        lines.append(
            f"{d.get('id', '?'):<7} "
            f"{(d.get('project', '?') or '?')[:12]:<12} "
            f"{(d.get('topic', '?') or '?')[:14]:<14} "
            f"{(d.get('date', '?') or '?')[:11]:<11} "
            f"{_truncate(d.get('title', '') or '', title_w)}"
        )
    return "\n".join(lines) + "\n"


def list_decisions(project_filter: str | None, topic_filter: str | None) -> list[dict]:
    if not DECISIONS_DIR.exists():
        return []
    out: list[dict] = []
    for p in sorted(DECISIONS_DIR.glob("D-*.yaml")):
        try:
            data = yaml.safe_load(p.read_text()) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if project_filter and data.get("project") != project_filter:
            continue
        if topic_filter and data.get("topic") != topic_filter:
            continue
        out.append(data)
    out.sort(key=lambda d: d.get("date", ""), reverse=True)
    return out


# ---------- argparse + main ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="decision",
        description="View, list, create, and update knowledge/decisions/D-NNN.yaml.",
    )
    p.add_argument("id", nargs="?", default=None,
                   help="Decision ID (e.g. D-042) for view/update modes.")
    p.add_argument("--list", action="store_true",
                   help="List all decisions (filtered by --project / --topic).")
    p.add_argument("--new", action="store_true",
                   help="Create a new decision (requires --title and --decision).")
    # Filters / fields
    p.add_argument("--project", help="Project name (for --new or --list filter).")
    p.add_argument("--topic", help=f"Topic (for --new or --list filter). Allowed: {', '.join(ALLOWED_TOPICS)}")
    p.add_argument("--title", help="Title (for --new).")
    p.add_argument("--decision", dest="decide_text",
                   help="Decision body (for --new).")
    p.add_argument("--context", help="Context body (for --new).")
    p.add_argument("--reasoning", help="Reasoning body (for --new).")
    # Update flags
    p.add_argument("--outcome", help="Set the outcome on an existing decision.")
    p.add_argument("--add-pattern", action="append", default=None,
                   help="Append to linked.patterns. Repeat for multiple.")
    p.add_argument("--add-issue", action="append", default=None,
                   help="Append to linked.issues (number or #N).")
    p.add_argument("--add-pr", action="append", default=None,
                   help="Append to linked.prs (number or #N).")
    p.add_argument("--add-related", action="append", default=None,
                   help="Append to linked.related_decisions (D-NNN).")
    p.add_argument("--no-prompt", action="store_true",
                   help="Skip interactive pickers; error on missing inputs.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)

        # --- list mode
        if args.list:
            decisions = list_decisions(args.project, args.topic)
            sys.stdout.write(render_list(decisions))
            return 0

        # --- new mode
        if args.new:
            if not args.title or not args.decide_text:
                raise DecisionError("--new requires --title and --decision")
            decision = create_decision(args)
            path = decision_path(decision["id"])
            write_decision(path, decision)
            update_index_for_new(decision)
            print(f"created {decision['id']}: {decision['title']!r}")
            try:
                rel = "~/" + str(path.relative_to(HOME))
            except ValueError:
                rel = str(path)
            print(f"  wrote {rel}")
            print(f"  updated index.yaml (by_project.{decision['project']}, by_topic.{decision['topic']})")
            print(f"  commit & push manually:")
            print(f"    git -C ~/agents add knowledge/decisions/{decision['id']}.yaml knowledge/decisions/index.yaml \\")
            print(f"      && git commit -m 'docs(decision): {decision['id']} — {decision['title']}' && git push")
            return 0

        # --- view / update modes (require a positional ID)
        if not args.id:
            raise DecisionError("missing decision ID — use 'decision D-NNN' or '--list' or '--new'")
        if not re.match(r"^D-\d+$", args.id):
            raise DecisionError(f"invalid decision id {args.id!r} — expected form D-NNN")
        path = decision_path(args.id)
        data = load_decision(path)

        update_flags = any([
            args.outcome is not None,
            args.add_pattern, args.add_issue, args.add_pr, args.add_related,
        ])

        if not update_flags:
            sys.stdout.write(render_decision(data))
            return 0

        changes = apply_update(data, args)
        if not changes:
            print(f"no changes for {args.id}")
            return 0
        write_decision(path, data)
        # Index update for any newly-added patterns.
        for pat in (args.add_pattern or []):
            update_index_for_pattern(args.id, pat)

        for line in changes:
            print(f"  {line}")
        try:
            rel = "~/" + str(path.relative_to(HOME))
        except ValueError:
            rel = str(path)
        print(f"updated {rel} — commit & push manually:")
        print(f"  git -C ~/agents add knowledge/decisions/{args.id}.yaml knowledge/decisions/index.yaml \\")
        print(f"    && git commit -m 'docs(decision): {args.id} update' && git push")
        return 0

    except (DecisionError, ProjectResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
