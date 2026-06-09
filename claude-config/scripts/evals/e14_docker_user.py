"""E14 DOCKER_ROOT_USER — a changed Dockerfile whose final state has no
USER directive (or whose last USER is root).

Whole-file eval: the failure mode is the final image state, so the check
reads the working-tree file, not just added lines.
"""

from __future__ import annotations

import re

from .common import ChangeSet, Finding, allowlisted

EVAL_ID = "E14"

_DOCKERFILE_RE = re.compile(r"(^|/)(Dockerfile[^/]*|.*\.dockerfile)$", re.IGNORECASE)
_USER_RE = re.compile(r"^\s*USER\s+(\S+)", re.IGNORECASE | re.MULTILINE)


def run(cs: ChangeSet) -> list[Finding]:
    findings: list[Finding] = []
    for path in cs.paths:
        if not _DOCKERFILE_RE.search(path):
            continue
        text = cs.file_text(path)
        if text is None:
            continue  # deleted Dockerfile — nothing to enforce
        if any(allowlisted(line, EVAL_ID) for line in text.splitlines()):
            continue
        users = _USER_RE.findall(text)
        if not users:
            findings.append(Finding(
                EVAL_ID, path, 0,
                "no USER directive — container runs as root",
            ))
        elif users[-1] in ("root", "0"):
            findings.append(Finding(
                EVAL_ID, path, 0,
                f"final USER is {users[-1]!r} — container runs as root",
            ))
    return findings
