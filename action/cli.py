#!/usr/bin/env python3
"""action — CRUD for ACTIONS.md.

The Python implementation. The /action Claude skill just shells out here.
For shell use directly: alias action='python3 ~/agents/action/cli.py'.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

HOME = Path.home()
ALLOWED_STATUS = ("open", "wip", "blocked", "done", "cancelled")
TERMINAL_STATUS = ("done", "cancelled")
ID_RE = re.compile(r"^A-\d+$")

# Current schema (v2): Files column inserted between Src/Closed and Notes.
OPEN_COLS = ["ID", "Issue", "Action", "Owner", "Status", "Opened", "Src", "Files", "Notes"]
CLOSED_COLS = ["ID", "Issue", "Action", "Owner", "Closed", "Files", "Notes"]
# Legacy schema (v1): no Files column. Tolerated on read; auto-migrated on next write.
OPEN_COLS_V1 = ["ID", "Issue", "Action", "Owner", "Status", "Opened", "Src", "Notes"]
CLOSED_COLS_V1 = ["ID", "Issue", "Action", "Owner", "Closed", "Notes"]

HELP_TEXT = """\
/action — manage entries in a project's ACTIONS.md

Read:
  action --help                       Show this help
  action --list                       List open actions in current project
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
  action --new "..." --owner <name>   Add a new action (auto-bumps Next ID)
                       [--status <s>]  Default: open
                       [--note "..."]
                       [--src "..."]
                       [--attach <path>]

Project resolution:
  --project <name>                     Override; otherwise inferred from cwd
                                       (~/agents → agents, ~/projects/X → X)

Status values: open · wip · blocked · done · cancelled
"""


class ActionError(Exception):
    """Single-line error to stderr + non-zero exit."""


# ---------- helpers ----------

def today() -> str:
    return date.today().isoformat()


def escape_pipes(s: str) -> str:
    return s.replace("|", r"\|")


def is_table_separator(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and all(c in "-:| " for c in s)


def split_row(line: str) -> list[str]:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return []
    return [p.strip() for p in s[1:-1].split("|")]


def render_row(cols: list[str], cells: dict[str, str]) -> str:
    return "| " + " | ".join(cells.get(c, "") for c in cols) + " |"


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


def parse_files_cell(s: str) -> list[str]:
    s = s.strip()
    if not s:
        return []
    return [p.strip().replace(r"\|", "|") for p in s.split(",") if p.strip()]


def render_files_cell(paths: list[str]) -> str:
    return ", ".join(escape_pipes(p) for p in paths)


# ---------- file model ----------

def _row_cells(line: str, schema: list[str], legacy: list[str]) -> dict[str, str]:
    """Parse a markdown table row into a dict, tolerating the legacy (no-Files) schema."""
    cells = split_row(line)
    if len(cells) == len(schema):
        return dict(zip(schema, cells))
    if len(cells) == len(legacy):
        d = dict(zip(legacy, cells))
        d["Files"] = ""  # synthesize missing column
        return d
    return {}  # malformed; treat as no row


@dataclass
class FileModel:
    path: Path
    lines: list[str]
    open_sep_idx: int           # index of `|----|----|` for Open
    closed_sep_idx: int         # index of `|----|----|` for Recently Closed
    open_row_indices: list[int]
    closed_row_indices: list[int]
    next_id_idx: int            # index of `Next ID:` line, or -1 if missing
    next_id_num: int            # integer for the next-to-create id

    def open_rows(self) -> list[dict[str, str]]:
        return [_row_cells(self.lines[i], OPEN_COLS, OPEN_COLS_V1) for i in self.open_row_indices]

    def closed_rows(self) -> list[dict[str, str]]:
        return [_row_cells(self.lines[i], CLOSED_COLS, CLOSED_COLS_V1) for i in self.closed_row_indices]

    def find_row(self, action_id: str) -> tuple[str, int]:
        """Return (table, line_index) where table ∈ {'open', 'closed'}."""
        for i in self.open_row_indices:
            cells = _row_cells(self.lines[i], OPEN_COLS, OPEN_COLS_V1)
            if cells.get("ID") == action_id:
                return ("open", i)
        for i in self.closed_row_indices:
            cells = _row_cells(self.lines[i], CLOSED_COLS, CLOSED_COLS_V1)
            if cells.get("ID") == action_id:
                return ("closed", i)
        raise ActionError(f"{action_id} not found in {self.path.parent.name}")

    def cells_at(self, line_idx: int, table: str) -> dict[str, str]:
        """Read a row at line_idx, normalized to current schema."""
        if table == "open":
            return _row_cells(self.lines[line_idx], OPEN_COLS, OPEN_COLS_V1)
        return _row_cells(self.lines[line_idx], CLOSED_COLS, CLOSED_COLS_V1)

    def migrate_schema_in_place(self) -> None:
        """Rewrite header + separator + every data row to current schema.

        Idempotent: rows already in current schema are reformatted but
        unchanged; rows in legacy v1 schema gain an empty Files cell.
        """
        # Open header lives one line above the separator.
        if self.open_sep_idx > 0:
            self.lines[self.open_sep_idx - 1] = render_row(OPEN_COLS, {c: c for c in OPEN_COLS})
            self.lines[self.open_sep_idx] = (
                "|" + "|".join(["----"] * len(OPEN_COLS)) + "|"
            )
        for i in self.open_row_indices:
            cells = _row_cells(self.lines[i], OPEN_COLS, OPEN_COLS_V1)
            if cells:
                self.lines[i] = render_row(OPEN_COLS, cells)

        if self.closed_sep_idx > 0:
            self.lines[self.closed_sep_idx - 1] = render_row(CLOSED_COLS, {c: c for c in CLOSED_COLS})
            self.lines[self.closed_sep_idx] = (
                "|" + "|".join(["----"] * len(CLOSED_COLS)) + "|"
            )
        for i in self.closed_row_indices:
            cells = _row_cells(self.lines[i], CLOSED_COLS, CLOSED_COLS_V1)
            if cells:
                self.lines[i] = render_row(CLOSED_COLS, cells)

    def write(self) -> None:
        self.migrate_schema_in_place()
        self.path.write_text("\n".join(self.lines))


def parse_file(path: Path) -> FileModel:
    if not path.exists():
        raise ActionError(f"ACTIONS.md not found at {path}")
    lines = path.read_text().split("\n")
    if lines and lines[-1] == "":
        # preserve trailing newline by leaving the final "" element; we'll re-join with \n
        pass

    def find_h2(name: str) -> int:
        target = f"## {name}"
        for i, line in enumerate(lines):
            if line.strip() == target:
                return i
        raise ActionError(f"{path}: missing '## {name}' section")

    open_h2 = find_h2("Open")
    closed_h2 = find_h2("Recently Closed")

    def find_sep(start: int) -> int:
        for i in range(start + 1, len(lines)):
            if is_table_separator(lines[i]):
                return i
            if lines[i].strip().startswith("##"):
                raise ActionError(f"{path}: no table under '## {lines[start].strip()[3:]}'")
        raise ActionError(f"{path}: no table under '## {lines[start].strip()[3:]}'")

    open_sep = find_sep(open_h2)
    closed_sep = find_sep(closed_h2)

    def collect_rows(after_idx: int) -> list[int]:
        out = []
        i = after_idx + 1
        while i < len(lines) and lines[i].strip().startswith("|"):
            out.append(i)
            i += 1
        return out

    open_row_indices = collect_rows(open_sep)
    closed_row_indices = collect_rows(closed_sep)

    # next id
    next_id_idx = -1
    next_id_num = 1
    for i, line in enumerate(lines):
        if line.strip().startswith("Next ID:"):
            next_id_idx = i
            m = re.search(r"A-(\d+)", line)
            if m:
                next_id_num = int(m.group(1))
            break
    if next_id_idx == -1:
        # fall back: max(existing) + 1
        all_ids = []
        for i in open_row_indices + closed_row_indices:
            cells = split_row(lines[i])
            if cells and ID_RE.match(cells[0]):
                all_ids.append(int(cells[0].split("-")[1]))
        next_id_num = (max(all_ids) + 1) if all_ids else 1

    return FileModel(
        path=path,
        lines=lines,
        open_sep_idx=open_sep,
        closed_sep_idx=closed_sep,
        open_row_indices=open_row_indices,
        closed_row_indices=closed_row_indices,
        next_id_idx=next_id_idx,
        next_id_num=next_id_num,
    )


# ---------- mutations ----------

def replace_row(model: FileModel, line_idx: int, cells: dict[str, str], cols: list[str]) -> None:
    model.lines[line_idx] = render_row(cols, cells)


def remove_row(model: FileModel, line_idx: int, table: str) -> None:
    del model.lines[line_idx]
    # shift bookkeeping
    def shift(indices: list[int]) -> list[int]:
        return [i - 1 if i > line_idx else i for i in indices if i != line_idx]
    model.open_row_indices = shift(model.open_row_indices)
    model.closed_row_indices = shift(model.closed_row_indices)
    if model.closed_sep_idx > line_idx:
        model.closed_sep_idx -= 1
    if model.next_id_idx > line_idx:
        model.next_id_idx -= 1


def insert_open_row(model: FileModel, cells: dict[str, str]) -> None:
    insert_at = (model.open_row_indices[-1] + 1) if model.open_row_indices else (model.open_sep_idx + 1)
    model.lines.insert(insert_at, render_row(OPEN_COLS, cells))
    model.open_row_indices.append(insert_at)
    if model.closed_sep_idx >= insert_at:
        model.closed_sep_idx += 1
    model.closed_row_indices = [i + 1 if i >= insert_at else i for i in model.closed_row_indices]
    if model.next_id_idx >= insert_at:
        model.next_id_idx += 1


def insert_closed_row(model: FileModel, cells: dict[str, str]) -> None:
    insert_at = (model.closed_row_indices[-1] + 1) if model.closed_row_indices else (model.closed_sep_idx + 1)
    model.lines.insert(insert_at, render_row(CLOSED_COLS, cells))
    model.closed_row_indices.append(insert_at)
    if model.next_id_idx >= insert_at:
        model.next_id_idx += 1


def bump_next_id(model: FileModel, new_num: int) -> None:
    if model.next_id_idx == -1:
        return  # no Next ID line to update; user can add one
    model.lines[model.next_id_idx] = f"Next ID: **A-{new_num:03d}**"
    model.next_id_num = new_num


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


def project_path(name: str) -> Path:
    if name == "agents":
        return HOME / "agents" / "ACTIONS.md"
    return HOME / "projects" / name / "ACTIONS.md"


# ---------- commands ----------

def cmd_new(args: argparse.Namespace, path: Path) -> int:
    if not args.owner:
        raise ActionError("--new requires --owner")
    status = args.status or "open"
    if status not in ALLOWED_STATUS:
        raise ActionError(f'invalid status "{status}" — must be one of {", ".join(ALLOWED_STATUS)}')
    model = parse_file(path)
    aid = f"A-{model.next_id_num:03d}"
    notes = f"{today()}: {escape_pipes(args.note)}" if args.note else ""
    files: list[str] = []
    for raw in collect_attach_args(args):
        files.append(str(normalize_attachment_path(raw)))
    cells = {
        "ID": aid,
        "Issue": "",
        "Action": escape_pipes(args.new),
        "Owner": args.owner,
        "Status": status,
        "Opened": today(),
        "Src": escape_pipes(args.src) if args.src else "",
        "Files": render_files_cell(files),
        "Notes": notes,
    }
    if status in TERMINAL_STATUS:
        closed_cells = {
            "ID": aid,
            "Issue": "",
            "Action": escape_pipes(args.new),
            "Owner": args.owner,
            "Closed": today(),
            "Files": render_files_cell(files),
            "Notes": notes,
        }
        insert_closed_row(model, closed_cells)
    else:
        insert_open_row(model, cells)
    bump_next_id(model, model.next_id_num + 1)
    model.write()
    suffix = f" [+{len(files)} file{'s' if len(files) != 1 else ''}]" if files else ""
    print(f"created {aid}: {args.new} [Owner: {args.owner}]{suffix}")
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

    for lbl, c in rows:
        if lbl == "closed":
            status_col = f"closed:{c.get('Closed', '?')}"
        else:
            status_col = c.get("Status", "?")
        print(f"{c.get('ID', '?'):<6} {c.get('Owner', '?'):<8} {status_col:<14} {c.get('Action', '')}")
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
    p.add_argument("--new")
    p.add_argument("--attach", action="append", default=[])
    p.add_argument("--unattach", action="append", default=[])
    p.add_argument("--project")
    args = p.parse_args(argv)

    # validation
    if args.id is not None and not ID_RE.match(args.id):
        raise ActionError(
            f'invalid action id "{args.id}" — expected format A-NNN (e.g. A-002)'
        )
    if args.new and args.id:
        raise ActionError("cannot combine --new with an action id")
    return args


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)
    except ActionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.help:
        print(HELP_TEXT, end="")
        return 0

    try:
        project = resolve_project(args)
        path = project_path(project)
        if args.new:
            return cmd_new(args, path)
        if args.list:
            return cmd_list(args, path)
        if args.id and not any([
            args.status, args.note, args.owner, args.reopen, args.attach, args.unattach,
        ]):
            return cmd_show(args, path)
        if args.id:
            return cmd_update(args, path)
        raise ActionError("no operation specified — use --help for usage")
    except ActionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
