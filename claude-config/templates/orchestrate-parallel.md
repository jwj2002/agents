# Orchestrate Parallel & Worktree Reference

Reference loaded by `/orchestrate` when running with `--parallel`, `--resume`, or any pattern that fans out work across multiple agents.

---

## MAP Fan-Out (COMPLEX issues only)

For COMPLEX issues, the MAP phase can fan out parallel exploration agents to investigate different subsystems concurrently. The MAP agent then synthesizes findings into a single artifact.

```
# Spawn in parallel (single message, multiple Task calls):
Task(
  description='Explore backend for issue N',
  subagent_type='Explore',
  prompt='''Investigate backend/ for issue #N: "{title}"
  Find: relevant models, services, routes, schemas, enums, and dependencies.
  Report: file paths, key functions, current behavior, and test coverage.
  Focus on files that will need changes.'''
)

Task(
  description='Explore frontend for issue N',
  subagent_type='Explore',
  prompt='''Investigate frontend/src/ for issue #N: "{title}"
  Find: relevant components, hooks, API calls, routes, and state management.
  Report: file paths, component APIs (PropTypes), current behavior.
  Focus on files that will need changes.'''
)

Task(
  description='Explore tests for issue N',
  subagent_type='Explore',
  prompt='''Investigate test coverage for issue #N: "{title}"
  Find: existing tests for affected modules in backend/ and frontend/.
  Report: test file paths, what is/isn't covered, test patterns used.'''
)
```

> **Fan-out agents get fresh context.** Each Explore agent spawns with only the issue title and investigation focus. Do NOT paste codebase findings into the prompt — let each agent discover independently.

**After all complete**: Feed combined findings into MAP agent prompt as `## Exploration Results`.
This replaces MAP doing its own sequential exploration, saving investigation time.

**Skip fan-out** when:
- Backend-only or frontend-only issue (only 1 subsystem to explore)
- TRIVIAL/SIMPLE classification (MAP-PLAN handles exploration inline)

---

## MAP + TEST-PLANNER Parallel (COMPLEX with --with-tests)

When `--with-tests` is provided and the issue is COMPLEX, MAP and TEST-PLANNER can run concurrently since they both read the issue context independently:

```
# Parallel: MAP + TEST-PLANNER (both read issue, no dependency)
Task(description='MAP for issue N', ...)             ← run in parallel
Task(description='TEST-PLANNER for issue N', ...)    ← run in parallel

# Then sequential: PLAN → CONTRACT → PLAN-CHECK → PATCH → PROVE
```

## PLAN-CHECK + TEST-PLANNER Parallel

When `--with-tests` is provided, PLAN-CHECK and TEST-PLANNER can run concurrently since both read the plan artifact but write to separate outputs:

```
# Parallel: PLAN-CHECK + TEST-PLANNER (both read plan, no dependency)
Task(description='PLAN-CHECK for issue N', ...)      ← run in parallel
Task(description='TEST-PLANNER for issue N', ...)    ← run in parallel

# Then sequential: PATCH → PROVE
```

---

## Speculative PATCH (alongside PLAN-CHECK)

PLAN-CHECK is read-only validation that passes ~90%+ of the time. Instead of waiting for it, start PATCH speculatively in parallel.

**Pre-condition**: Create a save point before speculative execution:

```bash
SPECULATIVE_BASE=$(git rev-parse HEAD)
```

```
# Spawn in parallel:
Task(description='PLAN-CHECK for issue N', ...)    ← validation
Task(description='PATCH for issue N', ...)          ← speculative implementation
```

**After both complete**:
- If PLAN-CHECK **passed**: PATCH result is valid. Proceed to PROVE. Saved one full agent cycle.
- If PLAN-CHECK **found issues**: Rollback speculative PATCH, then re-run after plan revision:

  ```bash
  # Rollback speculative PATCH changes
  git checkout -- .
  git clean -fd
  ```

**Enable speculative PATCH** when:
- Issue is SIMPLE (low plan-rejection risk)
- No prior PLAN-CHECK failures on this issue
- Backend-only change (simpler, lower conflict risk)

**Disable speculative PATCH** when:
- TRIVIAL (no PLAN-CHECK to run, so no speculation needed)
- COMPLEX issue or fullstack (plan rejection rate is higher)
- Prior attempt on this issue was BLOCKED
- User explicitly requests sequential execution

---

## Parallel Execution Rules

**Use parallel Task calls** (multiple Task invocations in a single message) when:
- Both agents read from the same input (issue body or plan artifact)
- Neither depends on the other's output
- Both write to separate artifact files

**Do NOT parallelize** agents that depend on predecessor artifacts (e.g., PATCH depends on PLAN).

---

## Parallel Worktree Mode (`--parallel`)

When `--parallel` is provided, the workflow runs inside an isolated git worktree.

### Setup

1. Create worktree:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, '$HOME/.claude/hooks')
   from worktree_manager import create_worktree
   path = create_worktree($ISSUE, 'feature/issue-$ISSUE-slug')
   print(f'Worktree created: {path}')
   "
   ```

2. If `WorktreeExistsError`:
   - If `--resume` also provided: use the existing worktree path
   - Otherwise: report error, suggest adding `--resume`

3. Track worktree in state (use **repo root** as `project_dir`, NOT worktree CWD):

   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   python3 -c "
   import sys; sys.path.insert(0, '$HOME/.claude/hooks')
   from state_manager import update_phase
   from pathlib import Path
   update_phase(Path('$REPO_ROOT'), $ISSUE, '$BRANCH', 'SETUP', 'Created worktree', worktree_path='$WORKTREE_PATH')
   "
   ```

### Agent Execution

All `Task()` spawns set working directory to the worktree path. Artifacts are written to `{worktree}/.agents/outputs/`.

**State tracking**: All `update_phase()` calls MUST use the **repo root** as `project_dir`, not the worktree CWD. Use `get_repo_root()` from `worktree_manager`:

```bash
REPO_ROOT=$(python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from worktree_manager import get_repo_root; print(get_repo_root())")
python3 -c "... update_phase(Path('$REPO_ROOT'), $ISSUE, '$BRANCH', '$PHASE', 'Starting $PHASE phase', worktree_path='$WORKTREE_PATH')"
```

### Auto-Detect Worktree on Resume

When `--resume` is provided (with or without `--parallel`):
1. Load worktree path from state: `get_worktree_for_issue(project_dir, issue)`
2. If state has a `worktree_path`:
   - If path still exists on disk: use it as CWD for remaining phases (auto-detect parallel mode)
   - If path is gone (cleaned up): re-create worktree and restart from beginning
3. If state has no `worktree_path`: resume normally (non-parallel mode)

### Post-Workflow

After PROVE completes, report worktree path for PR creation:

```
Worktree: .worktrees/issue-42/
Next: cd .worktrees/issue-42 && /pr 42
```

Do NOT auto-remove worktree — user may need it for PR revisions.

---

## Resume Mode (`--resume`)

When `--resume` is provided, skip already-completed phases:

1. Load state:

   ```bash
   python3 -c "import sys, json; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import load_state; from pathlib import Path; print(json.dumps(load_state(Path('.')), indent=2))"
   ```

2. Read `completed_phases` from state. If empty, start from beginning.

3. Determine next phase:

   | Last Completed | Next Phase |
   |----------------|------------|
   | None | MAP-PLAN (or MAP) |
   | MAP-PLAN | PLAN-CHECK (or CONTRACT if fullstack) |
   | PLAN-CHECK | PATCH |
   | PATCH | PROVE |
   | PROVE | Done — report status |

4. Verify artifacts exist for all completed phases before skipping:

   ```bash
   for PHASE in $COMPLETED_PHASES; do
     ls .agents/outputs/${PHASE,,}-${ISSUE}-*.md 2>/dev/null || echo "WARNING: Missing artifact for $PHASE"
   done
   ```

5. Resume from the next incomplete phase:

   ```
   Resuming issue #184 from PATCH phase (MAP-PLAN, PLAN-CHECK already complete)
   ```

---

## Failure Recovery (BLOCKED or crashed phase)

Use `--resume` after fixing the root cause. The state file tracks the last
**completed** phase, so resume always picks up at the right point.

### Scenario A: PROVE returns BLOCKED

1. Read the PROVE artifact for `root_cause` and fix the code.
2. Re-run: `/orchestrate N --resume`
3. Resume logic: `completed_phases` = `[MAP-PLAN, PLAN-CHECK]` (PATCH ran but
   PROVE blocked it, so PATCH is NOT in `completed_phases`).
   → Next phase = PATCH. Implementation re-runs with failure context injected.

### Scenario B: Agent crashes mid-run (no artifact written)

State still shows the previous completed phase (the crashed agent never called
`update_phase` to mark itself done). `--resume` re-runs the crashed phase from
scratch with a fresh context window.

### Scenario C: Artifact missing for a "completed" phase

The artifact-verification step (Resume Mode point 4) warns:
`WARNING: Missing artifact for MAP-PLAN`

Do not force-resume past a missing artifact. Instead:
- Re-run: `/orchestrate N --resume` — it will stop and warn, then restart from
  the missing phase.
- If the artifact was manually deleted and state is stale, clear state manually:
  ```bash
  python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import clear_active; from pathlib import Path; clear_active(Path('.'), N)"
  ```
  Then re-run from scratch: `/orchestrate N`
