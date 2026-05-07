"""ACTIONS.md schema, parser, and row mutators.

Tool-agnostic. Both `action/cli.py` and `dashboard/cli.py` consume this.

Read path:
- parse_file(path) -> FileModel
- model.open_rows() / model.closed_rows() -> list[dict[str, str]]

Mutation path:
- insert_open_row / insert_closed_row / replace_row / remove_row
- bump_next_id

All parse failures raise MarkdownParseError. Callers translate to their own
user-facing error type.

Schema (v2): | ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
            | ID | Issue | Action | Owner | Closed | Files | Notes |
Legacy v1 (no Files col) is tolerated on read; auto-migrated on next write.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Current schema (v2): Files column inserted between Src/Closed and Notes.
OPEN_COLS = ["ID", "Issue", "Action", "Owner", "Status", "Opened", "Src", "Files", "Notes"]
CLOSED_COLS = ["ID", "Issue", "Action", "Owner", "Closed", "Files", "Notes"]
# Legacy schema (v1): no Files column. Tolerated on read; auto-migrated on next write.
OPEN_COLS_V1 = ["ID", "Issue", "Action", "Owner", "Status", "Opened", "Src", "Notes"]
CLOSED_COLS_V1 = ["ID", "Issue", "Action", "Owner", "Closed", "Notes"]

ALLOWED_STATUS = ("open", "wip", "blocked", "done", "cancelled")
TERMINAL_STATUS = ("done", "cancelled")
ID_RE = re.compile(r"^A-\d+$")


class MarkdownParseError(Exception):
    """Raised when an ACTIONS.md file is missing or malformed."""


# ---------- text helpers ----------

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


def parse_files_cell(s: str) -> list[str]:
    s = s.strip()
    if not s:
        return []
    return [p.strip().replace(r"\|", "|") for p in s.split(",") if p.strip()]


def render_files_cell(paths: list[str]) -> str:
    return ", ".join(escape_pipes(p) for p in paths)


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


# ---------- file model ----------

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
        raise MarkdownParseError(f"{action_id} not found in {self.path.parent.name}")

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
        raise MarkdownParseError(f"ACTIONS.md not found at {path}")
    lines = path.read_text().split("\n")

    def find_h2(name: str) -> int:
        target = f"## {name}"
        for i, line in enumerate(lines):
            if line.strip() == target:
                return i
        raise MarkdownParseError(f"{path}: missing '## {name}' section")

    open_h2 = find_h2("Open")
    closed_h2 = find_h2("Recently Closed")

    def find_sep(start: int) -> int:
        for i in range(start + 1, len(lines)):
            if is_table_separator(lines[i]):
                return i
            if lines[i].strip().startswith("##"):
                raise MarkdownParseError(f"{path}: no table under '## {lines[start].strip()[3:]}'")
        raise MarkdownParseError(f"{path}: no table under '## {lines[start].strip()[3:]}'")

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


def parse_next_id_from_data(content: str) -> int:
    """Scan all table rows in content; return max(IDs) + 1 or 1 if none found.

    This is the authoritative ID-derivation path. The marker line is kept for
    human readability but the data always wins on mutation.
    """
    lines = content.split("\n")
    ids: list[int] = []
    for line in lines:
        cells = split_row(line)
        if cells and ID_RE.match(cells[0]):
            ids.append(int(cells[0].split("-")[1]))
    return (max(ids) + 1) if ids else 1


# ---------- mutations ----------

def replace_row(model: FileModel, line_idx: int, cells: dict[str, str], cols: list[str]) -> None:
    model.lines[line_idx] = render_row(cols, cells)


def remove_row(model: FileModel, line_idx: int, table: str) -> None:
    del model.lines[line_idx]
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
        return
    model.lines[model.next_id_idx] = f"Next ID: **A-{new_num:03d}**"
    model.next_id_num = new_num
