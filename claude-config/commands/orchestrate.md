---
description: Execute MAP → PLAN → PATCH → PROVE workflow for GitHub issues
argument-hint: [issue-number]
---

# Orchestrate Command

**Role**: Conductor (ORCHESTRATION ONLY)

---

## Table of Contents

- [Usage](#usage)
- [Agent Resolution](#agent-resolution-global--project-override)
- [Workflow](#workflow)
- [State Tracking](#state-tracking-critical-for-context-continuity)
- [Process](#process)
  - [Step 0: Verify Issue](#step-0-verify-issue)
  - [Step 1: Classify Complexity](#step-1-classify-complexity)
  - [Step 2: Create Feature Branch](#step-2-create-feature-branch)
  - [Step 3: Spawn Agents](#step-3-spawn-agents-task-tool)
  - [Step 4: Report Status](#step-4-report-status)
- [Parallel Execution](#parallel-execution)
- [Failure Handling](#failure-handling)
- [Artifacts](#artifacts)
- [Rules](#rules)

---

## Usage

```bash
/orchestrate 184
/orchestrate #184
/orchestrate 184 --with-tests    # Include TEST-PLANNER phase
/orchestrate 184 --resume        # Resume from last completed phase
/orchestrate 184 --parallel      # Run in isolated worktree
/orchestrate 184 --parallel --resume  # Resume in existing worktree
```

If no issue provided, instruct user to create one with `/feature` or `/bug`.

**Flags**:
- `--with-tests`: Run TEST-PLANNER agent after MAP-PLAN (recommended for calculations/formulas)
- `--resume`: Resume an interrupted workflow from the last completed phase
- `--parallel`: Run workflow in an isolated git worktree (`.worktrees/issue-{N}/`). Enables concurrent orchestrate sessions on independent issues.

---

## Agent Resolution (Global + Project Override)

Agent instructions are loaded with project-first fallback:

```
1. .claude/agents/{agent}.md     (project-specific override)
2. ~/.claude/agents/{agent}.md   (global default)
```

**Examples**:
- Project has custom `patch.md` → uses project version
- Project has no `map-plan.md` → uses global version
- Artifacts ALWAYS go to project-local `.agents/outputs/`

**Resolution helper** (use before spawning agents):
```bash
AGENT="map-plan"
if [ -f ".claude/agents/${AGENT}.md" ]; then
  AGENT_PATH=".claude/agents/${AGENT}.md"
else
  AGENT_PATH="~/.claude/agents/${AGENT}.md"
fi
```

---

## Workflow

```
TRIVIAL:        MAP-PLAN → PATCH → PROVE-lite
SIMPLE:         MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
COMPLEX:        MAP → PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
```

- `TRIVIAL` skips PLAN-CHECK and uses PROVE-lite (gates only, no Level 2-3 checks)
- `[TEST-PLANNER]` runs if `--with-tests` flag provided
- `CONTRACT*` **MANDATORY** if fullstack (not optional — PATCH will STOP without it)

---

## State Tracking (CRITICAL for Context Continuity)

**Purpose**: Persist orchestrate state so it survives context compaction.

**State file**: `.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`

### Update State Before Each Phase

**MUST** run this command BEFORE spawning each agent:

```bash
python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import update_phase; from pathlib import Path; update_phase(Path('.'), $ISSUE, '$BRANCH', '$PHASE', 'Starting $PHASE phase')"
```

Replace variables:
- `$ISSUE`: Issue number (e.g., `370`)
- `$BRANCH`: Current branch name (e.g., `feature/issue-370-description`)
- `$PHASE`: Current phase (e.g., `MAP-PLAN`, `PATCH`, `PROVE`)

### Clear State After Completion

After workflow completes successfully:

```bash
python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import clear_active; from pathlib import Path; clear_active(Path('.'), $ISSUE)"
```

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
   # Check each completed phase has its artifact
   for PHASE in $COMPLETED_PHASES; do
     ls .agents/outputs/${PHASE,,}-${ISSUE}-*.md 2>/dev/null || echo "WARNING: Missing artifact for $PHASE"
   done
   ```

5. Resume from the next incomplete phase. Report:
   ```
   Resuming issue #184 from PATCH phase (MAP-PLAN, PLAN-CHECK already complete)
   ```

---

## Parallel Worktree Mode (`--parallel`)

When `--parallel` is provided, the workflow runs inside an isolated git worktree.

### Setup Phase

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

All Task() spawns set working directory to the worktree path.
Artifacts are written to `{worktree}/.agents/outputs/`.

**State tracking**: All `update_phase()` calls MUST use the **repo root** as `project_dir`, not the worktree CWD. Use `get_repo_root()` from `worktree_manager` to resolve the correct path:

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
Do NOT auto-remove worktree -- user may need it for PR revisions.

---

## Process

### Step 0: Verify Issue

```bash
gh issue view $ISSUE --json number,title,body
```

If not found, STOP.

### Step 1: Classify Complexity

| Level | Criteria | Workflow |
|-------|----------|----------|
| TRIVIAL | Docs, config | MAP-PLAN |
| SIMPLE | 1-3 files | MAP-PLAN |
| COMPLEX | Endpoints, migrations | MAP + PLAN |

Report:
```
Issue #184 classified as: SIMPLE (backend)
Using workflow: MAP-PLAN → PATCH → PROVE
```

### Step 1.5: Detect Stack

After MAP-PLAN (or MAP) completes, scan its artifact for stack scope:

```bash
# Auto-detect stack from plan artifact
PLAN_FILE=$(ls .agents/outputs/{map-plan,plan}-${ISSUE}-*.md 2>/dev/null | head -1)
HAS_BACKEND=$(grep -l "backend/" "$PLAN_FILE" 2>/dev/null)
HAS_FRONTEND=$(grep -l "frontend/" "$PLAN_FILE" 2>/dev/null)

if [ -n "$HAS_BACKEND" ] && [ -n "$HAS_FRONTEND" ]; then
  STACK="fullstack"
elif [ -n "$HAS_FRONTEND" ]; then
  STACK="frontend"
else
  STACK="backend"
fi
```

**If STACK=fullstack**: CONTRACT is MANDATORY. Report to user:
```
Stack auto-detected: fullstack (plan touches backend/ and frontend/)
CONTRACT agent will run before PLAN-CHECK.
```

**Override**: If user initially classified as backend-only but plan touches frontend, escalate to fullstack.

### Step 1.6: CONTRACT Weight Assessment (fullstack only)

If STACK=fullstack, decide whether to spawn the full CONTRACT agent or use an inline contract:

| Signal | CONTRACT-lite (inline) | CONTRACT-full (agent) |
|--------|------------------------|----------------------|
| New endpoints | 0 | 1+ |
| Enum changes | 0-1 | 2+ |
| Breaking API changes | No | Yes |
| Frontend files touched | 1-2 | 3+ |

**CONTRACT-lite**: Skip the CONTRACT agent. Instead, add an inline contract section to the PATCH prompt:

```markdown
## API Contract (inline — no new endpoints)
- Enum VALUES: [extract from MAP-PLAN enum documentation]
- Changed response fields: [from MAP-PLAN]
- No new endpoints. Existing endpoints modified: [list]
```

**CONTRACT-full**: Spawn CONTRACT agent as documented in Step 3.

### Step 1.7: Check for File Conflicts with Open PRs

Before branching, check if open PRs touch files this issue will affect:

```bash
# Get files from open PRs
OPEN_PR_FILES=$(gh pr list --state open --json files --jq '.[].files[].path' 2>/dev/null | sort -u)

# After MAP-PLAN, compare planned files against open PR files
PLAN_FILES=$(grep -oP '`[^`]+\.(py|jsx?|tsx?|md|json)`' .agents/outputs/{map-plan,plan}-${ISSUE}-*.md 2>/dev/null | tr -d '`' | sort -u)

CONFLICTS=$(comm -12 <(echo "$OPEN_PR_FILES") <(echo "$PLAN_FILES"))

if [ -n "$CONFLICTS" ]; then
  echo "WARNING: File conflicts with open PRs:"
  echo "$CONFLICTS"
  echo "Consider serializing or rebasing after those PRs merge."
fi
```

Also check active worktrees for file overlap:

```bash
# Check worktrees for file conflicts (especially in --parallel mode)
python3 -c "
import sys, json
sys.path.insert(0, '$HOME/.claude/hooks')
from worktree_manager import check_file_conflicts
planned = json.loads('$PLAN_FILES_JSON')  # list of planned file paths
conflicts = check_file_conflicts(planned)
if conflicts:
    print('WARNING: File conflicts with active worktrees:')
    for c in conflicts:
        print(f'  {c[\"file\"]} (worktree: issue-{c[\"issue\"]})')
    print('Consider serializing or waiting for the other issue to complete.')
"
```

**Note**: This runs after MAP-PLAN produces the file list. If conflicts are found, warn but don't block — user decides whether to proceed.

### Step 2: Create Feature Branch

If `--parallel`: Branch was already created by worktree setup. Skip this step.

Otherwise:
```bash
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ]; then
  git checkout -b feature/issue-$ISSUE-description
fi
```

### Step 3: Spawn Agents (Task Tool)

**CRITICAL**: Use Task tool to spawn each agent WITH inherited context.

#### Context Inheritance Template

All agent prompts MUST include this inherited context block to reduce re-reading:

```markdown
## Inherited Context (DO NOT re-read these files)
- Issue: #{issue_number} - {title}
- Branch: {current_branch}
- Spec: {spec_path if any} ({version})
- Stack: {backend|frontend|fullstack}
- Complexity: {TRIVIAL|SIMPLE|COMPLEX}

## Critical Patterns (Always Apply)
Loaded from rules/core-patterns.md (auto-loaded by Claude Code).
Apply VERIFICATION_GAP, ENUM_VALUE, and COMPONENT_API checks as relevant.

## Prior Artifacts
- {list any prior artifacts for this issue}
```

!!! warning "Fresh Context Rule"
    Each agent gets a clean context window. Pass file PATHS in the artifact list, not file CONTENTS. Let agents use the Read tool to load what they need. This ensures consistent quality regardless of how long the orchestrate session has been running.

#### MAP Fan-Out (COMPLEX issues only)

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

!!! info "Fan-out agents get fresh context"
    Each Explore agent spawns with only the issue title and investigation focus. Do NOT paste codebase findings into the prompt — let each agent discover independently.

**After all complete**: Feed combined findings into MAP agent prompt as `## Exploration Results`.
This replaces MAP doing its own sequential exploration, saving investigation time.

**Skip fan-out** when:
- Backend-only or frontend-only issue (only 1 subsystem to explore)
- TRIVIAL/SIMPLE classification (MAP-PLAN handles exploration inline)

#### MAP-PLAN (or MAP + PLAN)

Use prompt template from `templates/agent-prompt.md` with:

| Variable | Value |
|----------|-------|
| AGENT_NAME | MAP-PLAN |
| AGENT_FILE | map-plan.md |
| ARTIFACT_NAME | map-plan-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | (none — first agent) |
| AGENT_INSTRUCTIONS | Investigate and plan. Include `## Issue Body` with full issue body. |

**Validate**: File exists, has AGENT_RETURN directive.

#### TEST-PLANNER (if --with-tests)

Use prompt template with:

| Variable | Value |
|----------|-------|
| AGENT_NAME | TEST-PLANNER |
| AGENT_FILE | test-planner.md |
| ARTIFACT_NAME | test-plan-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md |
| AGENT_INSTRUCTIONS | Read MAP-PLAN artifact. Generate test matrix, edge cases, and test signatures. |

**Validate**: File exists, has test matrix, has AGENT_RETURN directive.

#### CONTRACT (MANDATORY if fullstack — see Step 1.6 for lite path)

**GATE**: If stack is fullstack and CONTRACT-full selected, spawn CONTRACT agent. PATCH will refuse to proceed without the contract artifact.

Use prompt template with:

| Variable | Value |
|----------|-------|
| AGENT_NAME | CONTRACT |
| AGENT_FILE | contract.md |
| ARTIFACT_NAME | contract-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md |
| AGENT_INSTRUCTIONS | Define backend/frontend API contract. Document enum VALUES explicitly. |

#### PLAN-CHECK (Skip if TRIVIAL)

**If TRIVIAL**: Skip PLAN-CHECK entirely. Proceed directly to PATCH.
**If SIMPLE or COMPLEX**: Run PLAN-CHECK as documented below.
Use prompt template with:

| Variable | Value |
|----------|-------|
| AGENT_NAME | PLAN-CHECK |
| AGENT_FILE | plan-checker.md |
| ARTIFACT_NAME | plan-check-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md<br>- CONTRACT: (if fullstack) |
| AGENT_INSTRUCTIONS | Validate plan completeness. Do NOT modify any files. |

**Validate**: File exists, has AGENT_RETURN directive.
**If ISSUES_FOUND**: Report to user before proceeding to PATCH. User decides whether to continue or revise plan.

#### Failure Context Injection (Before Re-running PATCH)

If this issue has been attempted before (prior PROVE was BLOCKED), inject failure context into PATCH prompt:

```bash
# Check for prior failures on this issue
PRIOR_FAILURE=$(grep "\"issue\":${ISSUE}" .claude/memory/failures.jsonl 2>/dev/null | tail -1)
```

If found, add to PATCH prompt's Inherited Context:

```markdown
## Prior Failure (CRITICAL — avoid repeating)
- Root cause: {root_cause from failure record}
- Details: {details}
- Prevention: {prevention}
- Failed files: {files}
```

#### PATCH (Single-Stack or Default)

Use prompt template with:

| Variable | Value |
|----------|-------|
| AGENT_NAME | PATCH |
| AGENT_FILE | patch.md |
| ARTIFACT_NAME | patch-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN, TEST-PLAN (if exists), CONTRACT (if fullstack), PLAN-CHECK |
| PRIOR_FAILURE_BLOCK | Injected from failures.jsonl or "First attempt" |
| AGENT_INSTRUCTIONS | Implement changes per MAP-PLAN. Implement tests following TEST-PLAN signatures (if exists). |

#### PATCH (Parallel Fullstack — when CONTRACT exists)

When STACK=fullstack and CONTRACT artifact exists, split PATCH into two parallel tasks using the scoped variant from `templates/agent-prompt.md`.

Spawn in parallel (single message, two Task calls):

**PATCH-backend**:

| Variable | Value |
|----------|-------|
| AGENT_NAME | PATCH (BACKEND ONLY) |
| SCOPE | backend/ |
| ARTIFACT_NAME | patch-backend-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN, CONTRACT (AUTHORITATIVE), TEST-PLAN (if exists) |
| AGENT_INSTRUCTIONS | Implement ONLY backend/ changes. Run gates: ruff check . && pytest -q |

**PATCH-frontend**:

| Variable | Value |
|----------|-------|
| AGENT_NAME | PATCH (FRONTEND ONLY) |
| SCOPE | frontend/ |
| ARTIFACT_NAME | patch-frontend-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN, CONTRACT (AUTHORITATIVE), TEST-PLAN (if exists) |
| AGENT_INSTRUCTIONS | Implement ONLY frontend/ changes. Use CONTRACT for enum VALUES. Run gates: npm run lint && npm run build |

**After both complete**: Validate no file conflicts between the two artifacts.
Merge into single `patch-{ISSUE}-{MMDDYY}.md` summary artifact for PROVE.

**Skip parallel PATCH** when:
- Shared utility files appear in both backend and frontend plans (merge conflict risk)
- Issue involves fewer than 3 files per side (overhead exceeds benefit)
- No CONTRACT artifact exists (synchronization point missing)

#### PROVE (full) — SIMPLE and COMPLEX

Use prompt template with:

| Variable | Value |
|----------|-------|
| AGENT_NAME | PROVE |
| AGENT_FILE | prove.md |
| ARTIFACT_NAME | prove-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - PATCH: .agents/outputs/patch-{ISSUE}-{MMDDYY}.md<br>- MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md |
| AGENT_INSTRUCTIONS | Run verification commands (ruff, pytest, npm lint, npm build). Record outcome to metrics.jsonl. If BLOCKED, record to failures.jsonl. |

#### PROVE-lite — TRIVIAL only

Use the PROVE-lite variant from `templates/agent-prompt.md`. Gates only, no Level 2-3 checks.

### Step 4: Report Status

```
✓ Workflow complete for issue #184

Artifacts:
- map-plan-184-010325.md
- patch-184-010325.md
- prove-184-010325.md

PROVE status: PASS ✅

Next: /pr 184 to create pull request
```

---

## Parallel Execution

When `--with-tests` is provided and the issue is COMPLEX, MAP and TEST-PLANNER can run concurrently since they both read the issue context independently:

```
# Parallel: MAP + TEST-PLANNER (both read issue, no dependency)
Task(description='MAP for issue N', ...)      ← run in parallel
Task(description='TEST-PLANNER for issue N', ...)  ← run in parallel

# Then sequential: PLAN → CONTRACT → PLAN-CHECK → PATCH → PROVE
```

### PLAN-CHECK + TEST-PLANNER (when --with-tests)

When `--with-tests` is provided, PLAN-CHECK and TEST-PLANNER can run concurrently since both read the plan artifact but write to separate outputs:

```
# Parallel: PLAN-CHECK + TEST-PLANNER (both read plan, no dependency)
Task(description='PLAN-CHECK for issue N', ...)      ← run in parallel
Task(description='TEST-PLANNER for issue N', ...)     ← run in parallel

# Then sequential: PATCH → PROVE
```

### Speculative PATCH (alongside PLAN-CHECK)

PLAN-CHECK is read-only validation that passes ~90%+ of the time. Instead of waiting for it, start PATCH speculatively in parallel:

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

### Parallel Execution Rules

**Use parallel Task calls** (multiple Task invocations in a single message) when:
- Both agents read from the same input (issue body or plan artifact)
- Neither depends on the other's output
- Both write to separate artifact files

**Do NOT parallelize** agents that depend on predecessor artifacts (e.g., PATCH depends on PLAN).

---

## Failure Handling

If any agent fails:
1. STOP workflow
2. Report which agent failed
3. Show expected artifact path
4. Do NOT proceed

---

## Artifacts

All outputs to `.agents/outputs/`:
- `map-{issue}-{mmddyy}.md`
- `map-plan-{issue}-{mmddyy}.md`
- `plan-{issue}-{mmddyy}.md`
- `test-plan-{issue}-{mmddyy}.md` (if --with-tests)
- `contract-{issue}-{mmddyy}.md`
- `plan-check-{issue}-{mmddyy}.md`
- `patch-{issue}-{mmddyy}.md`
- `prove-{issue}-{mmddyy}.md`

---

## Rules

**MUST**:
- Require GitHub issue
- Use Task tool for agents
- Validate artifacts before proceeding
- Enforce `.claude/rules.md`

**MUST NOT**:
- Implement features yourself
- Edit code directly
- Skip verification gates
