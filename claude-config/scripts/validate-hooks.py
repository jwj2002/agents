#!/usr/bin/env python3
"""
Validate that hook command paths in settings.json reference existing scripts.

For each hook entry under `hooks.<Stage>[*].hooks[*].command`, parse the
command string, identify the interpreted script (if any), and verify the
file exists on disk. Heuristic is intentionally narrow:

  - Skip commands containing `${CLAUDE_PLUGIN_ROOT}` (resolved at runtime by
    the Claude Code plugin loader, not by this checker).
  - Only inspect commands whose first token is a known interpreter
    (`python3`, `python`, `bash`, `sh`, `node`, `npx`).
  - Take the first argument after the interpreter ending in a known script
    extension (`.py`, `.sh`, `.js`); ignore other tokens (data args, flags).

Anything else (raw scripts on PATH, complex pipelines via `bash -c`, etc.)
is intentionally not validated — false-positive risk outweighs the benefit.

Usage:
  validate-hooks.py                       # uses ../settings.json relative to script
  SETTINGS_PATH=/path/to/settings.json validate-hooks.py
  validate-hooks.py /path/to/settings.json   # positional arg also accepted

Exit codes:
  0  all checked hook script paths resolve (or no checkable hooks)
  1  one or more script paths missing, or settings.json unreadable

Run: python3 scripts/validate-hooks.py
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

KNOWN_INTERPRETERS = {"python3", "python", "bash", "sh", "node", "npx"}
SCRIPT_EXTS = (".py", ".sh", ".js")
HOOK_STAGES = (
    "PreCompact",
    "SessionStart",
    "Stop",
    "PostToolUse",
    "PreToolUse",
    "UserPromptSubmit",
    "Notification",
    "SubagentStop",
)


def _resolve_settings_path() -> Path:
    """Resolve settings.json path: argv[1] > $SETTINGS_PATH > ../settings.json."""
    if len(sys.argv) > 1 and sys.argv[1]:
        return Path(sys.argv[1]).expanduser()
    env = os.environ.get("SETTINGS_PATH")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "settings.json"


def _extract_script(cmd: str) -> str | None:
    """Return the first script-extension token after a known interpreter, or None."""
    if not cmd or "${CLAUDE_PLUGIN_ROOT}" in cmd:
        return None
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        # Malformed quoting — fail open (don't flag, don't crash).
        return None
    if not tokens:
        return None
    interpreter = os.path.basename(tokens[0])
    if interpreter not in KNOWN_INTERPRETERS:
        return None
    for tok in tokens[1:]:
        if tok.endswith(SCRIPT_EXTS):
            return tok
    return None


def main() -> int:
    settings_path = _resolve_settings_path()
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"  ✗ settings.json not found at {settings_path}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as e:
        # Fail open with a clear error rather than raising.
        print(f"  ✗ Could not parse {settings_path}: {e}", file=sys.stderr)
        return 1

    hooks_root = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks_root, dict):
        print(f"  ✓ No hooks section in {settings_path.name} — nothing to check")
        return 0

    missing: list[dict] = []
    checked = 0

    for stage in HOOK_STAGES:
        entries = hooks_root.get(stage, [])
        if not isinstance(entries, list):
            continue
        for entry_idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            for hook_idx, hook in enumerate(entry.get("hooks", []) or []):
                if not isinstance(hook, dict):
                    continue
                cmd = hook.get("command", "")
                if not isinstance(cmd, str):
                    continue
                script = _extract_script(cmd)
                if script is None:
                    continue
                checked += 1
                resolved = Path(os.path.expanduser(script))
                if not resolved.is_file():
                    missing.append(
                        {
                            "stage": stage,
                            "location": (
                                f"hooks.{stage}[{entry_idx}]"
                                f".hooks[{hook_idx}].command"
                            ),
                            "command": cmd,
                            "script": script,
                            "resolved": str(resolved),
                        }
                    )

    if missing:
        print("  ✗ Hook script paths missing:", file=sys.stderr)
        for m in missing:
            print(f"    {m['location']}", file=sys.stderr)
            print(f"      command:  {m['command']}", file=sys.stderr)
            print(
                f"      script:   {m['script']}  →  {m['resolved']} (not found)",
                file=sys.stderr,
            )
        return 1

    print(f"  ✓ All hook script paths resolve ({checked} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
