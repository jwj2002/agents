# State Manager

`state_manager.py` is the centralized module for reading and writing `PERSISTENT_STATE.yaml`. It is the single source of truth for orchestrate workflow state, used by hooks, the orchestrate command, and the `--resume` / `--parallel` flags.

## Why Centralized

Previously, three separate codepaths independently manipulated the same YAML file using inline `python3 -c` blocks embedded in shell commands. A quoting error, missing PyYAML, or malformed YAML would silently break state. Centralizing into one testable module with graceful fallbacks eliminated this fragility.

```
Before:  orchestrate (inline) -+
         precompact (inline)   +--> PERSISTENT_STATE.yaml (3 writers, no coordination)
         sessionstart (inline) +

After:   orchestrate  --+
         precompact   --+--> state_manager.py --> PERSISTENT_STATE.yaml (1 writer)
         sessionstart --+
         notify       --+
```

## PERSISTENT_STATE.yaml Schema

!!! example "Populated YAML during an active orchestrate session"
    ```yaml
    active_work:
      issue: 775
      branch: feature/issue-775-asset-form-fields
      phase: PATCH
      last_action: Implemented backend models
      completed_phases:
        - MAP-PLAN
        - PLAN-CHECK
      worktree_path: null    # Set when --parallel is used
    meta:
      updated: '2026-03-26'
    ```

| Field | Type | Purpose |
|-------|------|---------|
| `issue` | int or null | Current issue number |
| `branch` | string | Current git branch |
| `phase` | string or null | Current pipeline phase |
| `last_action` | string | Human-readable description of last action |
| `completed_phases` | list[str] | Phases already finished (for `--resume`) |
| `worktree_path` | string or null | Absolute path to worktree (for `--parallel`) |
| `meta.updated` | date string | Last modification date |

## Function Reference

### load_state

```python
def load_state(project_dir: Path) -> dict
```

Read `PERSISTENT_STATE.yaml` and return its contents as a dict. Returns an empty dict if the file does not exist, YAML parsing fails, or PyYAML is not installed.

### update_phase

```python
def update_phase(project_dir: Path, issue: int, branch: str,
                 phase: str, action: str, worktree_path: str | None = None) -> None
```

Update `active_work` with the current phase. Called by the orchestrate command before spawning each agent.

Key behaviors:

- Tracks the previous phase as completed (appends to `completed_phases` when transitioning to a new phase)
- Preserves existing `worktree_path` if not explicitly provided
- Updates `meta.updated` timestamp

```python
# Example: transitioning from MAP-PLAN to PATCH
update_phase(project_dir, issue=184, branch="feature/issue-184-fix",
             phase="PATCH", action="Starting PATCH agent")
# completed_phases now includes "MAP-PLAN"
```

### clear_active

```python
def clear_active(project_dir: Path, issue: int) -> None
```

Clear active workflow state after successful completion. Resets all fields to their defaults (`issue: None`, `branch: main`, `phase: None`, empty `completed_phases`). Sets `last_action` to `Completed issue #N`.

### get_completed_phases

```python
def get_completed_phases(project_dir: Path, issue: int) -> list[str]
```

Return the list of completed phases for an issue. Used by `--resume` to determine which phases to skip. Returns an empty list if the state file does not exist or the active issue does not match the requested issue.

### get_worktree_for_issue

```python
def get_worktree_for_issue(project_dir: Path, issue: int) -> str | None
```

Return the worktree path for an issue from persisted state. Used by `--resume` in combination with `--parallel` to find the correct worktree directory for resuming work.

### get_active_work

```python
def get_active_work(project_dir: Path) -> dict
```

Return the `active_work` section of the state. Used by the SessionStart hook to restore context and by the notification hook to build contextual messages.

### update_from_extracted

```python
def update_from_extracted(project_dir: Path, extracted: dict) -> None
```

Update state from precompact transcript extraction. Called by `precompact_checkpoint.py` after parsing the conversation transcript.

Accepts a dict with optional keys:

| Key | Effect |
|-----|--------|
| `last_issue` | Sets `active_work.issue` |
| `last_phase` | Sets `active_work.phase` |
| `artifacts_created` | Sets `last_action` to name of most recent artifact |

## How --resume Uses State

When `/orchestrate 184 --resume` is called:

1. `get_completed_phases(project_dir, 184)` returns `["MAP-PLAN", "PLAN-CHECK"]`
2. The orchestrate command skips MAP-PLAN and PLAN-CHECK
3. Execution continues from the next incomplete phase (CONTRACT or PATCH)

## How --parallel Uses State

When `/orchestrate 184 --parallel` is called:

1. A git worktree is created at `.worktrees/issue-184/`
2. `update_phase()` is called with `worktree_path="/abs/path/.worktrees/issue-184/"`
3. The path is persisted in `PERSISTENT_STATE.yaml`
4. On `--resume`, `get_worktree_for_issue()` returns the path so work continues in the correct worktree

## Graceful Fallbacks

The module handles missing dependencies without crashing:

- If PyYAML is not installed, all functions return empty dicts or silently no-op
- If the state file does not exist, `load_state()` returns `{}`
- If YAML parsing fails, the error is logged to `~/.claude/hooks.log` and an empty dict is returned
- Write failures are caught and logged without interrupting the session

!!! tip "Dependency"
    PyYAML is the only external dependency. The `install.sh` script installs it automatically. If it is missing at runtime, state management degrades gracefully rather than crashing.
