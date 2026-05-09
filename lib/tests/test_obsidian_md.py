"""Tests for lib/obsidian_md.py — frontmatter read/write + section helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import obsidian_md as md


# ---------- parse ----------

def test_parse_basic_frontmatter_and_body():
    text = "---\nproject: foo\nstatus: active\n---\n\n# Hello\n\nbody text\n"
    fm, body = md.parse(text)
    assert fm == {"project": "foo", "status": "active"}
    assert body == "# Hello\n\nbody text\n"


def test_parse_empty_body():
    text = "---\nproject: foo\n---\n"
    fm, body = md.parse(text)
    assert fm == {"project": "foo"}
    assert body == ""


def test_parse_no_frontmatter_returns_body_only():
    text = "# just a heading\n"
    fm, body = md.parse(text)
    assert fm == {}
    assert body == text


def test_parse_unterminated_frontmatter_errors():
    with pytest.raises(md.ObsidianMdError, match="not terminated"):
        md.parse("---\nproject: foo\n# never closes\n")


def test_parse_non_mapping_frontmatter_errors():
    with pytest.raises(md.ObsidianMdError, match="must be a mapping"):
        md.parse("---\n- list\n- not\n- mapping\n---\n")


def test_parse_handles_lists_and_nested_maps():
    text = (
        "---\n"
        "project: foo\n"
        "tags:\n  - a\n  - b\n"
        "linked:\n  patterns: []\n  issues: [1, 2]\n"
        "---\n\nbody\n"
    )
    fm, _ = md.parse(text)
    assert fm["tags"] == ["a", "b"]
    assert fm["linked"]["issues"] == [1, 2]


# ---------- dump ----------

def test_dump_roundtrip():
    fm = {"project": "foo", "status": "active", "tags": ["a", "b"]}
    body = "# Hello\n\nbody text\n"
    text = md.dump(fm, body)
    fm2, body2 = md.parse(text)
    assert fm2 == fm
    assert body2 == body


def test_dump_field_order_applied_first():
    fm = {"focus": "x", "project": "p", "status": "active"}
    text = md.dump(fm, "", field_order=["project", "status"])
    # project must precede status, which must precede focus
    assert text.index("project:") < text.index("status:")
    assert text.index("status:") < text.index("focus:")


def test_dump_unknown_keys_keep_relative_order():
    fm = {"project": "p", "x": 1, "y": 2}
    text = md.dump(fm, "", field_order=["project"])
    assert text.index("x:") < text.index("y:")


def test_dump_empty_body():
    text = md.dump({"project": "p"}, "")
    assert text.startswith("---\n")
    assert text.endswith("---\n")
    assert "\n\n" not in text.split("---\n", 2)[2]  # no trailing blank padding


# ---------- file I/O ----------

def test_write_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "note.md"
    fm = {"project": "foo", "status": "active"}
    body = "# Heading\n\nsome body text\n"
    md.write(path, fm, body)
    fm2, body2 = md.load(path)
    assert fm2 == fm
    assert body2 == body


def test_write_field_order_preserved(tmp_path: Path):
    path = tmp_path / "note.md"
    md.write(
        path,
        {"focus": "x", "project": "p", "status": "active"},
        "",
        field_order=["project", "status", "focus"],
    )
    text = path.read_text()
    assert text.index("project:") < text.index("status:")
    assert text.index("status:") < text.index("focus:")


def test_load_missing_file_errors(tmp_path: Path):
    with pytest.raises(md.ObsidianMdError, match="not found"):
        md.load(tmp_path / "missing.md")


def test_write_atomic_does_not_leave_tmp_on_success(tmp_path: Path):
    path = tmp_path / "note.md"
    md.write(path, {"a": 1}, "body\n")
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_write_atomic_overwrites_existing(tmp_path: Path):
    path = tmp_path / "note.md"
    md.write(path, {"v": 1}, "first\n")
    md.write(path, {"v": 2}, "second\n")
    fm, body = md.load(path)
    assert fm == {"v": 2}
    assert body == "second\n"


# ---------- section helpers ----------

_BODY = """\
# Title

## Context
context paragraph

## Decision
decision paragraph
multi-line

## Outcome

"""


def test_get_section_returns_content():
    assert md.get_section(_BODY, "Context") == "context paragraph"
    assert md.get_section(_BODY, "Decision") == "decision paragraph\nmulti-line"


def test_get_section_returns_empty_for_blank_section():
    assert md.get_section(_BODY, "Outcome") == ""


def test_get_section_missing_raises():
    with pytest.raises(md.ObsidianMdError, match="not found"):
        md.get_section(_BODY, "Nope")


def test_replace_section_updates_only_target():
    new = md.replace_section(_BODY, "Decision", "new decision text")
    assert "## Decision\nnew decision text\n\n" in new
    # Other sections preserved
    assert "## Context\ncontext paragraph" in new
    assert new.endswith("## Outcome\n\n")


def test_replace_section_then_get_roundtrip():
    new = md.replace_section(_BODY, "Outcome", "outcome content here")
    assert md.get_section(new, "Outcome") == "outcome content here"


def test_replace_section_missing_raises():
    with pytest.raises(md.ObsidianMdError, match="not found"):
        md.replace_section(_BODY, "Reasoning", "x")


def test_has_section():
    assert md.has_section(_BODY, "Context") is True
    assert md.has_section(_BODY, "Reasoning") is False


def test_replace_section_preserves_following_section():
    """Critical invariant: replacing one section must not corrupt the next."""
    body = "## A\nA-content\n\n## B\nB-content\n\n## C\nC-content\n"
    new = md.replace_section(body, "B", "new-B")
    assert "## A\nA-content" in new
    assert "## B\nnew-B" in new
    assert "## C\nC-content" in new
