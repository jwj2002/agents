#!/usr/bin/env python3
"""
PreToolUse hook: block access to secrets and env files.

Layered with permissions.deny in settings.json. Permissions.deny covers
Read/Edit/Write tool calls. This hook covers Bash commands that could
exfiltrate secrets (cat .env, grep KEY .env, sed/awk on key files).

Exit code 2 blocks the tool call. Exit code 0 allows.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

_log_file = Path.home() / ".claude" / "hooks.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_log_file),
    level=logging.WARNING,
    format="%(asctime)s [secret_guard] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Sensitive token patterns. Match against individual path tokens.
SENSITIVE_TOKEN_PATTERNS = [
    re.compile(r"(?:^|/)\.env(?:\.[\w-]+)?$"),  # .env, .env.local, .env.production
    re.compile(r"(?:^|/)secrets(?:/|$)"),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"(?:^|/)id_rsa(?:\.pub)?$"),
    re.compile(r"(?:^|/)id_ed25519(?:\.pub)?$"),
    re.compile(r"\.git-credentials$"),
    re.compile(r"\.pgpass$"),
    re.compile(r"\.netrc$"),
]

TOKEN_SPLIT = re.compile(r"[\s;&|<>()`'\"$]+")


def path_is_sensitive(path: str) -> bool:
    """Check if a single path string matches any sensitive pattern."""
    return any(p.search(path) for p in SENSITIVE_TOKEN_PATTERNS)


def bash_command_touches_secret(command: str) -> tuple[bool, str]:
    """Tokenize a Bash command and check each token."""
    for token in TOKEN_SPLIT.split(command):
        if not token:
            continue
        # Strip leading flags like --foo=
        if "=" in token:
            token = token.split("=", 1)[1]
        if path_is_sensitive(token):
            return True, f"command references sensitive path '{token}': {command[:120]}"
    return False, ""


def deny(reason: str) -> None:
    """Block the tool call with a reason. Anthropic spec: exit 2 + stderr."""
    logging.warning("BLOCKED: %s", reason)
    sys.stderr.write(
        f"[secret_guard] Blocked: {reason}\n"
        f"If you genuinely need this access, use environment variables, "
        f"a secrets manager, or temporarily disable the hook.\n"
    )
    sys.exit(2)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        logging.warning("could not parse stdin JSON: %s", e)
        return 0  # Don't block on parse errors

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = (
            tool_input.get("file_path")
            or tool_input.get("notebook_path")
            or ""
        )
        if path and path_is_sensitive(path):
            deny(f"{tool_name} on sensitive path: {path}")

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        blocked, reason = bash_command_touches_secret(command)
        if blocked:
            deny(reason)

    return 0


if __name__ == "__main__":
    sys.exit(main())
