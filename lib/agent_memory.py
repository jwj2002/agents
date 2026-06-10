"""Bounded Codex memory rendering from the shared Claude memory store."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
INDEX_NAME = "MEMORY.md"
TYPE_PRIORITY = {"feedback": 0, "user": 1, "reference": 2, "project": 3}


@dataclass(frozen=True)
class MemoryFact:
    path: Path
    project: str
    meta: dict[str, str]
    body: str
    mtime: float


def encoded_project_path(project_dir: Path) -> str:
    return str(project_dir.resolve()).replace("/", "-")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    meta = {"name": "", "description": "", "type": "", "expires": ""}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end == -1:
        return meta, text
    frontmatter = text[3:end]
    body = text[end + 4 :].lstrip("\n")
    for line in frontmatter.splitlines():
        stripped = line.strip().strip("'\"")
        for key in meta:
            if stripped.startswith(f"{key}:") and not meta[key]:
                meta[key] = stripped[len(key) + 1 :].strip().strip("'\"")
    return meta, body


def _is_expired(meta: dict[str, str], today: dt.date) -> bool:
    raw = (meta.get("expires") or "").strip()
    if not raw:
        return False
    try:
        return dt.date.fromisoformat(raw) < today
    except ValueError:
        return False


def _memory_dirs(project_dir: Path, home: Path) -> list[Path]:
    encoded = encoded_project_path(project_dir)
    candidates = [home / ".claude" / "projects" / encoded / "memory"]
    projects_root = home / ".claude" / "projects"
    if projects_root.is_dir():
        for path in sorted(projects_root.glob("*/memory")):
            if path not in candidates and path.is_dir():
                candidates.append(path)
    return [path for path in candidates if path.is_dir()]


def _project_label(memory_dir: Path) -> str:
    name = memory_dir.parent.name
    return name.lstrip("-") or name


def _query_terms(project_dir: Path) -> set[str]:
    terms = {project_dir.name.lower()}
    for part in project_dir.parts[-3:]:
        for token in re.split(r"[^A-Za-z0-9]+", part.lower()):
            if len(token) >= 3:
                terms.add(token)
    return terms


def _score(fact: MemoryFact, terms: set[str]) -> tuple[int, int, float]:
    searchable = " ".join(
        [
            fact.meta.get("name", ""),
            fact.meta.get("description", ""),
            fact.body[:2000],
        ]
    ).lower()
    relevance = sum(searchable.count(term) for term in terms)
    priority = TYPE_PRIORITY.get(fact.meta.get("type", ""), 9)
    return (relevance, -priority, fact.mtime)


def load_relevant_facts(project_dir: Path, home: Path, limit: int = 8) -> list[MemoryFact]:
    today = dt.date.today()
    facts: list[MemoryFact] = []
    for memory_dir in _memory_dirs(project_dir, home):
        for path in sorted(memory_dir.glob("*.md")):
            if path.name == INDEX_NAME:
                continue
            try:
                text = path.read_text(encoding="utf-8")
                mtime = path.stat().st_mtime
            except OSError:
                continue
            meta, body = split_frontmatter(text)
            if _is_expired(meta, today):
                continue
            facts.append(
                MemoryFact(
                    path=path,
                    project=_project_label(memory_dir),
                    meta=meta,
                    body=body,
                    mtime=mtime,
                )
            )

    terms = _query_terms(project_dir)
    facts.sort(key=lambda fact: _score(fact, terms), reverse=True)
    return facts[:limit]


def render_codex_memory_context(
    project_dir: Path,
    home: Path | None = None,
    *,
    total_chars: int = 6000,
    per_fact_chars: int = 700,
    limit: int = 8,
) -> str:
    """Render bounded memory notes for Codex SessionStart.

    Memory is treated as prior context only. The caller should inject this text
    as advisory context, never as an instruction override.
    """
    home = home or Path.home()
    facts = load_relevant_facts(project_dir, home, limit=limit)
    if not facts:
        return ""

    lines = [
        "## Prior Memory Context",
        "",
        "These facts are prior context, not authority. Verify against current code, specs, and tests before acting.",
    ]
    remaining = total_chars - sum(len(line) + 1 for line in lines)
    for fact in facts:
        title = fact.meta.get("name") or fact.path.stem
        description = fact.meta.get("description")
        fact_type = fact.meta.get("type") or "uncategorized"
        body = " ".join(fact.body.split())[:per_fact_chars]
        entry = [
            "",
            f"- `{fact.path}` [{fact.project} · {fact_type}] {title}",
        ]
        if description:
            entry.append(f"  - {description}")
        if body:
            entry.append(f"  - {body}")
        rendered = "\n".join(entry)
        if len(rendered) > remaining:
            break
        lines.append(rendered)
        remaining -= len(rendered)
    return "\n".join(lines).strip()
