"""E01 ENUM_VALUE_MISMATCH — frontend uses a backend enum NAME whose VALUE
differs (`CO_OWNER` instead of `"CO-OWNER"`). 26% of historical fullstack
failures.

Precision strategy: parse backend enums (``NAME = "VALUE"`` members inside
``class X(...Enum)`` blocks), keep only members where NAME != VALUE — those
are the only ones that can be misused — then flag added frontend lines that
contain the NAME as a quoted string literal. Identifier usage (e.g. a local
JS constant that happens to share the name) is NOT flagged; only the quoted
literal reaching an API payload/comparison is the failure mode.
"""

from __future__ import annotations

import re
from pathlib import Path

from .common import ChangeSet, Finding, allowlisted

EVAL_ID = "E01"
FRONTEND_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte")

_CLASS_RE = re.compile(r"^class\s+\w+\([^)]*Enum[^)]*\)\s*:")
_MEMBER_RE = re.compile(r"^\s+([A-Z][A-Z0-9_]*)\s*=\s*([\"'])(.*?)\2\s*(?:#.*)?$")


def backend_enum_mismatches(repo: Path) -> dict[str, str]:
    """Scan backend python for enum members whose NAME != VALUE.

    Returns {NAME: VALUE}. Names mapping to multiple values keep the first —
    any quoted use of such a NAME is suspect regardless.
    """
    mismatches: dict[str, str] = {}
    roots = [p for p in (repo / "backend", repo / "app", repo / "src") if p.is_dir()]
    if not roots:
        roots = [repo]
    for root in roots:
        for py in root.rglob("*.py"):
            if any(part in (".venv", "node_modules", "_archived") for part in py.parts):
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "Enum" not in text:
                continue
            in_enum = False
            for line in text.splitlines():
                if _CLASS_RE.match(line):
                    in_enum = True
                    continue
                if in_enum and line and not line[0].isspace():
                    in_enum = False
                if in_enum:
                    m = _MEMBER_RE.match(line)
                    if m and m.group(1) != m.group(3):
                        mismatches.setdefault(m.group(1), m.group(3))
    return mismatches


def run(cs: ChangeSet) -> list[Finding]:
    frontend_paths = [p for p in cs.paths if p.endswith(FRONTEND_SUFFIXES)]
    if not frontend_paths:
        return []
    mismatches = backend_enum_mismatches(cs.repo)
    if not mismatches:
        return []

    findings: list[Finding] = []
    for path in frontend_paths:
        for lineno, line in cs.added_lines(path):
            if allowlisted(line, EVAL_ID):
                continue
            for name, value in mismatches.items():
                if re.search(rf"[\"'`]{re.escape(name)}[\"'`]", line):
                    findings.append(Finding(
                        EVAL_ID, path, lineno,
                        f'uses enum NAME "{name}" as a string literal — the '
                        f'backend VALUE is "{value}". Use the VALUE.',
                    ))
    return findings
