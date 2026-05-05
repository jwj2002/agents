"""Tests for cap. Loaded via importlib because cap has no .py extension."""

from __future__ import annotations

import importlib.util
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

CAP_PATH = Path(__file__).resolve().parent.parent / "cap"


def _load_cap():
    loader = SourceFileLoader("cap", str(CAP_PATH))
    spec = importlib.util.spec_from_loader("cap", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


cap = _load_cap()


# ---------- helpers ----------

def _seed_actions_md(
    path: Path,
    next_id: int = 1,
    rows: list[str] | None = None,
    next_id_suffix: str = "",
) -> None:
    rows_block = "\n".join(rows or []) + ("\n" if rows else "")
    path.write_text(
        "# Actions — test\n\n"
        "## Sources\n\n_(none yet)_\n\n"
        "## Open\n\n"
        "| ID | Issue | Action | Owner | Status | Opened | Src | Notes |\n"
        "|----|-------|--------|-------|--------|--------|-----|-------|\n"
        f"{rows_block}"
        "\n## Recently Closed\n\n"
        "| ID | Issue | Action | Owner | Closed | Notes |\n"
        "|----|-------|--------|-------|--------|-------|\n"
        "\n## Archive\n\n_(none yet)_\n\n"
        "---\n"
        f"Next ID: **A-{next_id:03d}**{next_id_suffix}\n"
    )


# ---------- format_row ----------

def test_format_row_basic():
    row = cap.format_row(11, "Do the thing", "Jason", "2026-05-04", "M1")
    assert row == "| A-011 |  | Do the thing | Jason | open | 2026-05-04 | M1 |  |"


def test_format_row_has_eight_columns():
    row = cap.format_row(11, "x", "Jason", "2026-05-04", "")
    # 8 cells means 9 pipe characters (including leading and trailing)
    assert row.count("|") == 9


def test_format_row_pads_id_to_three_digits():
    assert cap.format_row(1, "x", "Jason", "2026-05-04", "").startswith("| A-001 ")
    assert cap.format_row(999, "x", "Jason", "2026-05-04", "").startswith("| A-999 ")


def test_format_row_escapes_pipes():
    row = cap.format_row(5, "fix a|b parsing", "Jason", "2026-05-04", "")
    assert "fix a\\|b parsing" in row


def test_format_row_flattens_newlines():
    row = cap.format_row(5, "line1\nline2", "Jason", "2026-05-04", "")
    assert "line1 line2" in row
    assert "\n" not in row.replace(" ", "")


# ---------- parse_next_id ----------

def test_parse_next_id():
    assert cap.parse_next_id("...\nNext ID: **A-011**\n") == 11


def test_parse_next_id_missing_raises():
    with pytest.raises(cap.CapError):
        cap.parse_next_id("no marker here")


# ---------- insert_rows + capture ----------

def test_capture_appends_to_existing_file(tmp_path: Path):
    actions_path = tmp_path / "ACTIONS.md"
    _seed_actions_md(
        actions_path,
        next_id=11,
        rows=["| A-010 |  | old | Jason | done | 2026-05-01 |  |  |"],
    )

    ids = cap.capture(["First", "Second"], tmp_path, "Jason", "M1", today="2026-05-04")

    assert ids == ["A-011", "A-012"]
    content = actions_path.read_text()
    assert "| A-011 |  | First | Jason | open | 2026-05-04 | M1 |  |" in content
    assert "| A-012 |  | Second | Jason | open | 2026-05-04 | M1 |  |" in content
    assert "| A-010 |  | old |" in content
    assert "Next ID: **A-013**" in content


def test_capture_preserves_next_issue_suffix(tmp_path: Path):
    """Sweetprocess augments the footer with ` · Next issue: **#N**`. cap must keep it intact."""
    actions_path = tmp_path / "ACTIONS.md"
    _seed_actions_md(
        actions_path,
        next_id=11,
        next_id_suffix=" · Next issue: **#11**",
    )

    cap.capture(["First"], tmp_path, "Jason", "", today="2026-05-04")
    content = actions_path.read_text()
    assert "Next ID: **A-012** · Next issue: **#11**" in content


def test_capture_creates_file_when_missing(tmp_path: Path):
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    actions_path = project_dir / "ACTIONS.md"
    assert not actions_path.exists()

    ids = cap.capture(["Hello"], project_dir, "Jason", "", today="2026-05-04")

    assert ids == ["A-001"]
    content = actions_path.read_text()
    assert "# Actions — myproj" in content
    assert "| A-001 |  | Hello | Jason | open | 2026-05-04 |" in content
    assert "| ID | Issue | Action | Owner | Status | Opened | Src | Notes |" in content
    assert "Next ID: **A-002**" in content


def test_capture_empty_template_layout_is_correct(tmp_path: Path):
    """Regression for #110: blank line must sit between last row and `## Recently Closed`,
    NOT between the separator and the first row."""
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()

    cap.capture(["first", "second"], project_dir, "Jason", "", today="2026-05-04")
    content = (project_dir / "ACTIONS.md").read_text()

    separator = "|----|-------|--------|-------|--------|--------|-----|-------|"
    assert f"{separator}\n| A-001 |" in content
    assert (
        "| A-002 |  | second | Jason | open | 2026-05-04 |  |  |\n\n## Recently Closed"
        in content
    )
    assert f"{separator}\n\n| A-001" not in content


def test_capture_preserves_sections(tmp_path: Path):
    actions_path = tmp_path / "ACTIONS.md"
    _seed_actions_md(actions_path, next_id=1)

    cap.capture(["First"], tmp_path, "Jason", "", today="2026-05-04")

    content = actions_path.read_text()
    assert "## Sources" in content
    assert "## Recently Closed" in content
    assert "## Archive" in content


def test_capture_owner_override(tmp_path: Path):
    actions_path = tmp_path / "ACTIONS.md"
    _seed_actions_md(actions_path, next_id=1)
    cap.capture(["Search"], tmp_path, "Laura", "M1", today="2026-05-04")
    content = actions_path.read_text()
    assert "| Search | Laura | open | 2026-05-04 | M1 |" in content


def test_capture_empty_list_raises(tmp_path: Path):
    actions_path = tmp_path / "ACTIONS.md"
    _seed_actions_md(actions_path, next_id=1)
    with pytest.raises(cap.CapError):
        cap.capture([], tmp_path, "Jason", "", today="2026-05-04")


# ---------- atomic_write ----------

def test_atomic_write_no_temp_left_behind(tmp_path: Path):
    target = tmp_path / "out.md"
    cap.atomic_write(target, "hello")
    assert target.read_text() == "hello"
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_write_unchanged_on_failure(tmp_path: Path, monkeypatch):
    target = tmp_path / "out.md"
    target.write_text("original")

    def boom(*a, **kw):
        raise OSError("disk on fire")

    monkeypatch.setattr(cap.os, "replace", boom)
    with pytest.raises(OSError):
        cap.atomic_write(target, "new content")
    assert target.read_text() == "original"
    assert not list(tmp_path.glob("*.tmp"))


# ---------- find_project_root ----------

def test_find_project_root_git(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sub = tmp_path / "sub"
    sub.mkdir()
    found = cap.find_project_root(sub)
    assert found is not None and found.resolve() == tmp_path.resolve()


def test_find_project_root_actions_marker(tmp_path: Path):
    (tmp_path / "ACTIONS.md").write_text("placeholder")
    sub = tmp_path / "deep" / "sub"
    sub.mkdir(parents=True)
    found = cap.find_project_root(sub)
    assert found is not None and found.resolve() == tmp_path.resolve()


def test_find_project_root_claude_marker(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text("placeholder")
    found = cap.find_project_root(tmp_path)
    assert found is not None and found.resolve() == tmp_path.resolve()


def test_find_project_root_none_when_no_repo(tmp_path: Path, monkeypatch):
    # /tmp/pytest-... has no git repo and no markers up the chain
    # (until we hit something on the way to /). To make this deterministic,
    # mock subprocess.run so the git step always reports "not a repo", and
    # confirm None is returned for a fresh tmp_path with no markers.
    real_run = cap.subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "rev-parse"]:
            class R:
                returncode = 128
                stdout = ""
                stderr = "fatal"
            return R()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(cap.subprocess, "run", fake_run)
    # walk-up will eventually hit / with no markers — should return None
    # but in real test environments the user's home may have CLAUDE.md, so
    # use an isolated fake home
    monkeypatch.setattr(cap.Path, "home", classmethod(lambda c: tmp_path))
    isolated = tmp_path / "isolated_dir"
    isolated.mkdir()
    assert cap.find_project_root(isolated) is None


# ---------- collect_actions ----------

def test_collect_actions_filters_empty():
    class Args:
        actions = ["one", "  ", "two"]
    assert cap.collect_actions(Args()) == ["one", "two"]


# ---------- end-to-end via main() ----------

def test_main_writes_ids_to_stdout(tmp_path: Path, capsys, monkeypatch):
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    # Make detection deterministic: mock git to fail, mock home to tmp_path,
    # add CLAUDE.md so walk-up finds the project
    (project_dir / "CLAUDE.md").write_text("x")
    monkeypatch.setattr(cap.Path, "home", classmethod(lambda c: tmp_path))

    real_run = cap.subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "rev-parse"]:
            class R:
                returncode = 128
                stdout = ""
                stderr = "fatal"
            return R()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(cap.subprocess, "run", fake_run)

    rc = cap.main(["First", "Second"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == "A-001\nA-002\n"
    assert captured.err == ""


def test_main_errors_when_no_project(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cap.Path, "home", classmethod(lambda c: tmp_path))

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "rev-parse"]:
            class R:
                returncode = 128
                stdout = ""
                stderr = "fatal"
            return R()
        raise RuntimeError("unexpected subprocess call")

    monkeypatch.setattr(cap.subprocess, "run", fake_run)
    rc = cap.main(["something"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "no project repo detected" in captured.err


def test_main_project_flag(tmp_path: Path, capsys, monkeypatch):
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    (projects_root / "myproj").mkdir()
    monkeypatch.setattr(cap, "PROJECTS_ROOT", projects_root)
    rc = cap.main(["-p", "myproj", "Hello"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == "A-001"
    assert (projects_root / "myproj" / "ACTIONS.md").exists()
