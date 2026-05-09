#!/usr/bin/env python3
"""project — view or update a project's Obsidian note.

Reads/writes ``<vault>/Projects/<name>.md`` directly. The frontmatter is the
manually-edited project tracker (focus, status, blockers, next_steps,
open_questions, etc.); the markdown body is the user's freeform area
(Purpose / Stack / Repository / Notes / journal). Pulse never writes to
this file — pulse owns ``_pulse/<project>--<host>.md`` sidecars (Codex F3).

Vault resolution: by default, the vault is looked up from
``~/.claude/dashboard-subscriptions.json``. The first vault whose
``subscribed`` list contains the project name wins; ambiguous matches
error.

This CLI does NOT auto-commit. Project frontmatter changes are infrequent;
user commits manually on whatever cadence suits them.

Subscription model (Path B):
- ``--subscribe`` / ``--unsubscribe``: machine-local; preserves the on-disk
  format (legacy flat or vault-keyed). New ``--subscribe`` calls on a
  vault-keyed file route to the default vault (``AGENTS_DEFAULT_VAULT``
  env var, fallback "JNS-Personal-Vault").
- ``--claim-ssh-host VAULT HOSTNAME`` / ``--release-ssh-host VAULT HOSTNAME``:
  per-machine declaration that this device is the SSH writer for the
  given (vault, remote-host) pair. Implements the single-writer-per-host
  convention from spec §6 (Codex F3 fix).

Alias: ``alias project='python3 ~/agents/project/cli.py'``
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

# Repo root for lib imports (works whether invoked directly or via wrapper)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import obsidian_md  # noqa: E402
from lib import project_resolver  # noqa: E402
from lib.project_resolver import (  # noqa: E402
    ProjectResolutionError,
    add_subscription,
    claim_ssh_host,
    get_host_name,
    project_md_path,
    register_project,
    release_ssh_host,
    remove_subscription,
    resolve_with_picker,
    set_host_name,
)

ALLOWED_STATUS = ("active", "paused", "blocked", "done")

# Frontmatter field order for project notes (spec §6 / §7 destination schema).
# Pulse-managed fields live in per-host sidecars, not here (Codex F3).
PROJECT_FIELDS_ORDER = [
    "project", "host", "client", "kind", "status", "focus", "status_updated",
    "blockers", "next_steps", "open_questions",
    "stack", "repo_path", "repo_remote",
]


class ProjectError(Exception):
    """Single-line user-facing error → stderr + exit 1."""


# ---------- I/O ----------

def load_project(path: Path) -> tuple[dict, str]:
    """Load project note. Returns (frontmatter, body)."""
    try:
        return obsidian_md.load(path)
    except obsidian_md.ObsidianMdError as e:
        raise ProjectError(str(e)) from e


def write_project(path: Path, frontmatter: dict, body: str) -> None:
    """Atomic write of the project note, preserving body content."""
    obsidian_md.write(path, frontmatter, body, field_order=PROJECT_FIELDS_ORDER)


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
    """Remove the first item matching ``query`` (case-insensitive substring or exact).

    Returns the removed string, or raises ProjectError if no match.
    """
    items = _ensure_list(data, key)
    q = query.lower()
    for i, item in enumerate(items):
        if item == query:
            return items.pop(i)
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
    """Apply mutations to the frontmatter dict. Returns human-readable change list.

    Caller bumps ``status_updated`` to today if any change is made.
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
    updated = data.get("status_updated", "?")
    host = data.get("host") or "?"
    lines = [
        f"PROJECT: {name}",
        "─" * width,
        f"Status:    {status}    Host: {host}    Updated: {updated}",
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
        description="View or update a project's Obsidian note.",
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
    p.add_argument("--set-host", dest="set_host", default=None,
                   help="Set the project's host: frontmatter field "
                        "(e.g., jns-mac, vitalai-laptop, jbox06).")
    p.add_argument("--register-host", dest="register_host", default=None, metavar="HOSTNAME",
                   help="Write ~/.claude/host-name with the canonical name for THIS machine. "
                        "Does not require a project name.")
    p.add_argument("--claim-ssh-host", dest="claim_ssh_host", default=None,
                   nargs=2, metavar=("VAULT", "HOSTNAME"),
                   help="Add HOSTNAME to vault.ssh_writes — this device claims to be the "
                        "SSH writer for that remote host (single-writer-per-host convention). "
                        "Does not require a project name.")
    p.add_argument("--release-ssh-host", dest="release_ssh_host", default=None,
                   nargs=2, metavar=("VAULT", "HOSTNAME"),
                   help="Remove HOSTNAME from vault.ssh_writes. Does not require a project name.")
    p.add_argument("--no-prompt", action="store_true", default=False,
                   help="Skip interactive picker; error if name is missing/unknown.")
    return p.parse_args(argv)


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)

        # Project-name-free flags handled first.
        if args.register_host is not None:
            set_host_name(args.register_host)
            print(f"this machine is now registered as host: {args.register_host}")
            print(f"  wrote {Path.home() / '.claude' / 'host-name'}")
            print(f"  current autodetect: {get_host_name()}")
            return 0

        if args.claim_ssh_host is not None:
            vault, host = args.claim_ssh_host
            claim_ssh_host(vault, host)
            print(f"claimed ssh host: {host} → vault {vault}")
            return 0

        if args.release_ssh_host is not None:
            vault, host = args.release_ssh_host
            release_ssh_host(vault, host)
            print(f"released ssh host: {host} from vault {vault}")
            return 0

        # Resolve project name (cwd / explicit / picker / auto-register).
        name = resolve_with_picker(args.name, no_prompt=args.no_prompt)

        path = project_md_path(name)

        write_flags = any([
            args.focus is not None,
            args.status is not None,
            args.next, args.done,
            args.blocker, args.unblock,
            args.question, args.unquestion,
        ])
        host_flag = args.set_host is not None
        sub_flags = args.subscribe or args.unsubscribe

        if not write_flags and not sub_flags and not host_flag:
            data, _ = load_project(path)
            sys.stdout.write(render(data))
            return 0

        applied: list[str] = []

        if write_flags:
            data, body = load_project(path)
            applied = apply_updates(data, args)
            if applied:
                data["status_updated"] = today_iso()
                write_project(path, data, body)

        if host_flag:
            data, body = load_project(path)
            old_host = data.get("host")
            if old_host == args.set_host:
                applied.append(f"host already {args.set_host} for {name} (no-op)")
            else:
                data["host"] = args.set_host
                write_project(path, data, body)
                applied.append(f"host: {old_host or '(unset)'} → {args.set_host}")

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
        print(f"updated {display_path}")
        return 0

    except (ProjectError, ProjectResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
