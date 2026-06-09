"""E04 MODEL_WITHOUT_MIGRATION — a SQLAlchemy model file changed schema
(Column/relationship/table changes) but the diff adds no Alembic migration.

Precision strategy: only fires when an added line in a models file actually
touches schema surface (Column(, ForeignKey(, __tablename__, relationship(,
Index(, UniqueConstraint() — renaming a helper method in a models file does
not fire. Any added file under a migrations/versions directory clears it.
"""

from __future__ import annotations

import re

from .common import ChangeSet, Finding, allowlisted

EVAL_ID = "E04"

_MODEL_PATH_RE = re.compile(r"(^|/)models?(/|\.py$)")
_MIGRATION_PATH_RE = re.compile(r"(^|/)(alembic|migrations)/(versions/)?.+\.(py|sql)$")
_SCHEMA_TOUCH_RE = re.compile(
    r"\b(Column|mapped_column|ForeignKey|relationship|Index|UniqueConstraint)\s*\("
    r"|__tablename__"
)


def run(cs: ChangeSet) -> list[Finding]:
    schema_touches: list[tuple[str, int, str]] = []
    has_migration = False
    for path in cs.paths:
        if _MIGRATION_PATH_RE.search(path):
            has_migration = True
            continue
        if _MODEL_PATH_RE.search(path) and path.endswith(".py"):
            for lineno, line in cs.added_lines(path):
                if allowlisted(line, EVAL_ID):
                    continue
                if _SCHEMA_TOUCH_RE.search(line):
                    schema_touches.append((path, lineno, line.strip()))

    if not schema_touches or has_migration:
        return []
    findings = [
        Finding(EVAL_ID, path, lineno,
                f"schema change ({snippet[:60]!r}) but the diff adds no "
                "alembic/migrations file")
        for path, lineno, snippet in schema_touches[:5]  # cap noise per diff
    ]
    return findings
