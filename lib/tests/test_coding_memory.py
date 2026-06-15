"""Pure-function tests for coding_memory.parse (no DB / no model needed)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lib/ on path

from coding_memory import parse as P  # noqa: E402


def test_parse_full_frontmatter():
    raw = (
        "---\n"
        "name: codex-always-inline\n"
        "type: feedback\n"
        "summary: Run codex inline only.\n"
        "durability: durable\n"
        "expires: 2026-12-31\n"
        "---\n"
        "Body line one.\n\nBody line two.\n"
    )
    out = P.parse_markdown(raw, fallback_name="fallback")
    assert out["name"] == "codex-always-inline"
    assert out["type"] == "feedback"
    assert out["summary"] == "Run codex inline only."
    assert out["durability"] == "durable"
    assert out["expires"] == "2026-12-31"
    assert out["body"].startswith("Body line one.")
    assert "Body line two." in out["body"]


def test_parse_nested_metadata():
    raw = "---\nname: x\nmetadata:\n  type: reference\n---\nhello\n"
    out = P.parse_markdown(raw, fallback_name="x")
    assert out["type"] == "reference"


def test_parse_no_frontmatter_uses_fallback():
    out = P.parse_markdown("just a body, no frontmatter", fallback_name="my-file")
    assert out["name"] == "my-file"
    assert out["type"] is None
    assert out["body"] == "just a body, no frontmatter"


def test_description_aliases_summary():
    raw = "---\nname: x\ndescription: one liner\n---\nbody\n"
    assert P.parse_markdown(raw)["summary"] == "one liner"


def test_content_hash_changes_with_content():
    a = P.content_hash("alpha")
    b = P.content_hash("beta")
    assert a != b
    assert P.content_hash("alpha") == a  # stable
    assert len(a) == 64


def test_embed_text_composition():
    rec = {"name": "N", "summary": "S", "body": "B"}
    assert P.embed_text(rec) == "N. S. B"
    assert P.embed_text({"name": "", "summary": None, "body": "B"}) == "B"
