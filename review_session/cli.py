#!/usr/bin/env python3
"""review-session — review pending session activity and apply focus updates.

Reads ~/.claude/pending_focus_reviews.json (written by the session-end hook).
For each project with new commits, renders the commit list + current focus and
asks the user to apply / skip / quit. Applies focus updates by shelling out
to the `project` CLI's --focus path (delegation pattern from #141).

Phase 6B P-4 port. Replaces the /review-session skill's calls to
mcp__knowledge__update_project_context.

Behavior change vs. the original skill: the CLI does NOT auto-propose a focus
statement via LLM synthesis. The user types the new focus based on the
rendered commit list. Consistent with action/dashboard/project pattern —
CLIs don't do LLM. If LLM-drafted defaults become useful again, they belong
in the SKILL.md wrapper, not here.

Alias: `alias review-session='python3 ~/agents/review_session/cli.py'`
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Repo root for lib imports (works whether invoked directly or via wrapper).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import project_resolver  # noqa: E402
from lib.project_resolver import project_yaml_path  # noqa: E402

HOME = Path.home()
PENDING_REVIEWS_PATH = HOME / ".claude" / "pending_focus_reviews.json"
PROJECT_CLI_PATH = Path(__file__).resolve().parent.parent / "project" / "cli.py"


class ReviewError(Exception):
    """Single-line user-facing error → stderr + exit 1."""


# ---------- pending file I/O ----------

def load_pending() -> dict:
    """Return parsed pending entries; {} if file missing.

    Raises ReviewError on unparseable or wrong-shaped content.
    """
    if not PENDING_REVIEWS_PATH.exists():
        return {}
    try:
        data = json.loads(PENDING_REVIEWS_PATH.read_text())
    except json.JSONDecodeError as e:
        raise ReviewError(f"could not parse {PENDING_REVIEWS_PATH}: {e}")
    if not isinstance(data, dict):
        raise ReviewError(
            f"{PENDING_REVIEWS_PATH}: top-level must be a JSON object, got {type(data).__name__}"
        )
    return data


def write_pending(data: dict) -> None:
    """Atomic write; delete the file if data is empty."""
    if not data:
        if PENDING_REVIEWS_PATH.exists():
            PENDING_REVIEWS_PATH.unlink()
        return
    PENDING_REVIEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=PENDING_REVIEWS_PATH.name + ".",
        suffix=".tmp",
        dir=str(PENDING_REVIEWS_PATH.parent),
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, PENDING_REVIEWS_PATH)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


# ---------- rendering ----------

def render_summary(data: dict) -> str:
    """One-line-per-project summary used by --list."""
    if not data:
        return "no pending session reviews. You're all caught up.\n"
    plural = "s" if len(data) != 1 else ""
    lines = [f"{len(data)} project{plural} pending review:"]
    for name, entry in data.items():
        if not isinstance(entry, dict):
            lines.append(f"  - {name}: (malformed entry)")
            continue
        commits = entry.get("commits") or []
        focus = entry.get("current_focus") or ""
        c_plural = "s" if len(commits) != 1 else ""
        lines.append(
            f"  - {name}: {len(commits)} commit{c_plural}"
            f" — current focus: {focus or '(none)'}"
        )
    return "\n".join(lines) + "\n"


def render_project(name: str, entry: dict, max_commits: int = 5) -> str:
    commits = entry.get("commits") or []
    current_focus = entry.get("current_focus") or "(none)"
    plural = "s" if len(commits) != 1 else ""
    lines = [
        f"📝 {name} — {len(commits)} commit{plural} this session",
        "",
        f"  Current focus: {current_focus}",
        "",
        "  Commits:",
    ]
    for c in commits[:max_commits]:
        if isinstance(c, dict):
            msg = str(c.get("message", "?"))
        else:
            msg = str(c)
        subject = msg.split("\n", 1)[0]
        lines.append(f"    - {subject}")
    if len(commits) > max_commits:
        lines.append(f"    (+{len(commits) - max_commits} more)")
    lines.append("")
    return "\n".join(lines)


# ---------- apply step (delegation to project CLI) ----------

def apply_focus(name: str, new_focus: str) -> int:
    """Shell out to the project CLI to write the focus. Returns its exit code."""
    cmd = [
        sys.executable,
        str(PROJECT_CLI_PATH),
        name,
        "--focus", new_focus,
        "--no-prompt",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


# ---------- interactive flow ----------

def prompt(text: str) -> str:
    """input() wrapper so tests can monkeypatch a single seam."""
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def review_one(name: str, entry: dict, *, no_prompt: bool) -> str:
    """Drive the per-project flow.

    Returns one of: 'applied', 'skipped', 'quit'.
    """
    sys.stdout.write(render_project(name, entry))

    if not project_yaml_path(name).exists():
        print(f"  warning: knowledge/projects/{name}.yaml not found — skipping")
        return "skipped"

    if no_prompt:
        print("  --no-prompt set; skipping (would need input to apply)")
        return "skipped"

    print("  Actions: [a] apply  [s] skip  [q] quit")
    for _ in range(3):
        choice = prompt("  Choice [a/s/q]: ").lower()
        if not choice:
            print("  cancelled")
            return "quit"
        if choice in ("a", "apply", "y", "yes"):
            new_focus = prompt("  New focus (≤80 chars recommended): ")
            if not new_focus:
                print("  empty focus — skipping")
                return "skipped"
            rc = apply_focus(name, new_focus)
            if rc != 0:
                print(
                    f"  apply failed (project CLI exit {rc}); leaving entry pending",
                    file=sys.stderr,
                )
                return "quit"
            return "applied"
        if choice in ("s", "skip", "n", "no"):
            return "skipped"
        if choice in ("q", "quit"):
            return "quit"
        print("    invalid choice — enter a, s, or q")
    print("  too many invalid choices — quitting")
    return "quit"


# ---------- argparse + main ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="review-session",
        description="Review pending session activity and apply focus updates.",
    )
    p.add_argument(
        "project", nargs="?", default=None,
        help="Only review this project (default: iterate all pending).",
    )
    p.add_argument(
        "--list", action="store_true",
        help="Print pending summary and exit; no prompts.",
    )
    p.add_argument(
        "--no-prompt", action="store_true",
        help="Non-interactive; skips any project that needs input.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)
        data = load_pending()

        if args.list:
            sys.stdout.write(render_summary(data))
            return 0

        if not data:
            print("no pending session reviews. You're all caught up.")
            return 0

        if args.project:
            if args.project not in data:
                pending = ", ".join(data.keys()) or "none"
                raise ReviewError(
                    f'no pending review for project "{args.project}" '
                    f"(pending: {pending})"
                )
            project_names = [args.project]
        else:
            project_names = list(data.keys())

        applied = 0
        skipped = 0
        for name in project_names:
            entry = data.get(name)
            if not isinstance(entry, dict):
                print(f"  warning: malformed entry for {name}; removing")
                data.pop(name, None)
                write_pending(data)
                continue
            outcome = review_one(name, entry, no_prompt=args.no_prompt)
            if outcome == "quit":
                break
            data.pop(name, None)
            write_pending(data)
            if outcome == "applied":
                applied += 1
            else:
                skipped += 1
            print()

        remaining = len(load_pending())
        print(
            f"Done — {applied} applied, {skipped} skipped, "
            f"{remaining} remaining."
        )
        return 0

    except ReviewError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
