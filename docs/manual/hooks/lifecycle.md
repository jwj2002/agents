# Hook Lifecycle

Claude Code hooks fire at specific moments during a session. Five hooks turn stateless chat sessions into stateful development workflows by persisting context across compactions, monitoring context usage, verifying completion quality, and sending notifications.

## Hook Execution Order

```
+-- SessionStart ------------------------------------------------+
|  sessionstart_restore_state.py                                  |
|  +-- state_manager.get_active_work() -> restore active context  |
|  +-- Load patterns (project -> global -> core-patterns.md)      |
|  +-- Output ~500 tokens of restored context                     |
+-----------------------------------------------------------------+
                          |
                    [Session Work]
                          |
+-- PostToolUse (after each tool call) ------------------------+
|  context_monitor.py                                          |
|  +-- Check remaining context window %                        |
|  +-- Debounce: skip unless 10 calls elapsed or escalation    |
|  +-- Output WARNING (<=35%) or CRITICAL (<=25%)              |
|  +-- Always exits 0 (advisory only)                          |
+-----------------------------------------------------------------+
                          |
+-- PreCompact ----------------------------------------------+
|  precompact_checkpoint.py                                   |
|  +-- Extract state from last 300 transcript lines           |
|  +-- state_manager.update_from_extracted() -> save state    |
|  +-- Save transcript checkpoint for recovery                |
|  +-- Auto-delete checkpoints older than 7 days              |
+-----------------------------------------------------------------+
                          |
                    [Session Stop]
                          |
+-- Stop (2 hooks, sequential) ---------------------------------+
|  1. verify_completion.py                                       |
|     +-- Check for uncommitted changes                          |
|     +-- Scan for TODO/FIXME/HACK in diff                       |
|     +-- Exit 0 to allow, advisory warning printed              |
|                                                                |
|  2. notify_completion.py                                       |
|     +-- Platform guard (macOS only, no-op elsewhere)           |
|     +-- state_manager.get_active_work() -> get context         |
|     +-- osascript display notification -> Notification Center  |
|     +-- Auto-forwards to iPhone via Handoff                    |
+-----------------------------------------------------------------+
```

## SessionStart: Restore State

**File**: `sessionstart_restore_state.py`

When a new session begins, this hook restores context from the previous session:

1. Loads `PERSISTENT_STATE.yaml` via `state_manager.get_active_work()`
2. Loads critical failure patterns from `patterns-critical.md` (checks project-level first, then global, then `rules/core-patterns.md` as final fallback)
3. Detects if an orchestrate workflow was in progress
4. Outputs continuation instructions with issue number, phase, and branch

!!! example "What SessionStart outputs (~500 tokens)"

    ```
    ## Restored Context

    ### Project State
    active_work:
      issue: 42
      branch: feature/issue-42-health-check
      phase: PATCH
      last_action: Starting PATCH phase
      completed_phases: [MAP-PLAN, PLAN-CHECK]

    ### Critical Patterns (Always Apply)
    1. VERIFICATION_GAP: Read spec/code before assuming
    2. ENUM_VALUE: Use VALUES not Python names
    3. COMPONENT_API: Read PropTypes before using

    ### ACTIVE ORCHESTRATE WORKFLOW
    Issue: #42 | Phase: PATCH | Branch: feature/issue-42-health-check
    Continue with the current phase using the Task tool.
    ```

!!! note "Token Budget"
    SessionStart outputs approximately 500 tokens of restored context. This is an 85% reduction from the naive approach of dumping raw transcript summaries (~3,250 tokens). Every token of hook output competes with code context in the agent's working memory.

## PreCompact: Extract and Save State

**File**: `precompact_checkpoint.py`

Before context compression, this hook extracts structured state from the conversation transcript:

| Extracted Field | Source Pattern | Example |
|----------------|---------------|---------|
| `last_issue` | `Issue #NNN` in transcript | `775` |
| `last_phase` | Phase keywords (MAP-PLAN, PATCH, etc.) | `PATCH` |
| `artifacts_created` | `AGENT_RETURN: filename.md` | `["patch-775-032626.md"]` |
| `files_modified` | Created/modified/updated mentions | `["backend/models.py"]` |
| `pending_tasks` | `- [ ]` items (last 5) | `["Add frontend tests"]` |
| `key_decisions` | Sentences with "decided", "chose" | `["Using Zustand for state"]` |

The extracted state is written to `PERSISTENT_STATE.yaml` via `state_manager.update_from_extracted()`. A raw transcript copy is saved for recovery. Checkpoints older than 7 days are automatically deleted.

## Stop: Verify Completion

**File**: `verify_completion.py`

!!! warning "Anti-Rationalization"
    AI agents exhibit a specific failure mode: declaring a task complete when it is not. Common rationalizations include "functionally complete" (but uncommitted), "tests would require additional infrastructure" (but the issue says "add tests"), and "remaining TODOs are minor" (but they are in the acceptance criteria).

This hook checks for signs of incomplete work:

- **Uncommitted changes** in substantive files (ignoring lock files and config files like `.yaml`, `.yml`, `.toml`)
- **TODO/FIXME/HACK markers** in added lines within the current diff

The output is advisory -- it prints warnings visible to the user as context for whether to continue the conversation. The hook always exits 0 to avoid feedback loops.

## Stop: Notify Completion

**File**: `notify_completion.py`

Sends a macOS Notification Center alert when the session finishes. See [Notifications](notifications.md) for details.

## PostToolUse: Context Monitor

**File**: `context_monitor.py`

`context_monitor.py` runs after every tool call and monitors context window usage:

| Remaining Context | Severity | Action |
|-------------------|----------|--------|
| > 35% | Silent | No output |
| <= 35% | WARNING | "Avoid starting new complex work" |
| <= 25% | CRITICAL | "Context nearly exhausted -- wrap up or compact" |

- Debounced every 10 tool calls to avoid spam
- Severity escalation bypasses debounce (WARNING to CRITICAL warns immediately)
- Session-isolated state in `/tmp/claude-ctx-monitor-{session_id}.json`
- Always exits 0 (advisory only, never blocks)

## Configuration

Hooks are configured in `settings.json`:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/precompact_checkpoint.py"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/sessionstart_restore_state.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/context_monitor.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/verify_completion.py"
          },
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/notify_completion.py"
          }
        ]
      }
    ]
  }
}
```

## How Hooks Create Statefulness

Without hooks, every context compaction resets the agent. It loses track of the current issue, branch, phase, and what work has been done. The hook pair solves this:

```
Session 1:  Work on issue #775, PATCH phase
               |
            PreCompact fires -> saves issue=775, phase=PATCH to YAML
               |
            [Context compressed -- conversation history lost]
               |
            SessionStart fires -> restores issue=775, phase=PATCH
               |
Session 2:  Agent knows it was working on #775 PATCH, continues
```

The `--resume` flag in `/orchestrate` reads `completed_phases` from this same state file to skip phases that already finished, even across session restarts.
