# Parallel Execution

Parallel execution operates at two levels: agent-level parallelism within a single session, and worktree-level parallelism across multiple terminal sessions.

## Two Levels of Parallelism

```
Level 1: Agent-Level (within one session)
+-------------------------------------------+
| /orchestrate 42                           |
|                                           |
|   MAP fan-out:                            |
|     Task(explore backend)  ---+           |
|     Task(explore frontend) ---+-- parallel|
|     Task(explore tests)    ---+           |
|                                           |
|   Speculative PATCH:                      |
|     Task(PLAN-CHECK) ---+                 |
|     Task(PATCH)      ---+-- parallel      |
+-------------------------------------------+

Level 2: Worktree-Level (across sessions)
+--------------------+  +--------------------+
| Terminal Tab 1     |  | Terminal Tab 2     |
| /orchestrate 42    |  | /orchestrate 57    |
|   --parallel       |  |   --parallel       |
|        |           |  |        |           |
|        v           |  |        v           |
| .worktrees/        |  | .worktrees/        |
|   issue-42/        |  |   issue-57/        |
|   (isolated copy)  |  |   (isolated copy)  |
+--------------------+  +--------------------+
```

## Agent-Level Parallelism

Within a single orchestrate session, certain agents can run concurrently when they share input but produce independent outputs.

### Parallel Patterns

| Pattern | Agents | Condition |
|---------|--------|-----------|
| MAP fan-out | Explore backend + frontend + tests | COMPLEX pipeline tier |
| MAP + TEST-PLANNER | MAP + TEST-PLANNER | COMPLEX pipeline with `--with-tests` |
| PLAN-CHECK + TEST-PLANNER | PLAN-CHECK + TEST-PLANNER | `--with-tests` flag |
| Speculative PATCH | PLAN-CHECK + PATCH | SIMPLE pipeline, backend-only |
| Fullstack PATCH | Backend PATCH + Frontend PATCH | Fullstack with CONTRACT |

### MAP Fan-Out

For COMPLEX issues, the MAP phase can spawn parallel exploration agents:

```
+-- Task(Explore backend/)  --> file paths, functions, current behavior
|
+-- Task(Explore frontend/) --> components, hooks, API calls, state
|
+-- Task(Explore tests/)    --> test coverage, patterns, gaps
|
v
MAP agent synthesizes all findings into single artifact
```

Skip fan-out for TRIVIAL/SIMPLE pipeline tiers (MAP-PLAN handles exploration inline) or when only one subsystem is involved.

### Speculative PATCH

PLAN-CHECK passes approximately 90% of the time. Instead of waiting for validation, PATCH can start speculatively in parallel:

```
Spawn in parallel:
  Task(PLAN-CHECK for issue 42)    <-- validation
  Task(PATCH for issue 42)         <-- speculative implementation

  PLAN-CHECK passes  --> PATCH result is valid, proceed to PROVE
  PLAN-CHECK fails   --> roll back PATCH, revise plan, re-run
```

!!! warning "When NOT to speculate"
    Disable speculative PATCH for COMPLEX issues, fullstack changes, or issues that were previously BLOCKED. The plan rejection rate is higher in these cases.

### Fullstack PATCH Split

When a CONTRACT artifact exists, PATCH can split into backend and frontend tasks:

```
CONTRACT artifact
       |
       +-- Task(PATCH backend/)   -- runs ruff + pytest
       |
       +-- Task(PATCH frontend/)  -- runs lint + build
       |
       v
  Merge into single patch artifact for PROVE
```

Skip the split when shared utility files appear in both plans or when fewer than 3 files per side are affected.

## Worktree-Level Parallelism

The `--parallel` flag isolates the entire workflow in a git worktree, enabling multiple orchestrate sessions to run concurrently on different issues.

### How It Works

```bash
/orchestrate 42 --parallel
```

1. Creates `.worktrees/issue-42/` as a full copy of the repository on its own branch
2. Runs all agents with the worktree as working directory
3. Writes artifacts to `{worktree}/.agents/outputs/`
4. Tracks state in the main repo's `PERSISTENT_STATE.yaml` (not the worktree's)

### The worktree_manager.py Module

Located in `claude-config/hooks/`, this module manages the worktree lifecycle:

| Function | Purpose |
|----------|---------|
| `create_worktree(issue, branch)` | Create `.worktrees/issue-{N}/` with feature branch |
| `remove_worktree(issue)` | Clean up after PR merge |
| `get_repo_root()` | Resolve main repo root (not worktree CWD) |
| `check_file_conflicts(planned_files)` | Check for overlap with other active worktrees |
| `get_worktree_for_issue(project_dir, issue)` | Find existing worktree path from state |

### State Tracking with Repo Root

!!! warning "State uses repo root, not worktree CWD"
    All `update_phase()` calls must use the **repo root** as `project_dir`, not the worktree path. The state file lives in the main repository so all parallel sessions share a single source of truth.

```bash
REPO_ROOT=$(python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/hooks')
from worktree_manager import get_repo_root
print(get_repo_root())
")
```

### Conflict Check (Step 1.7)

Before the workflow proceeds, it checks for file overlap at two levels:

**Open PRs:**

```bash
gh pr list --state open --json files --jq '.[].files[].path'
```

**Active worktrees:**

```python
from worktree_manager import check_file_conflicts
conflicts = check_file_conflicts(planned_files)
```

```
Planned files for issue 42:
  backend/accounts/services.py
  backend/accounts/schemas.py

Active worktree issue-57 touches:
  backend/accounts/services.py    <-- CONFLICT

WARNING: File conflicts with active worktrees.
Consider serializing or waiting for issue 57 to complete.
```

The conflict check warns but does not block. You decide whether to proceed.

### Resume in Worktree

When `--resume` is used:

1. Loads worktree path from state (`get_worktree_for_issue()`)
2. If the worktree still exists on disk: resumes inside it
3. If the worktree was cleaned up: re-creates it and starts from the beginning

When `--resume` is used without `--parallel`, it checks state for a `worktree_path` field and auto-detects whether the issue was running in parallel mode.

### Post-Merge Cleanup

After a PR merges, the `/pr` command handles cleanup:

```bash
# Archive artifacts
mv .agents/outputs/*-42-*.md .agents/outputs/archive/

# Remove worktree
python3 -c "
from worktree_manager import remove_worktree
remove_worktree(42)
"
# Result: .worktrees/issue-42/ deleted
```

!!! note "Worktrees are not auto-removed after PROVE"
    The orchestrator reports the worktree path after completion but does not delete it. You may need the worktree for PR revisions. Cleanup happens during `/pr --merge`.

## macOS Notifications

When a session completes (via the Stop hook), `notify_completion.py` sends a macOS Notification Center alert:

- Includes issue number and current phase from `state_manager`
- Auto-forwards to iPhone via Handoff
- Particularly useful when running parallel sessions in background terminal tabs

## When NOT to Parallelize

| Situation | Reason |
|-----------|--------|
| Issues share files | Merge conflicts are likely |
| Issue B depends on Issue A | B needs A's changes in main first |
| Single-file changes | Worktree overhead exceeds benefit |
| Limited machine resources | Each worktree is a full repo copy |

## Recommended Pattern: Wave Scheduling

Group independent issues into parallel waves. Dependent issues run in later waves after predecessors merge.

```
Wave 1 (parallel -- no file overlap):
  /orchestrate 42 --parallel   # accounts module
  /orchestrate 57 --parallel   # reports module

      |  both merge to main  |

Wave 2 (after Wave 1 merges):
  /orchestrate 63 --parallel   # depends on #42 changes
  /orchestrate 71 --parallel   # independent of #63
```

This pattern maximizes throughput while preventing merge conflicts. Always rebase on the latest main before creating a PR from a worktree.
