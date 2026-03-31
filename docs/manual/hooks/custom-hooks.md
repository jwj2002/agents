# Writing Custom Hooks

Hooks are Python scripts (or any executable) that run at specific moments in a Claude Code session. They let you inject context, persist state, enforce quality gates, and trigger external integrations.

## Available Events

| Event | When It Fires | stdin Receives | stdout Goes To |
|-------|--------------|----------------|----------------|
| `SessionStart` | New session begins | `{"session_id": "..."}` | Injected into agent context |
| `PreCompact` | Before context compression | `{"transcript_path": "...", "session_id": "...", "trigger": "..."}` | Logged only (not injected) |
| `Stop` | Agent stops responding | `{}` | Injected into agent context |
| `PreToolUse` | Before a tool call executes | Tool call details | Injected into agent context |
| `PostToolUse` | After a tool call completes | Tool call result | Injected into agent context |

!!! note "stdout Injection"
    Only SessionStart, Stop, PreToolUse, and PostToolUse output is injected into the agent's context. PreCompact stdout is logged but not visible to the agent. This means PreCompact hooks can be verbose for debugging without consuming context tokens.

## Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success / allow the operation to proceed |
| 2 | Block the operation and send stdout as feedback |

!!! warning "Exit Code 2 on Stop"
    Using exit code 2 on a Stop hook means the agent receives your stdout as feedback and continues working. Use this carefully to avoid infinite loops. The built-in `verify_completion.py` intentionally uses exit 0 (advisory only) rather than exit 2 (blocking) to prevent feedback loops.

## settings.json Configuration

Hooks are configured in `settings.json` (or `settings.local.json` for machine-specific hooks):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/my_hook.py"
          }
        ]
      }
    ]
  }
}
```

The `matcher` field filters which events trigger the hook. An empty string `""` matches all events of that type. For `PreToolUse` and `PostToolUse`, you can match specific tools:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/audit_bash.py"
          }
        ]
      }
    ]
  }
}
```

Multiple hooks on the same event run sequentially in the order they appear.

## Design Principles

!!! tip "Four principles for reliable hooks"
    1. **Fail gracefully** -- wrap external imports and degrade, never crash
    2. **Log to file** -- hooks run silently; without file logging, failures are invisible
    3. **Keep output compact** -- stdout goes into context; every line costs tokens
    4. **Auto-clean old data** -- checkpoint files accumulate; include a retention cleanup

### Fail Gracefully

If your hook depends on an external package (like PyYAML), wrap the import and degrade rather than crash:

```python
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

def load_config():
    if not HAS_YAML:
        return {}  # Graceful degradation
    # ... normal logic
```

A crashing hook can break every session. A gracefully degrading hook just provides less functionality.

### Log to File

Hooks run silently. Without file-based logging, failures are invisible:

```python
import logging
from pathlib import Path

log_file = Path.home() / ".claude" / "hooks.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.WARNING,
    format="%(asctime)s [my_hook] %(levelname)s: %(message)s",
)
```

### Keep Output Compact

SessionStart and Stop hook output goes directly into the agent's context window. Every line costs tokens that could have been used for code context. Aim for the minimum viable context restoration.

```python
# Bad: dumping 200 lines of state
print(full_state_dump)

# Good: 5 lines of essential context
print(f"Issue: #{issue}")
print(f"Phase: {phase}")
print(f"Branch: {branch}")
```

### Auto-Clean Old Data

If your hook writes checkpoint files, include a cleanup routine:

```python
from datetime import datetime

RETENTION_DAYS = 7

def cleanup(directory: Path):
    cutoff = datetime.now().timestamp() - (RETENTION_DAYS * 86400)
    for f in directory.iterdir():
        if f.stat().st_mtime < cutoff:
            f.unlink()
```

## Example: Simple SessionStart Hook

A minimal hook that prints the current git branch and last commit:

```python
#!/usr/bin/env python3
"""Print current git context at session start."""

import json
import subprocess
import sys


def run(cmd: str) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def main() -> int:
    # Read hook input (required even if unused)
    _hook_input = json.load(sys.stdin)

    branch = run("git branch --show-current")
    last_commit = run("git log --oneline -1")

    print("## Git Context\n")
    print(f"- **Branch**: {branch}")
    print(f"- **Last commit**: {last_commit}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Register it in `settings.json` under the `SessionStart` event with an empty `matcher` to run on every session start.

!!! warning "Common mistakes"
    - **Forgetting to read stdin** -- hooks receive JSON on stdin even if unused; not reading it can cause the hook to hang
    - **Printing too much** -- SessionStart output goes directly into context; dumping 200 lines of state wastes tokens
    - **Using exit code 2 on Stop** -- this sends feedback and resumes the agent, which can cause infinite loops
    - **Missing error handling on subprocess calls** -- a failed `git` or `osascript` call should not crash the hook

## Testing Hooks

Test hooks by piping sample JSON input through stdin:

```bash
# Test a SessionStart hook
echo '{"session_id": "test-123"}' | python3 ~/.claude/hooks/my_hook.py
echo $?  # Check exit code

# Test a PreCompact hook
echo '{"transcript_path": "/tmp/test.jsonl", "session_id": "test", "trigger": "manual"}' \
  | python3 ~/.claude/hooks/precompact_checkpoint.py

# Check for logged errors
tail -20 ~/.claude/hooks.log
```
