"""E13 MISSING_FK_INDEX — an added ForeignKey column without index=True.

Precision strategy: fires only on added lines that declare a Column/
mapped_column containing ForeignKey( and no index= / primary_key= /
unique= on the same statement line (PKs and unique columns are indexed
implicitly). Multi-line column definitions are joined within the added
hunk before matching.
"""

from __future__ import annotations

import re

from .common import ChangeSet, Finding, allowlisted

EVAL_ID = "E13"

_COL_START_RE = re.compile(r"\b(Column|mapped_column)\s*\(")


def _statements(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join consecutive added lines into paren-balanced statements."""
    out: list[tuple[int, str]] = []
    buf = ""
    start = 0
    depth = 0
    prev_no = None
    for lineno, line in lines:
        if buf and prev_no is not None and lineno != prev_no + 1:
            out.append((start, buf))  # hunk break — flush
            buf, depth = "", 0
        if not buf:
            start = lineno
        buf += line + " "
        depth += line.count("(") - line.count(")")
        prev_no = lineno
        if depth <= 0:
            out.append((start, buf))
            buf, depth = "", 0
    if buf:
        out.append((start, buf))
    return out


def run(cs: ChangeSet) -> list[Finding]:
    findings: list[Finding] = []
    for path in cs.paths:
        if not path.endswith(".py"):
            continue
        for lineno, stmt in _statements(cs.added_lines(path)):
            if allowlisted(stmt, EVAL_ID):
                continue
            if (_COL_START_RE.search(stmt) and "ForeignKey(" in stmt
                    and "index=" not in stmt
                    and "primary_key=" not in stmt
                    and "unique=" not in stmt):
                findings.append(Finding(
                    EVAL_ID, path, lineno,
                    "ForeignKey column without index=True — FK lookups and "
                    "joins will table-scan",
                ))
    return findings
