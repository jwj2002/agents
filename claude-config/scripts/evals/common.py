"""Shared change-set model for the executable evals (#361).

Evals operate on a ChangeSet — the list of changed files plus their added
lines — so unit tests can construct one directly and only the CLI layer
touches git. Precision rule: evals only inspect ADDED lines (this diff's
responsibility), never the whole file, except where the eval is inherently
whole-file (E14 needs the final Dockerfile state).

Inline allowlist: a line containing `eval-ok: <ID>` (e.g. `# eval-ok: E15`)
is skipped by that eval. Use sparingly, with a reason in the surrounding
code.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class DiffError(Exception):
    """git diff could not be read for the requested range."""


@dataclass
class Finding:
    eval_id: str
    path: str
    line: int  # 0 = file-level finding
    message: str

    def render(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.eval_id}] {loc}: {self.message}"


@dataclass
class ChangeSet:
    """Changed paths -> list of (new_lineno, added_line_text)."""

    repo: Path
    added: dict[str, list[tuple[int, str]]] = field(default_factory=dict)

    @property
    def paths(self) -> list[str]:
        return sorted(self.added)

    def added_lines(self, path: str) -> list[tuple[int, str]]:
        return self.added.get(path, [])

    def file_text(self, path: str) -> str | None:
        """Current working-tree content (None if deleted/binary/unreadable)."""
        try:
            return (self.repo / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None


def allowlisted(line: str, eval_id: str) -> bool:
    return f"eval-ok: {eval_id}" in line


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def changeset_from_git(repo: Path, diff_range: str) -> ChangeSet:
    """Build a ChangeSet from `git diff <range>` unified output."""
    try:
        out = subprocess.run(
            ["git", "diff", "--no-color", "--unified=0", diff_range],
            cwd=repo, capture_output=True, text=True, check=True, timeout=60,
        ).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise DiffError(f"git diff {diff_range} failed: {exc}") from exc

    cs = ChangeSet(repo=repo)
    path: str | None = None
    lineno = 0
    for raw in out.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
            cs.added.setdefault(path, [])
        elif raw.startswith("+++ /dev/null"):
            path = None  # deletion — nothing added
        elif raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            if m:
                lineno = int(m.group(1))
        elif path is not None and raw.startswith("+") and not raw.startswith("+++"):
            cs.added[path].append((lineno, raw[1:]))
            lineno += 1
        elif path is not None and not raw.startswith("-"):
            lineno += 1
    # Drop entries with no added lines (pure deletions) — except keep the key
    # so "file changed" evals (E04/E14) still see them.
    return cs
