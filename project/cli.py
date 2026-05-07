#!/usr/bin/env python3
"""project — view or update a project's tracker YAML.

Reads/writes ~/agents/knowledge/projects/<name>.yaml directly. Replaces
the /project skill's calls to mcp__knowledge__get_project_context and
mcp__knowledge__update_project_context (Phase 6B port; see
specs/phase6b-mcp-audit.md).

This CLI does NOT auto-commit. Project YAML changes are less frequent
than ACTIONS.md mutations; user commits manually on whatever cadence
suits them. (The action CLI's auto-commit / multi-device-safety design
from #121 can be extracted into lib/git_ops.py in a follow-up if this
becomes a real pain point.)

Update paths owned elsewhere:
- decisions journal:       knowledge/decisions/*.yaml (hand-edit)
- subscriptions:           --subscribe / --unsubscribe (machine-local;
                           writes ~/.claude/dashboard-subscriptions.json)

Alias: `alias project='python3 ~/agents/project/cli.py'`
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

# Repo root for lib imports (works whether invoked directly or via wrapper)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import project_resolver  # noqa: E402
from lib.project_resolver import (  # noqa: E402
    ProjectResolutionError,
    add_subscription,
    project_yaml_path,
    register_project,
    remove_subscription,
    resolve_with_picker,
)

ALLOWED_STATUS = ("active", "paused", "blocked", "done")
PROJECT_FIELDS_ORDER = [
    "schema_version",
    "project", "status", "focus", "next_steps", "blockers",
    "open_questions", "specs", "dependencies", "updated_at", "updated_by",
]
DEFAULT_OWNER = "jason"


class ProjectError(Exception):
    """Single-line user-facing error → stderr + exit 1."""


# ---------- YAML I/O ----------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ProjectError(f"project YAML not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ProjectError(f"{path}: top-level YAML must be a mapping, got {type(data).__name__}")
    return data


def write_yaml(path: Path, data: dict) -> None:
    """Atomic write of project YAML with stable field order."""
    ordered: dict = {}
    for k in PROJECT_FIELDS_ORDER:
        if k in data:
            ordered[k] = data[k]
    for k, v in data.items():
        if k not in ordered:
            ordered[k] = v
    text = yaml.safe_dump(
        ordered, sort_keys=False, default_flow_style=False,
        allow_unicode=True, width=80,
    )
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


# ---------- mutations ----------

def today_iso() -> str:
    return date.today().isoformat()


def _ensure_list(data: dict, key: str) -> list:
    val = data.get(key)
    if not isinstance(val, list):
        val = []
        data[key] = val
    return val


def add_to_list(data: dict, key: str, item: str) -> None:
    items = _ensure_list(data, key)
    if item not in items:
        items.append(item)


def remove_from_list_by_match(data: dict, key: str, query: str) -> str:
    """Remove the first item matching `query` (case-insensitive substring or exact).

    Returns the removed string, or raises ProjectError if no match.
    """
    items = _ensure_list(data, key)
    q = query.lower()
    # Prefer exact match if present.
    for i, item in enumerate(items):
        if item == query:
            return items.pop(i)
    # Fall back to substring match.
    matches = [i for i, item in enumerate(items) if q in str(item).lower()]
    if not matches:
        raise ProjectError(f'no item matching "{query}" in {key}')
    if len(matches) > 1:
        listing = "\n".join(f"  - {items[i]}" for i in matches)
        raise ProjectError(
            f'multiple items match "{query}" in {key}; use a more specific string:\n{listing}'
        )
    return items.pop(matches[0])


def apply_updates(data: dict, args: argparse.Namespace) -> list[str]:
    """Apply mutations from args. Returns a list of human-readable change descriptions.

    Caller bumps updated_at + updated_by once at the end if the list is non-empty.
    """
    changes: list[str] = []

    if args.focus is not None:
        old = data.get("focus", "") or ""
        data["focus"] = args.focus
        if old != args.focus:
            changes.append(f"focus → {args.focus!r}")

    if args.status is not None:
        if args.status not in ALLOWED_STATUS:
            raise ProjectError(
                f'invalid status "{args.status}" — must be one of {", ".join(ALLOWED_STATUS)}'
            )
        old = data.get("status", "")
        data["status"] = args.status
        if old != args.status:
            changes.append(f"status: {old} → {args.status}")

    for item in (args.next or []):
        add_to_list(data, "next_steps", item)
        changes.append(f"+next_step: {item!r}")
    for item in (args.done or []):
        removed = remove_from_list_by_match(data, "next_steps", item)
        changes.append(f"-next_step: {removed!r}")

    for item in (args.blocker or []):
        add_to_list(data, "blockers", item)
        changes.append(f"+blocker: {item!r}")
    for item in (args.unblock or []):
        removed = remove_from_list_by_match(data, "blockers", item)
        changes.append(f"-blocker: {removed!r}")

    for item in (args.question or []):
        add_to_list(data, "open_questions", item)
        changes.append(f"+question: {item!r}")
    for item in (args.unquestion or []):
        removed = remove_from_list_by_match(data, "open_questions", item)
        changes.append(f"-question: {removed!r}")

    return changes


# ---------- rendering ----------

def _term_width() -> int:
    return shutil.get_terminal_size((90, 24)).columns


def _truncate(s: str, w: int) -> str:
    return s if len(s) <= w else s[: w - 1] + "…"


def render(data: dict) -> str:
    width = max(70, min(_term_width(), 110))
    name = data.get("project", "?")
    status = (data.get("status") or "?").upper()
    updated = data.get("updated_at", "?")
    lines = [
        f"PROJECT: {name}",
        "─" * width,
        f"Status:    {status}    Updated: {updated}",
    ]
    focus = (data.get("focus") or "").strip()
    if focus:
        lines.append(_truncate(f"Focus:     {focus}", width))

    blockers = data.get("blockers") or []
    if blockers:
        lines.append("Blockers:")
        for b in blockers:
            lines.append(_truncate(f"  ⛔ {b}", width))

    questions = data.get("open_questions") or []
    if questions:
        lines.append("Open Questions:")
        for q in questions:
            lines.append(_truncate(f"  ? {q}", width))

    steps = data.get("next_steps") or []
    if steps:
        lines.append("Next Steps:")
        for i, s in enumerate(steps, 1):
            lines.append(_truncate(f"  {i}. {s}", width))

    return "\n".join(lines).rstrip() + "\n"


# ---------- argparse ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="project",
        description="View or update a project's tracker YAML.",
    )
    p.add_argument("name", nargs="?", default=None,
                   help="Project name (default: cwd-detect)")
    p.add_argument("--focus", help="Set the focus line")
    p.add_argument("--status", help=f"Set status — one of {', '.join(ALLOWED_STATUS)}")
    p.add_argument("--next", action="append", default=None,
                   help="Append to next_steps. Repeat for multiple.")
    p.add_argument("--done", action="append", default=None,
                   help="Remove an item from next_steps by exact-or-substring match.")
    p.add_argument("--blocker", action="append", default=None,
                   help="Append to blockers.")
    p.add_argument("--unblock", action="append", default=None,
                   help="Remove a blocker by match.")
    p.add_argument("--question", action="append", default=None,
                   help="Append to open_questions.")
    p.add_argument("--unquestion", action="append", default=None,
                   help="Remove an open question by match.")
    p.add_argument("--subscribe", action="store_true",
                   help="Add to ~/.claude/dashboard-subscriptions.json (this machine).")
    p.add_argument("--unsubscribe", action="store_true",
                   help="Remove from ~/.claude/dashboard-subscriptions.json.")
    p.add_argument("--no-prompt", action="store_true", default=False,
                   help="Skip interactive picker; error if name is missing/unknown.")
    return p.parse_args(argv)


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)

        # Resolve project name (cwd / explicit / picker / auto-register).
        name = resolve_with_picker(args.name, no_prompt=args.no_prompt)

        path = project_yaml_path(name)

        # Determine if any mutation flags were passed.
        write_flags = any([
            args.focus is not None,
            args.status is not None,
            args.next, args.done,
            args.blocker, args.unblock,
            args.question, args.unquestion,
        ])
        sub_flags = args.subscribe or args.unsubscribe

        if not write_flags and not sub_flags:
            # Read mode.
            data = load_yaml(path)
            sys.stdout.write(render(data))
            return 0

        # Write mode — apply YAML mutations first (if any).
        applied: list[str] = []
        if write_flags:
            data = load_yaml(path)
            applied = apply_updates(data, args)
            if applied:
                data["updated_at"] = today_iso()
                data["updated_by"] = data.get("updated_by") or DEFAULT_OWNER
                write_yaml(path, data)

        # Subscription flags (machine-local; never touch the YAML).
        if args.subscribe:
            add_subscription(name)
            applied.append(f"subscribed to {name} on this machine")
        if args.unsubscribe:
            remove_subscription(name)
            applied.append(f"unsubscribed from {name} on this machine")

        if not applied:
            print(f"no changes for {name}")
            return 0

        for line in applied:
            print(f"  {line}")
        try:
            display_path = "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            display_path = str(path)
        print(f"updated {display_path} — commit & push manually:")
        print(f"  git -C ~/agents add knowledge/projects/{name}.yaml && git commit -m 'chore(project): update {name}' && git push")
        return 0

    except (ProjectError, ProjectResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
