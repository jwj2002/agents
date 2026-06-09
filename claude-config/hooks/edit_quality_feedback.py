#!/usr/bin/env python3
"""
PostToolUse hook: edit-time quality feedback.

Fires after Edit, Write, and MultiEdit on *.py files. Runs:
  1. ruff check --no-fix on the edited file path
  2. E15 secrets regex on the added/new content only

Findings are printed to stdout so Claude Code surfaces them as inline
feedback. The hook is non-blocking — always exits 0. Any internal error
is silently swallowed (fail-open by design; BLE001 already ignored for
hooks/ in ruff.toml).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

_WATCHED_TOOLS = {"Edit", "Write", "MultiEdit"}

# Ruff concise-format finding lines look like: path:line:col: CODE message
_RUFF_FINDING_RE = re.compile(r".+:\d+:\d+: [A-Z]\d+")


def _ruff_check(file_path: str) -> list[str]:
    """Return ruff finding lines for file_path, or [] on any failure."""
    if shutil.which("ruff") is None:
        return []
    try:
        result = subprocess.run(
            ["ruff", "check", "--no-fix", "--output-format=concise", file_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        # Only keep lines that match path:line:col: CODE format — filter
        # out summary lines ("All checks passed!", "Found N error(s).", etc.)
        return [
            f"[ruff] {ln}"
            for ln in lines
            if _RUFF_FINDING_RE.match(ln)
        ]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _e15_check(content: str, file_path: str) -> list[str]:
    """Return E15 finding lines for the added content, or [] on any failure."""
    scripts_str = str(_SCRIPTS_DIR)
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)

    try:
        from evals.e15_secrets import (  # type: ignore[import]
            _ASSIGN_RE,
            _ENV_LOOKUP_RE,
            _PLACEHOLDER_RE,
            _TOKEN_RES,
        )
        from evals.common import allowlisted  # type: ignore[import]
    except ImportError:
        return []

    findings: list[str] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        if allowlisted(line, "E15"):
            continue
        matched = False
        for rx in _TOKEN_RES:
            if rx.search(line):
                findings.append(
                    f"[E15] {file_path}:{lineno}: "
                    "high-confidence credential pattern in added content"
                )
                matched = True
                break
        if not matched:
            m = _ASSIGN_RE.search(line)
            if m and not _PLACEHOLDER_RE.search(line) and not _ENV_LOOKUP_RE.search(line):
                findings.append(
                    f"[E15] {file_path}:{lineno}: "
                    f"hardcoded {m.group(1)} literal — load from env/config instead"
                )
    return findings


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        tool_name = payload.get("tool_name", "")
        if tool_name not in _WATCHED_TOOLS:
            sys.exit(0)

        tool_input = payload.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path.endswith(".py"):
            sys.exit(0)

        # Extract added content for E15 scan
        if tool_name == "Edit":
            added_content = tool_input.get("new_string", "")
        elif tool_name == "Write":
            added_content = tool_input.get("content", "")
        else:  # MultiEdit
            edits = tool_input.get("edits", [])
            added_content = "\n".join(e.get("new_string", "") for e in edits)

        ruff_findings = _ruff_check(file_path)
        e15_findings = _e15_check(added_content, file_path)

        all_findings = ruff_findings + e15_findings
        if all_findings:
            count = len(all_findings)
            print(f"[edit_quality_feedback] {count} finding(s) in {file_path}:")
            for finding in all_findings:
                print(f"  {finding}")

    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
