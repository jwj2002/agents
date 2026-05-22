#!/usr/bin/env python3
"""decision — view, list, create, and update Obsidian decision records.

Reads/writes ``<vault>/Decisions/D-NNN.md`` directly. The frontmatter is the
machine-queryable metadata (id, date, project, topic, title, status, linked,
created_at). The MADR body (Context, Decision, Alternatives, Reasoning,
Outcome, Linked) is the human narrative; the CLI fills in body sections on
``--new`` and replaces ``## Outcome`` content on ``--outcome``.

Decisions span all subscribed vaults — ``next_id()`` and ``--list`` aggregate
across vaults so the global D-NNN counter stays unique.

The ``index.yaml`` file from the YAML era is gone — Dataview queries against
the per-vault ``<vault>/Decisions/`` folder replace it (see Daily.md template's
"Decisions this week" block and Project.md's "Decisions linked" block).

Modes::

  decision D-042                            # read one (across all vaults)
  decision --list [--project X] [--topic Y] # list all / filtered
  decision --new --title "..." --decision "..." [--project X] [--topic Y] \\
           [--context "..."] [--reasoning "..."]
  decision D-042 --outcome "..."            # fill outcome later (body section)
  decision D-042 --add-pattern pat-X        # append to linked.patterns
  decision D-042 --add-pr 147               # append to linked.prs
  decision D-042 --add-issue 148            # append to linked.issues
  decision D-042 --add-related D-091        # append to linked.related_decisions

This CLI does NOT auto-commit; it prints suggested git command after writes.
Consistent with project/cli.py and action/cli.py precedents.

Alias: ``alias decision='python3 ~/agents/decision/cli.py'``
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

# Repo root for lib imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import obsidian_md  # noqa: E402
from lib import project_resolver as pr  # noqa: E402
from lib.project_resolver import (  # noqa: E402
    ProjectResolutionError,
    resolve_with_picker,
)

ALLOWED_TOPICS = (
    "auth", "database", "api", "frontend", "infrastructure",
    "workflow", "testing", "observability",
    "orchestration", "philosophy", "architecture", "export",
)

DECISION_FIELDS_ORDER = [
    "schema_version", "id", "date", "project", "topic", "title", "status",
    "linked", "created_at",
]
LINKED_FIELDS_ORDER = ["patterns", "issues", "prs", "related_decisions"]
ID_RE = re.compile(r"^D-(\d+)$")


class DecisionError(Exception):
    """User-facing error → stderr + exit 1."""


# ---------- vault scan + path resolution ----------

def _all_decision_dirs() -> list[Path]:
    """Decisions/ directories across every subscribed vault."""
    subs = pr.read_subscriptions_dict()
    out: list[Path] = []
    for vault in subs:
        d = pr.vault_path(vault) / "Decisions"
        if d.is_dir():
            out.append(d)
    return out


def find_decision_path(decision_id: str) -> Path:
    """Locate ``<vault>/Decisions/<decision_id>.md`` across vaults.

    Raises DecisionError if not found in any vault.
    """
    for d in _all_decision_dirs():
        candidate = d / f"{decision_id}.md"
        if candidate.is_file():
            return candidate
    raise DecisionError(f"decision {decision_id} not found in any subscribed vault")


def list_existing_ids() -> list[str]:
    """All D-NNN ids across every subscribed vault, sorted ascending."""
    ids: list[str] = []
    for d in _all_decision_dirs():
        for p in d.glob("D-*.md"):
            if ID_RE.match(p.stem):
                ids.append(p.stem)
    return sorted(set(ids))


def next_id() -> str:
    """Return the next ``D-NNN`` id (max + 1, zero-padded to 3 digits minimum)."""
    max_n = 0
    for did in list_existing_ids():
        m = ID_RE.match(did)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"D-{max_n + 1:03d}"


# ---------- I/O ----------

def load_decision(path: Path) -> tuple[dict, str]:
    """Load decision MD. Returns (frontmatter, body)."""
    try:
        fm, body = obsidian_md.load(path)
    except obsidian_md.ObsidianMdError as e:
        raise DecisionError(str(e)) from e
    return _normalize_linked(fm), body


def write_decision(path: Path, frontmatter: dict, body: str) -> None:
    fm = _normalize_linked(frontmatter)
    obsidian_md.write(path, fm, body, field_order=DECISION_FIELDS_ORDER)


def _normalize_linked(fm: dict) -> dict:
    """Ensure ``linked`` is a dict with the four canonical keys (lists)."""
    linked = fm.get("linked")
    if not isinstance(linked, dict):
        linked = {}
    for k in LINKED_FIELDS_ORDER:
        v = linked.get(k)
        linked[k] = list(v) if isinstance(v, list) else []
    fm["linked"] = {k: linked[k] for k in LINKED_FIELDS_ORDER}
    return fm


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


def _starter_or(text: str | None, fallback: str) -> str:
    return text.rstrip() if text else fallback


def render_new_body(
    decision_id: str, title: str,
    context: str | None, decide_text: str,
    reasoning: str | None,
) -> str:
    """Render the MADR body for a new decision."""
    return (
        f"# {decision_id} — {title}\n\n"
        "## Context\n"
        f"{_starter_or(context, '*(what is the problem; what constraints exist)*')}\n\n"
        "## Decision\n"
        f"{decide_text.rstrip()}\n\n"
        "## Alternatives considered\n"
        "- **Option A**: \n"
        "  - Rejected because: \n"
        "- **Option B**: \n"
        "  - Rejected because: \n\n"
        "## Reasoning\n"
        f"{_starter_or(reasoning, '*(why this is the right call given context + alternatives)*')}\n\n"
        "## Outcome\n"
        "*(filled in later when shipped — what actually happened)*\n\n"
        "## Linked\n"
        "- Patterns: \n"
        "- PRs: \n"
        "- Issues: \n"
        "- Related decisions: \n"
    )


def create_decision(args: argparse.Namespace) -> tuple[dict, str, Path]:
    """Build (frontmatter, body, target_path) for a new decision."""
    project = resolve_with_picker(args.project, no_prompt=args.no_prompt)
    vault = pr.resolve_vault_for_project(project)
    topic = args.topic or pick_topic(args.no_prompt)
    today = today_iso()
    decision_id = next_id()
    fm = {
        "schema_version": 1,
        "id": decision_id,
        "date": today,
        "project": project,
        "topic": topic,
        "title": args.title,
        "status": "proposed",
        "linked": {k: [] for k in LINKED_FIELDS_ORDER},
        "created_at": today,
    }
    body = render_new_body(
        decision_id, args.title,
        args.context, args.decide_text, args.reasoning,
    )
    return fm, body, pr.decision_md_path(decision_id, vault)


# ---------- update ----------

def apply_update(fm: dict, body: str, args: argparse.Namespace) -> tuple[str, list[str]]:
    """Apply mutations. Returns (new_body, change_descriptions)."""
    changes: list[str] = []
    linked = fm["linked"]

    if args.outcome is not None:
        try:
            current = obsidian_md.get_section(body, "Outcome")
        except obsidian_md.ObsidianMdError:
            current = None
        if current != args.outcome.rstrip():
            try:
                body = obsidian_md.replace_section(body, "Outcome", args.outcome)
            except obsidian_md.ObsidianMdError as e:
                raise DecisionError(str(e)) from e
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

    for prn in (args.add_pr or []):
        normalized = prn if prn.startswith("#") else f"#{prn}"
        if normalized not in linked["prs"]:
            linked["prs"].append(normalized)
            changes.append(f"+linked.pr: {normalized}")

    for rd in (args.add_related or []):
        if rd not in linked["related_decisions"]:
            linked["related_decisions"].append(rd)
            changes.append(f"+linked.related: {rd}")

    return body, changes


# ---------- rendering ----------

def _term_width() -> int:
    return shutil.get_terminal_size((90, 24)).columns


def _truncate(s: str, w: int) -> str:
    return s if len(s) <= w else s[: w - 1] + "…"


def render_decision(fm: dict, body: str) -> str:
    width = max(70, min(_term_width(), 110))
    lines = [
        f"DECISION {fm.get('id', '?')}",
        "─" * width,
        f"Project:  {fm.get('project', '?')}    "
        f"Topic: {fm.get('topic', '?')}    Date: {fm.get('date', '?')}",
        "",
        f"Title:    {fm.get('title', '?')}",
    ]
    for section in ("Context", "Decision", "Reasoning", "Outcome"):
        if obsidian_md.has_section(body, section):
            content = obsidian_md.get_section(body, section)
            label = (section + ":").ljust(10)
            shown = content.strip() or "(none yet)"
            lines.append("")
            lines.append(f"{label}{shown}")
    linked = fm.get("linked") or {}
    if any(linked.get(k) for k in LINKED_FIELDS_ORDER):
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
    """Aggregate decisions across all subscribed vaults, newest date first."""
    out: list[dict] = []
    for d in _all_decision_dirs():
        for path in sorted(d.glob("D-*.md")):
            try:
                fm, _ = obsidian_md.load(path)
            except obsidian_md.ObsidianMdError:
                continue
            if project_filter and fm.get("project") != project_filter:
                continue
            if topic_filter and fm.get("topic") != topic_filter:
                continue
            out.append(fm)
    out.sort(key=lambda d: d.get("date", ""), reverse=True)
    return out


# ---------- argparse + main ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="decision",
        description="View, list, create, and update Obsidian decision records.",
    )
    p.add_argument("id", nargs="?", default=None,
                   help="Decision ID (e.g. D-042) for view/update modes.")
    p.add_argument("--list", action="store_true",
                   help="List all decisions (filtered by --project / --topic).")
    p.add_argument("--new", action="store_true",
                   help="Create a new decision (requires --title and --decision).")
    p.add_argument("--project", help="Project name (for --new or --list filter).")
    p.add_argument("--topic",
                   help=f"Topic (for --new or --list filter). Allowed: {', '.join(ALLOWED_TOPICS)}")
    p.add_argument("--title", help="Title (for --new).")
    p.add_argument("--decision", dest="decide_text",
                   help="Decision body (for --new).")
    p.add_argument("--context", help="Context body (for --new).")
    p.add_argument("--reasoning", help="Reasoning body (for --new).")
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

        if args.list:
            decisions = list_decisions(args.project, args.topic)
            sys.stdout.write(render_list(decisions))
            return 0

        if args.new:
            if not args.title or not args.decide_text:
                raise DecisionError("--new requires --title and --decision")
            fm, body, path = create_decision(args)
            write_decision(path, fm, body)
            print(f"created {fm['id']}: {fm['title']!r}")
            try:
                rel = "~/" + str(path.relative_to(Path.home()))
            except ValueError:
                rel = str(path)
            print(f"  wrote {rel}")
            return 0

        if not args.id:
            raise DecisionError(
                "missing decision ID — use 'decision D-NNN' or '--list' or '--new'"
            )
        if not ID_RE.match(args.id):
            raise DecisionError(f"invalid decision id {args.id!r} — expected form D-NNN")

        path = find_decision_path(args.id)
        fm, body = load_decision(path)

        update_flags = any([
            args.outcome is not None,
            args.add_pattern, args.add_issue, args.add_pr, args.add_related,
        ])

        if not update_flags:
            sys.stdout.write(render_decision(fm, body))
            return 0

        body, changes = apply_update(fm, body, args)
        if not changes:
            print(f"no changes for {args.id}")
            return 0
        write_decision(path, fm, body)
        for line in changes:
            print(f"  {line}")
        try:
            rel = "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            rel = str(path)
        print(f"updated {rel}")
        return 0

    except (DecisionError, ProjectResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
