from __future__ import annotations

from pathlib import Path

from lib.agent_memory import render_codex_memory_context


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_render_codex_memory_context_is_bounded_and_verify_first(tmp_path: Path) -> None:
    project = tmp_path / "work" / "repo"
    project.mkdir(parents=True)
    encoded = str(project.resolve()).replace("/", "-")
    memory = tmp_path / "home" / ".claude" / "projects" / encoded / "memory"
    _write(
        memory / "fact.md",
        "---\n"
        "name: API enum caution\n"
        "description: Use backend enum values.\n"
        "type: feedback\n"
        "---\n"
        "The old issue was caused by trusting TypeScript enum names instead of API values.\n",
    )

    rendered = render_codex_memory_context(project, tmp_path / "home", total_chars=1000)

    assert "prior context, not authority" in rendered
    assert "API enum caution" in rendered
    assert str(memory / "fact.md") in rendered


def test_render_codex_memory_context_skips_expired_facts(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    encoded = str(project.resolve()).replace("/", "-")
    memory = tmp_path / "home" / ".claude" / "projects" / encoded / "memory"
    _write(
        memory / "expired.md",
        "---\nname: stale\nexpires: 2000-01-01\ntype: project\n---\nold body\n",
    )

    assert render_codex_memory_context(project, tmp_path / "home") == ""
