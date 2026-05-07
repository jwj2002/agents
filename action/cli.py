#!/usr/bin/env python3
"""action — CRUD for ACTIONS.md.

The Python implementation. The /action Claude skill just shells out here.
For shell use directly: alias action='python3 ~/agents/action/cli.py'.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# Add the agents repo root to sys.path so `lib.actions_md` resolves whether
# this file is invoked as `python3 ~/agents/action/cli.py` or via the
# `bin/action` symlink.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.actions_md import (  # noqa: E402
    ALLOWED_STATUS,
    CLOSED_COLS,
    CLOSED_COLS_V1,
    FileModel,
    ID_RE,
    MarkdownParseError,
    OPEN_COLS,
    OPEN_COLS_V1,
    TERMINAL_STATUS,
    bump_next_id,
    escape_pipes,
    insert_closed_row,
    insert_open_row,
    is_table_separator,
    parse_file,
    parse_files_cell,
    parse_next_id_from_data,
    remove_row,
    render_files_cell,
    render_row,
    replace_row,
    split_row,
)

HOME = Path.home()
KNOWLEDGE_PROJECTS_DIR = HOME / "agents" / "knowledge" / "projects"
SUBSCRIPTIONS_PATH = Path.home() / ".claude" / "dashboard-subscriptions.json"
GIT_OK            = "ok"
GIT_NETWORK_ERROR = "network_error"
GIT_CONFLICT      = "conflict"
GIT_NOT_A_REPO    = "not_a_git_repo"
GIT_PUSH_REJECTED = "push_rejected"

HELP_TEXT = """\
/action — manage entries in a project's ACTIONS.md

Read:
  action --help                       Show this help
  action --list                       List open actions (wide table with metadata)
  action --list --short               Compact format: ID Owner Status Action
  action --list --no-trunc            Don't truncate the Action column
  action --list --status <s>          Filter by status (open|wip|blocked|done|cancelled|closed)
  action --list --owner <name>        Filter by owner (case-insensitive)
  action --list --closed              Show Recently Closed table
  action --list --all                 Show open + recently closed
  action A-NNN                        Show one action in detail

Update:
  action A-NNN --status <s>           Transition status; done/cancelled auto-close the row
  action A-NNN --note "..."           Append a dated note (preserves prior notes)
  action A-NNN --owner <name>         Reassign owner
  action A-NNN --reopen               Move closed row back to Open with status=open

Attachments (used by /email-digest to attach files to outgoing mail):
  action A-NNN --attach <path>        Attach a file. Path may be Linux absolute,
                                      ~/..., or \\\\wsl.localhost\\<distro>\\... — all
                                      normalized to a Linux absolute path.
                                      Repeat --attach to add multiple files.
  action A-NNN --unattach <name>      Remove attachment by basename or full path

Create:
  action --new "..."                  Add one new action (defaults: owner=Jason, status=open)
  action --new "x" "y" "z"            Add multiple actions in one batch
  action --new < file.txt             Read action texts from stdin (one per line)
  action --new -e                     Open $EDITOR with a template; one row per non-comment line
  action --new -i                     Interactive prompt loop until a blank line
                                      Optional: [--owner <name>] [--status <s>]
                                                [--note "..."] [--src "..."]
                                                [--attach <path>]
  Auto-creates ACTIONS.md from template if missing in the resolved project.

Project resolution:
  --project, -p <name>                 Override; otherwise inferred from cwd
                                       (~/agents → agents, ~/projects/X → X)
  --no-prompt                          Skip interactive picker; error instead
                                       (set automatically by non-TTY callers)
  --no-commit                          Skip all git ops (pull + push); write file locally
  --strict                             Abort if git pull fails (network down); default
                                       is warn-and-continue
Picker: when project is unresolved or unknown and stdin is a TTY, a numbered
list of known projects is shown. Ctrl-C, EOF, or blank input aborts.

Status values: open · wip · blocked · done · cancelled
"""


class ActionError(Exception):
    """Single-line error to stderr + non-zero exit."""


# ---------- helpers ----------

def today() -> str:
    return date.today().isoformat()


# Table parsing/rendering, file model, mutations, and schema constants live
# in lib/actions_md.py and are imported above. The remaining helpers below
# are action-specific (notes, attachments, project resolution, git, etc.).


def append_note(existing: str, text: str) -> str:
    """Append ' | YYYY-MM-DD: <text>' (escaped) preserving prior notes."""
    fragment = f"{today()}: {escape_pipes(text)}"
    existing = existing.strip()
    return f"{existing} | {fragment}" if existing else fragment


def normalize_attachment_path(raw: str) -> Path:
    """Translate WSL UNC, ~/..., or Linux absolute → resolved Path that exists.

    Accepted inputs (whitespace and surrounding quotes are stripped):
      \\\\wsl.localhost\\Ubuntu-24.04\\home\\jjob\\...    (WSL UNC, modern)
      \\\\wsl$\\Ubuntu\\home\\jjob\\...                   (WSL UNC, legacy)
      ~/projects/...                                       (home-relative)
      /home/jjob/projects/...                              (Linux absolute)
    """
    s = raw.strip().strip('"').strip("'").replace("\\", "/")
    lowered = s.lower()
    for prefix in ("//wsl.localhost/", "//wsl$/"):
        if lowered.startswith(prefix):
            tail = s[len(prefix):]
            parts = tail.split("/", 1)
            s = "/" + (parts[1] if len(parts) > 1 else "")
            break
    if s.startswith("~"):
        s = str(Path(s).expanduser())
    if not s.startswith("/"):
        raise ActionError(
            f'cannot resolve attachment path "{raw}" — pass a Linux absolute, '
            r"~/..., or \\wsl.localhost\<distro>\... path"
        )
    p = Path(s).resolve()
    if not p.is_file():
        raise ActionError(f"attachment file not found: {p}")
    return p


# NOTE: parse_files_cell, render_files_cell, _row_cells, FileModel,
# parse_file, parse_next_id_from_data, and the row mutators live in
# lib/actions_md.py — imported at the top of this file.


# ---------- project resolution ----------

def resolve_project(args: argparse.Namespace) -> str:
    if args.project:
        return args.project
    cwd = Path.cwd()
    agents_dir = HOME / "agents"
    projects_dir = HOME / "projects"
    if cwd == agents_dir or agents_dir in cwd.parents:
        return "agents"
    if projects_dir in cwd.parents:
        return cwd.relative_to(projects_dir).parts[0]
    raise ActionError(
        "no project resolved — pass --project <name> or run from inside the project directory"
    )


def list_known_projects() -> list[str]:
    """Return sorted list of project names, filtered by this machine's subscriptions.

    Falls back to all registered yamls if subscriptions file is missing or empty.
    """
    all_registered = sorted(p.stem for p in KNOWLEDGE_PROJECTS_DIR.glob("*.yaml"))
    subs = read_subscriptions()
    if not subs:
        return all_registered
    filtered = [p for p in all_registered if p in subs]
    return filtered if filtered else all_registered


def _interactive_pick(candidates: list[str], header: str) -> str:
    """Print numbered menu, prompt for 1-based selection.

    Reprompts up to 3 times on out-of-range or non-numeric input.
    Raises ActionError on Ctrl-C, EOF, blank input, or exhausted retries.
    """
    print(header)
    for i, name in enumerate(candidates, 1):
        print(f"  {i}) {name}")
    for attempt in range(3):
        try:
            raw = input(f"Enter number (1-{len(candidates)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ActionError("project selection cancelled")
        if not raw:
            raise ActionError("project selection cancelled")
        try:
            choice = int(raw)
        except ValueError:
            if attempt < 2:
                print(f"  invalid input — enter a number between 1 and {len(candidates)}")
                continue
            raise ActionError("too many invalid inputs — project selection aborted")
        if 1 <= choice <= len(candidates):
            return candidates[choice - 1]
        if attempt < 2:
            print(f"  out of range — enter a number between 1 and {len(candidates)}")
        else:
            raise ActionError("too many invalid inputs — project selection aborted")
    raise ActionError("too many invalid inputs — project selection aborted")


def resolve_project_with_picker(args: argparse.Namespace) -> str:
    """Wrap resolve_project(); apply validation + interactive picker where appropriate.

    Validation order:
      1. cwd inference (via resolve_project) — if resolved, return immediately.
      2. --project <name>: if supplied AND in known list, return it.
      3. --project <name>: if supplied BUT NOT in known list, picker with
         header 'unknown project "<name>". Pick one:'.
      4. No project resolved: picker with header 'no project resolved. Pick one:'.
      5. Picker only fires when sys.stdin.isatty() AND NOT args.no_prompt.
         Otherwise raises ActionError with existing message.
    """
    # If --project not supplied, try cwd inference first.
    if not args.project:
        try:
            return resolve_project(args)
        except ActionError:
            pass
        # cwd inference failed — offer picker or hard error
        if sys.stdin.isatty() and not args.no_prompt:
            candidates = list_known_projects()
            return _interactive_pick(candidates, "no project resolved. Pick one:")
        raise ActionError(
            "no project resolved — pass --project <name> or run from inside the project directory"
        )

    # --project was supplied — validate against known list
    known = list_known_projects()
    if args.project in known:
        return args.project

    # Unknown project name — check if disk dir exists → auto-register
    if project_dir_exists(args.project):
        register_project(args.project)
        print(f'registered new project "{args.project}" on this machine')
        return args.project

    # No disk dir — picker or error (Rule 3)
    if sys.stdin.isatty() and not args.no_prompt:
        return _interactive_pick(known, f'unknown project "{args.project}". Pick one:')
    subs = read_subscriptions()
    subscribed_str = ", ".join(subs) if subs else "(none)"
    raise ActionError(
        f'unknown project "{args.project}"\n'
        f"  - not registered (knowledge/projects/{args.project}.yaml missing)\n"
        f"  - no repo at ~/projects/{args.project}/\n"
        f"  To add: clone the repo to ~/projects/{args.project}, "
        f'or register manually.\n'
        f"  Subscribed on this machine: {subscribed_str}"
    )


def project_path(name: str) -> Path:
    if name == "agents":
        return HOME / "agents" / "ACTIONS.md"
    return HOME / "projects" / name / "ACTIONS.md"


def project_dir_exists(name: str) -> bool:
    """Return True if a local repo directory exists for this project name."""
    if name == "agents":
        return (HOME / "agents").is_dir()
    return (HOME / "projects" / name).is_dir()


def read_subscriptions() -> list[str]:
    """Read subscribed project names from dashboard-subscriptions.json.

    Returns [] on missing file, malformed JSON, or absent/empty subscribed key.
    """
    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text())
        subs = data.get("subscribed", [])
        return [s for s in subs if isinstance(s, str)]
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return []


def add_subscription(name: str) -> None:
    """Append name to dashboard-subscriptions.json, creating the file if absent."""
    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    subs: list[str] = data.get("subscribed", [])
    if name not in subs:
        subs.append(name)
    data["subscribed"] = subs
    SUBSCRIPTIONS_PATH.write_text(json.dumps(data, indent=2) + "\n")


def register_project(name: str) -> Path:
    """Write a default yaml to knowledge/projects/<name>.yaml and subscribe this machine.

    Raises FileExistsError if yaml already exists (prevents double-registration).
    Returns the path to the created yaml.
    """
    yaml_path = KNOWLEDGE_PROJECTS_DIR / f"{name}.yaml"
    if yaml_path.exists():
        raise FileExistsError(f"project yaml already exists: {yaml_path}")
    today_str = date.today().isoformat()
    content = (
        f"project: {name}\n"
        f"status: active\n"
        f'focus: ""\n'
        f"next_steps: []\n"
        f"blockers: []\n"
        f"open_questions: []\n"
        f"specs: []\n"
        f"dependencies: []\n"
        f'updated_at: "{today_str}"\n'
        f"updated_by: jason\n"
    )
    yaml_path.write_text(content)
    add_subscription(name)
    return yaml_path


# ---------- commands ----------

DEFAULT_OWNER = "Jason"


def _actions_template(project_name: str) -> str:
    """Initial ACTIONS.md content (v2 schema with Files column)."""
    return (
        f"# Actions — {project_name}\n"
        "\n"
        "Open and recently closed actions for this project.\n"
        "\n"
        "**How to use**\n"
        "- Add: append a row, next ID, status=open, fill owner/opened/source\n"
        "- Update: edit in place (status, notes, closed date)\n"
        "- Closed >30 days: move to Archive\n"
        "- Refer as `A-NNN` in commits, PRs, chat, other docs\n"
        "\n"
        "**Status:** `open` · `wip` · `blocked` · `done` · `cancelled`\n"
        "\n"
        "## Sources\n"
        "\n"
        "_(none yet)_\n"
        "\n"
        "## Open\n"
        "\n"
        "| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |\n"
        "|----|-------|--------|-------|--------|--------|-----|-------|-------|\n"
        "\n"
        "## Recently Closed\n"
        "\n"
        "| ID | Issue | Action | Owner | Closed | Files | Notes |\n"
        "|----|-------|--------|-------|--------|-------|-------|\n"
        "\n"
        "## Archive\n"
        "\n"
        "_(none yet)_\n"
        "\n"
        "---\n"
        "Next ID: **A-001**\n"
    )


def _collect_from_editor() -> list[str]:
    """Open $EDITOR with a template; return non-comment, non-empty lines."""
    if not sys.stdin.isatty():
        raise ActionError("--editor requires a TTY (cannot launch $EDITOR from a pipe)")
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"
    template = (
        "# Enter one action per line. Lines starting with '#' are ignored.\n"
        "# Save and exit when done. Empty file = no actions created.\n"
        "\n"
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", prefix="action-", delete=False, encoding="utf-8"
    ) as f:
        f.write(template)
        tmp_path = f.name
    try:
        result = subprocess.run([editor, tmp_path])
        if result.returncode != 0:
            raise ActionError(f"editor '{editor}' exited with status {result.returncode}")
        with open(tmp_path, encoding="utf-8") as f:
            content = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _collect_from_repl(owner: str, src: str) -> list[str]:
    """Prompt-loop for action text. Blank line ends the batch. Ctrl-C/D aborts."""
    if not sys.stdin.isatty():
        raise ActionError("--interactive requires a TTY")
    src_label = src or "(none)"
    print(f"Owner: {owner}   Src: {src_label}   (blank Action to finish, Ctrl-C to abort)")
    texts: list[str] = []
    while True:
        try:
            line = input("Action: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise ActionError("interactive capture aborted — no rows written")
        if not line:
            return texts
        texts.append(line)


def _collect_new_texts(args: argparse.Namespace, owner: str) -> list[str]:
    """Resolve action texts from --editor / --interactive / --new args / stdin."""
    if args.editor:
        return _collect_from_editor()
    if args.interactive:
        return _collect_from_repl(owner, args.src or "")
    if args.new is None:
        return []
    if args.new:
        return [t.strip() for t in args.new if t.strip()]
    # --new flag with no positional args → read stdin if piped
    if not sys.stdin.isatty():
        return [line.rstrip() for line in sys.stdin if line.strip()]
    return []


def cmd_new(args: argparse.Namespace, path: Path) -> int:
    owner = args.owner or DEFAULT_OWNER
    status = args.status or "open"
    if status not in ALLOWED_STATUS:
        raise ActionError(f'invalid status "{status}" — must be one of {", ".join(ALLOWED_STATUS)}')

    texts = _collect_new_texts(args, owner)
    if not texts:
        raise ActionError(
            "no actions to create — pass text after --new, pipe via stdin, "
            "or use --editor / --interactive"
        )

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_actions_template(path.parent.name))

    model = parse_file(path)
    current_max = parse_next_id_from_data("\n".join(model.lines))
    notes = f"{today()}: {escape_pipes(args.note)}" if args.note else ""
    files: list[str] = [str(normalize_attachment_path(raw)) for raw in collect_attach_args(args)]
    files_cell = render_files_cell(files)

    written_ids: list[str] = []
    for i, text in enumerate(texts):
        aid = f"A-{current_max + i:03d}"
        if status in TERMINAL_STATUS:
            insert_closed_row(model, {
                "ID": aid, "Issue": "",
                "Action": escape_pipes(text),
                "Owner": owner,
                "Closed": today(),
                "Files": files_cell, "Notes": notes,
            })
        else:
            insert_open_row(model, {
                "ID": aid, "Issue": "",
                "Action": escape_pipes(text),
                "Owner": owner, "Status": status,
                "Opened": today(),
                "Src": escape_pipes(args.src) if args.src else "",
                "Files": files_cell, "Notes": notes,
            })
        written_ids.append(aid)

    bump_next_id(model, current_max + len(texts))
    model.write()

    args._written_ids = written_ids  # main() reads this for the commit message

    suffix = f" [+{len(files)} file{'s' if len(files) != 1 else ''}]" if files else ""
    if len(written_ids) == 1:
        print(f"created {written_ids[0]}: {texts[0]} [Owner: {owner}]{suffix}")
    else:
        print(f"created {len(written_ids)} actions [Owner: {owner}]{suffix}:")
        for aid, text in zip(written_ids, texts):
            print(f"  {aid}: {text}")
    return 0


def collect_attach_args(args: argparse.Namespace) -> list[str]:
    """Flatten --attach values (each may itself be comma-separated)."""
    out: list[str] = []
    for value in (args.attach or []):
        for piece in value.split(","):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def collect_unattach_args(args: argparse.Namespace) -> list[str]:
    out: list[str] = []
    for value in (args.unattach or []):
        for piece in value.split(","):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def remove_attachment(files: list[str], query: str) -> tuple[list[str], str]:
    """Remove a file from the list by full path or basename. Returns (new_list, removed_path)."""
    # exact path match first
    for f in files:
        if f == query:
            return ([x for x in files if x != f], f)
    # basename match
    matches = [f for f in files if Path(f).name == Path(query).name]
    if len(matches) == 1:
        return ([x for x in files if x != matches[0]], matches[0])
    if len(matches) > 1:
        raise ActionError(
            f'attachment "{query}" matches multiple files; pass the full path: '
            + ", ".join(matches)
        )
    raise ActionError(f'no attachment matches "{query}"')


# ---------- git helpers ----------

def _git_detect_repo(repo_path: Path) -> bool:
    """Return True if repo_path is inside a git repo."""
    r = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"],
        capture_output=True, timeout=10,
    )
    return r.returncode == 0


def _git_current_branch(repo_path: Path) -> str:
    """Return current branch name, or 'main' as fallback."""
    r = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip() if r.returncode == 0 else "main"


def _git_pull_rebase(repo_path: Path) -> str:
    """Pull with --rebase. Returns GIT_OK, GIT_NETWORK_ERROR, GIT_CONFLICT, or GIT_NOT_A_REPO."""
    if not _git_detect_repo(repo_path):
        return GIT_NOT_A_REPO
    branch = _git_current_branch(repo_path)
    r = subprocess.run(
        ["git", "-C", str(repo_path), "pull", "--rebase", "origin", branch],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0:
        return GIT_OK
    combined = (r.stdout + r.stderr).lower()
    if "conflict" in combined:
        return GIT_CONFLICT
    if any(phrase in combined for phrase in (
        "could not resolve host", "unable to access", "network is unreachable", "timed out"
    )):
        return GIT_NETWORK_ERROR
    # fail-open: treat any other non-zero as a network error
    return GIT_NETWORK_ERROR


def _git_commit_and_push(repo_path: Path, actions_md: Path, message: str) -> str:
    """Stage, commit, and push ACTIONS.md. Returns GIT_OK, GIT_PUSH_REJECTED, or GIT_NETWORK_ERROR."""
    branch = _git_current_branch(repo_path)

    # Stage
    r = subprocess.run(
        ["git", "-C", str(repo_path), "add", str(actions_md)],
        capture_output=True, timeout=10,
    )
    if r.returncode != 0:
        return GIT_NETWORK_ERROR

    # Commit
    r = subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", message],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        if "nothing to commit" in (r.stdout + r.stderr).lower():
            return GIT_OK  # idempotent
        return GIT_NETWORK_ERROR

    # Push
    r = subprocess.run(
        ["git", "-C", str(repo_path), "push", "--force-with-lease", "origin", branch],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0:
        return GIT_OK
    combined = (r.stdout + r.stderr).lower()
    if "rejected" in combined or "non-fast-forward" in combined:
        return GIT_PUSH_REJECTED
    return GIT_NETWORK_ERROR


def _commit_message_for(
    verb: str,
    action_id: str | list[str],
    owner: str | None = None,
    status: str | None = None,
) -> str:
    """Build a conventional commit message for an ACTIONS.md mutation.

    `action_id` may be a single ID string or a list of IDs (multi-row add).
    """
    if isinstance(action_id, list):
        if not action_id:
            ids_str = ""
        elif len(action_id) == 1:
            ids_str = action_id[0]
        elif len(action_id) <= 3:
            ids_str = ", ".join(action_id)
        else:
            ids_str = f"{action_id[0]}..{action_id[-1]} ({len(action_id)} actions)"
    else:
        ids_str = action_id

    if verb == "add":
        tail = f"add {ids_str} ({owner})" if owner else f"add {ids_str}"
    elif verb == "close":
        tail = f"close {ids_str} → {status}" if status else f"close {ids_str}"
    elif verb == "reopen":
        tail = f"reopen {ids_str}"
    elif verb == "note":
        tail = f"note on {ids_str}"
    else:
        tail = f"update {ids_str}"
    return f"chore(action): {tail}"


def cmd_list(args: argparse.Namespace, path: Path) -> int:
    model = parse_file(path)
    rows: list[tuple[str, dict[str, str]]] = []  # (table_label, cells)

    if args.closed or (args.status and args.status.lower() == "closed"):
        for cells in model.closed_rows():
            rows.append(("closed", cells))
    elif args.all:
        for cells in model.open_rows():
            rows.append(("open", cells))
        for cells in model.closed_rows():
            rows.append(("closed", cells))
    else:
        for cells in model.open_rows():
            rows.append(("open", cells))

    def matches(label: str, cells: dict[str, str]) -> bool:
        if args.status and args.status.lower() != "closed":
            if label == "closed":
                return False
            if cells.get("Status", "").lower() != args.status.lower():
                return False
        if args.owner:
            if cells.get("Owner", "").lower() != args.owner.lower():
                return False
        return True

    rows = [(lbl, c) for lbl, c in rows if matches(lbl, c)]
    if not rows:
        print("(no matching actions)")
        return 0

    if args.short:
        for lbl, c in rows:
            if lbl == "closed":
                status_col = f"closed:{c.get('Closed', '?')}"
            else:
                status_col = c.get("Status", "?")
            print(f"{c.get('ID', '?'):<6} {c.get('Owner', '?'):<8} {status_col:<14} {c.get('Action', '')}")
        return 0

    def _cell(c: dict[str, str], key: str, default: str = "-") -> str:
        val = (c.get(key, "") or "").strip()
        return val if val else default

    def _status(lbl: str, c: dict[str, str]) -> str:
        if lbl == "closed":
            return f"closed:{c.get('Closed', '?')}"
        return _cell(c, "Status")

    def _files_count(c: dict[str, str]) -> str:
        files = parse_files_cell(c.get("Files", ""))
        return str(len(files)) if files else "-"

    rendered = [
        {
            "ID":     _cell(c, "ID", "?"),
            "Owner":  _cell(c, "Owner"),
            "Status": _status(lbl, c),
            "Opened": _cell(c, "Opened"),
            "Src":    _cell(c, "Src"),
            "Issue":  _cell(c, "Issue"),
            "Files":  _files_count(c),
            "Action": _cell(c, "Action", ""),
        }
        for lbl, c in rows
    ]

    fixed_cols = ["ID", "Owner", "Status", "Opened", "Src", "Issue", "Files"]
    widths = {col: max(len(col), max(len(r[col]) for r in rendered)) for col in fixed_cols}

    term_width = shutil.get_terminal_size((120, 24)).columns
    fixed_width = sum(widths.values()) + 2 * len(fixed_cols)  # 2-space gutter after each fixed col
    action_budget = max(20, term_width - fixed_width)

    def _join(values: list[str]) -> str:
        parts = [v.ljust(widths[col]) for col, v in zip(fixed_cols, values[:-1])]
        parts.append(values[-1])
        return "  ".join(parts)

    print(_join([*fixed_cols, "Action"]))
    for r in rendered:
        action = r["Action"]
        if not args.no_trunc and len(action) > action_budget:
            action = action[: action_budget - 1] + "…"
        print(_join([r[c] for c in fixed_cols] + [action]))
    return 0


def cmd_show(args: argparse.Namespace, path: Path) -> int:
    model = parse_file(path)
    table, idx = model.find_row(args.id)
    cells = model.cells_at(idx, table)
    cols = OPEN_COLS if table == "open" else CLOSED_COLS
    print(f"[{table}] {args.id}")
    for col in cols:
        val = cells.get(col, "")
        if col == "Files":
            files = parse_files_cell(val)
            if not files:
                print(f"  {col:<8} (none)")
            else:
                print(f"  {col:<8} {len(files)} file{'s' if len(files) != 1 else ''}")
                for f in files:
                    print(f"           - {f}")
        else:
            print(f"  {col:<8} {val}")
    return 0


def cmd_update(args: argparse.Namespace, path: Path) -> int:
    if args.reopen and args.status:
        raise ActionError("--reopen cannot be combined with --status")
    if args.status and args.status not in ALLOWED_STATUS:
        raise ActionError(f'invalid status "{args.status}" — must be one of {", ".join(ALLOWED_STATUS)}')

    model = parse_file(path)
    table, idx = model.find_row(args.id)
    cells = model.cells_at(idx, table)
    prior_status = cells.get("Status", "")
    msgs: list[str] = []

    # in-place updates first
    if args.owner:
        cells["Owner"] = args.owner
        msgs.append(f"owner → {args.owner}")
    if args.note:
        cells["Notes"] = append_note(cells.get("Notes", ""), args.note)
        msgs.append("note appended")
    attach_args = collect_attach_args(args)
    if attach_args:
        files = parse_files_cell(cells.get("Files", ""))
        added = 0
        for raw in attach_args:
            resolved = str(normalize_attachment_path(raw))
            if resolved not in files:
                files.append(resolved)
                added += 1
        cells["Files"] = render_files_cell(files)
        msgs.append(f"+{added} file{'s' if added != 1 else ''}")
    unattach_args = collect_unattach_args(args)
    if unattach_args:
        files = parse_files_cell(cells.get("Files", ""))
        removed = 0
        for query in unattach_args:
            files, _ = remove_attachment(files, query)
            removed += 1
        cells["Files"] = render_files_cell(files)
        msgs.append(f"-{removed} file{'s' if removed != 1 else ''}")

    # status / reopen transition
    if args.reopen:
        if table == "open":
            raise ActionError(f"{args.id} is already in Open")
        # move closed -> open
        new_open = {
            "ID": cells["ID"],
            "Issue": cells.get("Issue", ""),
            "Action": cells.get("Action", ""),
            "Owner": cells.get("Owner", ""),
            "Status": "open",
            "Opened": today(),
            "Src": "",
            "Files": cells.get("Files", ""),
            "Notes": cells.get("Notes", ""),
        }
        remove_row(model, idx, "closed")
        insert_open_row(model, new_open)
        msgs.append("reopened")
    elif args.status and args.status in TERMINAL_STATUS:
        if table == "open":
            new_closed = {
                "ID": cells["ID"],
                "Issue": cells.get("Issue", ""),
                "Action": cells.get("Action", ""),
                "Owner": cells.get("Owner", ""),
                "Closed": today(),
                "Files": cells.get("Files", ""),
                "Notes": cells.get("Notes", ""),
            }
            remove_row(model, idx, "open")
            insert_closed_row(model, new_closed)
            msgs.append(f"status {prior_status} → {args.status}, moved to Recently Closed")
        else:
            # already closed; just update Closed date if a meaningful change requested
            cells["Closed"] = today()
            replace_row(model, idx, cells, CLOSED_COLS)
            msgs.append(f"already closed — updated Closed date to {today()}")
    elif args.status:
        if table == "closed":
            raise ActionError(
                f"{args.id} is in Recently Closed; use --reopen to move it back to Open"
            )
        cells["Status"] = args.status
        replace_row(model, idx, cells, OPEN_COLS)
        msgs.append(f"status {prior_status} → {args.status}")
    else:
        # only owner/note changes
        replace_row(model, idx, cells, OPEN_COLS if table == "open" else CLOSED_COLS)

    if not msgs:
        raise ActionError(
            "no changes specified — pass --status, --note, --owner, --attach, --unattach, or --reopen"
        )

    model.write()
    print(f"{args.id}: {'; '.join(msgs)}")
    return 0


# ---------- argparse + dispatch ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="action", add_help=False)
    p.add_argument("id", nargs="?", default=None)
    p.add_argument("--help", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--closed", action="store_true")
    p.add_argument("--status")
    p.add_argument("--owner")
    p.add_argument("--note")
    p.add_argument("--src")
    p.add_argument("--reopen", action="store_true")
    p.add_argument("--new", nargs="*", default=None)
    p.add_argument("-e", "--editor", action="store_true", default=False)
    p.add_argument("-i", "--interactive", action="store_true", default=False)
    p.add_argument("--attach", action="append", default=[])
    p.add_argument("--unattach", action="append", default=[])
    p.add_argument("-p", "--project")
    p.add_argument("--no-prompt", action="store_true", default=False)
    p.add_argument("--no-commit", action="store_true", default=False)
    p.add_argument("--strict", action="store_true", default=False)
    p.add_argument("--short", action="store_true", default=False)
    p.add_argument("--no-trunc", action="store_true", default=False)
    args = p.parse_args(argv)

    # --editor and --interactive imply a capture session even without --new.
    if (args.editor or args.interactive) and args.new is None:
        args.new = []

    # validation
    if args.id is not None and not ID_RE.match(args.id):
        raise ActionError(
            f'invalid action id "{args.id}" — expected format A-NNN (e.g. A-002)'
        )
    if args.new is not None and args.id:
        raise ActionError("cannot combine --new with an action id")
    if args.editor and args.interactive:
        raise ActionError("--editor and --interactive are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)
    except (ActionError, MarkdownParseError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.help:
        print(HELP_TEXT, end="")
        return 0

    try:
        project = resolve_project_with_picker(args)
        path = project_path(project)

        # Read-only operations: no git
        if args.list:
            return cmd_list(args, path)
        if args.id and not any([
            args.status, args.note, args.owner, args.reopen, args.attach, args.unattach,
        ]):
            return cmd_show(args, path)

        # Mutation operations: wrap with git pull/push unless --no-commit
        is_mutation = (args.new is not None) or args.id
        if not is_mutation:
            raise ActionError("no operation specified — use --help for usage")

        repo_path = path.parent
        # _do_push: True when a post-write commit+push should happen
        _do_push = True

        if not args.no_commit:
            pull_result = _git_pull_rebase(repo_path)
            if pull_result == GIT_CONFLICT:
                print(
                    f"error: cannot sync ACTIONS.md — pull conflict on this file.\n"
                    f"  Resolve manually:\n"
                    f"    cd {repo_path}\n"
                    f"    git status\n"
                    f"    # edit ACTIONS.md, then:\n"
                    f"    git add ACTIONS.md && git rebase --continue\n"
                    f"  Then retry the action.",
                    file=sys.stderr,
                )
                return 1
            elif pull_result == GIT_NETWORK_ERROR:
                if args.strict:
                    print(
                        "error: cannot sync — offline. Pass --no-commit to write locally without git.",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    "WARNING: offline — could not pull latest. Writing locally.\n"
                    "  Sync manually with `git push` when network returns."
                )
                _do_push = False
            elif pull_result == GIT_NOT_A_REPO:
                _do_push = False
            # GIT_OK: proceed normally (push will run)

        # Dispatch mutation
        if args.new is not None:
            verb = "add"
            rc = cmd_new(args, path)
            written_ids = getattr(args, "_written_ids", []) or []
            owner_for_msg = args.owner or DEFAULT_OWNER
            commit_msg = _commit_message_for("add", written_ids, owner=owner_for_msg)
        else:
            rc = cmd_update(args, path)
            # Determine verb from args
            if args.reopen:
                verb = "reopen"
            elif args.status in TERMINAL_STATUS if args.status else False:
                verb = "close"
            elif args.note and not args.status and not args.owner:
                verb = "note"
            else:
                verb = "update"
            commit_msg = _commit_message_for(verb, args.id, status=args.status)

        if rc != 0:
            return rc

        if not args.no_commit and _do_push:
            push_result = _git_commit_and_push(repo_path, path, commit_msg)
            if push_result == GIT_PUSH_REJECTED:
                print(
                    "error: push rejected — another device wrote between rebase and commit.\n"
                    "  Run the same command again to retry.",
                    file=sys.stderr,
                )
                return 1
            elif push_result == GIT_NETWORK_ERROR:
                # Non-fatal: file already written locally
                print(
                    "WARNING: could not push — network error. File written locally.\n"
                    "  Sync manually with `git push` when network returns."
                )

        return 0
    except (ActionError, MarkdownParseError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
