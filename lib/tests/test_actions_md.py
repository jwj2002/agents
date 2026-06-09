"""Unit tests for lib/actions_md.py (issue #369).

The schema-migration paths (v1/v2 → current) and _row_cells branching were
previously covered only indirectly through the action CLI integration tests.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.actions_md import (  # noqa: E402
    CLOSED_COLS,
    CLOSED_COLS_V1,
    CLOSED_COLS_V2,
    OPEN_COLS,
    OPEN_COLS_V1,
    MarkdownParseError,
    _row_cells,
    escape_pipes,
    parse_file,
    parse_files_cell,
    parse_next_id_from_data,
    render_files_cell,
    render_row,
)


def _doc(open_rows: list[str], closed_rows: list[str], *,
         open_cols=OPEN_COLS, closed_cols=CLOSED_COLS, next_id: str | None = "A-010") -> str:
    def table(cols, rows):
        head = render_row(cols, {c: c for c in cols})
        sep = "|" + "|".join(["----"] * len(cols)) + "|"
        return "\n".join([head, sep, *rows])

    parts = [
        "# Actions",
        "",
        "## Open",
        "",
        table(open_cols, open_rows),
        "",
        "## Recently Closed",
        "",
        table(closed_cols, closed_rows),
        "",
    ]
    if next_id:
        parts.append(f"Next ID: {next_id}")
    return "\n".join(parts)


CUR_OPEN = "| A-001 | #5 | Do thing | Jason | open | 2026-06-01 | gh | a.py | note |"
V1_OPEN = "| A-002 | #6 | Old thing | Jason | open | 2026-05-01 | gh | old note |"
CUR_CLOSED = "| A-003 | #7 | Done | Jason | 2026-05-01 | 2026-06-01 | b.py | done |"
V2_CLOSED = "| A-004 | #8 | Done v2 | Jason | 2026-06-02 | c.py | n |"
V1_CLOSED = "| A-005 | #9 | Done v1 | Jason | 2026-06-03 | n |"


# ---------- _row_cells schema branching ----------

def test_row_cells_current_schema():
    cells = _row_cells(CUR_OPEN, OPEN_COLS, OPEN_COLS_V1)
    assert cells["ID"] == "A-001"
    assert cells["Files"] == "a.py"


def test_row_cells_legacy_synthesizes_missing_fields():
    cells = _row_cells(V1_OPEN, OPEN_COLS, OPEN_COLS_V1)
    assert cells["ID"] == "A-002"
    assert cells["Notes"] == "old note"
    assert cells["Files"] == ""  # synthesized — every current key present


def test_row_cells_malformed_returns_empty():
    assert _row_cells("| only | three | cells |", OPEN_COLS, OPEN_COLS_V1) == {}


def test_row_cells_tries_multiple_legacies():
    v2 = _row_cells(V2_CLOSED, CLOSED_COLS, CLOSED_COLS_V2, CLOSED_COLS_V1)
    assert v2["Files"] == "c.py" and v2["Opened"] == ""
    v1 = _row_cells(V1_CLOSED, CLOSED_COLS, CLOSED_COLS_V2, CLOSED_COLS_V1)
    assert v1["Closed"] == "2026-06-03" and v1["Files"] == "" and v1["Opened"] == ""


# ---------- parse_file ----------

def test_parse_file_reads_rows_and_next_id(tmp_path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_doc([CUR_OPEN], [CUR_CLOSED]))
    m = parse_file(p)
    assert [r["ID"] for r in m.open_rows()] == ["A-001"]
    assert [r["ID"] for r in m.closed_rows()] == ["A-003"]
    assert m.next_id_num == 10


def test_parse_file_derives_next_id_from_data_when_marker_missing(tmp_path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_doc([CUR_OPEN], [CUR_CLOSED], next_id=None))
    m = parse_file(p)
    assert m.next_id_num == 4  # max(A-001, A-003) + 1


def test_parse_file_missing_section_raises(tmp_path):
    p = tmp_path / "ACTIONS.md"
    p.write_text("# Actions\n\n## Open\n\n| ID |\n|----|\n")
    with pytest.raises(MarkdownParseError):
        parse_file(p)


def test_parse_file_missing_file_raises(tmp_path):
    with pytest.raises(MarkdownParseError):
        parse_file(tmp_path / "nope.md")


def test_find_row_and_missing_id(tmp_path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_doc([CUR_OPEN], [CUR_CLOSED]))
    m = parse_file(p)
    assert m.find_row("A-001")[0] == "open"
    assert m.find_row("A-003")[0] == "closed"
    with pytest.raises(MarkdownParseError):
        m.find_row("A-999")


# ---------- migration ----------

def test_migrate_v1_open_table_gains_files_column(tmp_path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_doc([V1_OPEN], [V1_CLOSED],
                      open_cols=OPEN_COLS_V1, closed_cols=CLOSED_COLS_V1))
    m = parse_file(p)
    m.write()
    m2 = parse_file(p)
    header = m2.lines[m2.open_sep_idx - 1]
    assert "Files" in header
    row = m2.open_rows()[0]
    assert row["ID"] == "A-002" and row["Files"] == ""
    closed = m2.closed_rows()[0]
    assert closed["ID"] == "A-005" and closed["Files"] == ""


def test_migrate_is_idempotent(tmp_path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_doc([CUR_OPEN], [CUR_CLOSED]))
    m = parse_file(p)
    m.write()
    first = p.read_text()
    parse_file(p).write()
    assert p.read_text() == first


def test_write_roundtrip_preserves_data(tmp_path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_doc([CUR_OPEN], [CUR_CLOSED]))
    before = parse_file(p)
    rows_before = (before.open_rows(), before.closed_rows())
    before.write()
    after = parse_file(p)
    assert (after.open_rows(), after.closed_rows()) == rows_before


# ---------- small helpers ----------

def test_parse_next_id_from_data_prefers_data_over_marker():
    content = _doc([CUR_OPEN], [CUR_CLOSED], next_id="A-002")  # marker LIES (data has A-003)
    assert parse_next_id_from_data(content) == 4


def test_escape_pipes_and_files_cells():
    assert "\\|" in escape_pipes("a|b")
    assert parse_files_cell("a.py, b.py") == ["a.py", "b.py"]
    assert parse_files_cell("") == []
    assert render_files_cell(["a.py", "b.py"]) == "a.py, b.py"
