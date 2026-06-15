"""Pure-function tests for coding_memory.parse (no DB / no model needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lib/ on path

from coding_memory import cli as C  # noqa: E402
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


def test_build_records_clean_dir_is_prune_safe(tmp_path):
    d = tmp_path / "ns1"
    d.mkdir()
    (d / "a.md").write_text("---\nname: a\n---\nbody a\n")
    (d / "MEMORY.md").write_text("index")  # skipped, not a fact
    out = P.build_records({"ns1": str(d)})
    assert len(out["records"]) == 1
    assert out["prune_namespaces"] == ["ns1"]


def test_build_records_missing_root_not_prunable(tmp_path):
    out = P.build_records({"gone": str(tmp_path / "nope")})
    assert out["records"] == []
    assert out["prune_namespaces"] == []  # missing source must never trigger prune


def test_build_records_empty_dir_not_prunable(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    out = P.build_records({"empty": str(d)})
    assert out["records"] == []
    assert "empty" not in out["prune_namespaces"]  # empty must not wipe existing rows


def test_residency_rejects_unknown_namespace():
    with pytest.raises(SystemExit):
        C._sources_from_args(["work=~/.claude/projects/some-work-repo/memory"])


def test_residency_rejects_path_outside_namespace_root(tmp_path):
    # personal namespace label but a work/other path must be refused (the bridge bug)
    with pytest.raises(SystemExit):
        C._sources_from_args([f"agents={tmp_path}"])


def test_residency_defaults_pass():
    out = C._sources_from_args(None)
    assert set(out) == {"agents", "buddy", "global"}


def test_global_record_uses_shared_origin():
    # git-synced global facts get a fixed origin so they dedupe across machines
    rec = P._record("global", "/x/agents/memory/global/foo.md", "---\nname: f\n---\nb")
    assert rec["origin"] == "shared"


def test_project_record_uses_hostname_origin():
    rec = P._record("agents", "/x/.claude/projects/p/memory/foo.md", "body")
    assert rec["origin"] == P.current_origin()


def test_embed_service_disabled_returns_none(monkeypatch):
    from coding_memory import embedder as E

    monkeypatch.delenv("CODING_MEMORY_EMBED_URL", raising=False)
    assert E._try_service(["x"], "doc") is None  # no URL -> caller falls back to local


def test_embed_service_unreachable_returns_none(monkeypatch):
    from coding_memory import embedder as E

    # pointed at a dead port -> _try_service swallows the error and returns None
    monkeypatch.setenv("CODING_MEMORY_EMBED_URL", "http://127.0.0.1:1")
    assert E._try_service(["x"], "doc") is None


def test_prompt_block_empty_is_blank():
    assert C._prompt_block([]) == ""  # fail-open: nothing relevant -> inject nothing


def test_prompt_block_is_bounded():
    rows = [
        {"namespace": "global", "name": f"n{i}", "summary": "x" * 200}
        for i in range(10)
    ]
    block = C._prompt_block(rows, max_chars=300)
    assert block.startswith("## Recalled coding-memory")
    assert len(block) <= 300  # hard cap so it can't bloat a phase prompt


def test_embed_service_non_loopback_refused(monkeypatch):
    from coding_memory import embedder as E

    # residency: a non-loopback URL must never receive fact text -> fall back local
    monkeypatch.setenv("CODING_MEMORY_EMBED_URL", "http://example.com:8788")
    assert E._try_service(["x"], "doc") is None
