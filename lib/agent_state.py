"""Compact checkpoint helpers for Codex hooks."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.agent_completion import run

ISSUE_RE = re.compile(r"(?:#|issue[-/ ]?)(\d+)", re.IGNORECASE)


def current_branch(cwd: Path) -> str | None:
    result = run(["git", "branch", "--show-current"], cwd, timeout=3)
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout


def issue_refs_from_payload(payload: dict[str, Any]) -> list[int]:
    refs: set[int] = set()
    for value in _walk_values(payload):
        if not isinstance(value, str):
            continue
        for match in ISSUE_RE.finditer(value):
            refs.add(int(match.group(1)))
    return sorted(refs)


def _walk_values(value: object) -> list[object]:
    if isinstance(value, dict):
        out: list[object] = []
        for child in value.values():
            out.extend(_walk_values(child))
        return out
    if isinstance(value, list):
        out = []
        for child in value:
            out.extend(_walk_values(child))
        return out
    return [value]


def write_codex_checkpoint(
    project_dir: Path,
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> Path:
    now = now or datetime.now(UTC)
    out_dir = project_dir / ".agents" / "outputs" / "codex_checkpoints"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "PERSISTENT_STATE.yaml"

    branch = current_branch(project_dir)
    refs = issue_refs_from_payload(payload)
    session_id = str(payload.get("session_id") or payload.get("thread_id") or "unknown")
    trigger = str(payload.get("trigger") or payload.get("matcher") or payload.get("event") or "unknown")
    lines = [
        "# Codex persistent state",
        f"updated_at: {now.isoformat()}",
        f"project_dir: {project_dir}",
        f"session_id: {session_id}",
        f"trigger: {trigger}",
        f"branch: {branch or ''}",
        "issue_refs:",
    ]
    if refs:
        lines.extend(f"  - {ref}" for ref in refs)
    else:
        lines.append("  []")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
