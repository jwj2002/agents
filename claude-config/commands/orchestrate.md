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
```

If no issue provided, instruct user to create one with `/feature` or `/bug`.

**Flags**:
- `--with-tests`: Run TEST-PLANNER agent after MAP-PLAN (recommended for calculations/formulas)

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
TRIVIAL/SIMPLE: MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
COMPLEX:        MAP → PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
```

- `[TEST-PLANNER]` runs if `--with-tests` flag provided
- `CONTRACT*` **MANDATORY** if fullstack (not optional — PATCH will STOP without it)

---

## State Tracking (CRITICAL for Context Continuity)

**Purpose**: Persist orchestrate state so it survives context compaction.

**State file**: `.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`

### Update State Before Each Phase

**MUST** run this command BEFORE spawning each agent:

```bash
python3 -c "
import yaml
from pathlib import Path
state_file = Path('.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml')
if state_file.exists():
    data = yaml.safe_load(state_file.read_text())
    data['active_work'] = {
        'issue': $ISSUE,
        'branch': '$BRANCH',
        'phase': '$PHASE',
        'last_action': 'Starting $PHASE phase'
    }
    state_file.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
"
```

Replace variables:
- `$ISSUE`: Issue number (e.g., `370`)
- `$BRANCH`: Current branch name (e.g., `feature/issue-370-description`)
- `$PHASE`: Current phase (e.g., `MAP-PLAN`, `PATCH`, `PROVE`)

### Clear State After Completion

After workflow completes successfully:

```bash
python3 -c "
import yaml
from pathlib import Path
state_file = Path('.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml')
if state_file.exists():
    data = yaml.safe_load(state_file.read_text())
    data['active_work'] = {
        'issue': None,
        'branch': 'main',
        'phase': None,
        'last_action': 'Completed issue #$ISSUE'
    }
    state_file.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
"
```

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

### Step 2: Create Feature Branch

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
1. VERIFICATION_GAP: Verify assumptions by reading actual code
2. ENUM_VALUE: Use VALUES not Python names ("CO-OWNER" not "CO_OWNER")
3. COMPONENT_API: Read PropTypes before using components

## Prior Artifacts
- {list any prior artifacts for this issue}
```

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

**After all complete**: Feed combined findings into MAP agent prompt as `## Exploration Results`.
This replaces MAP doing its own sequential exploration, saving investigation time.

**Skip fan-out** when:
- Backend-only or frontend-only issue (only 1 subsystem to explore)
- TRIVIAL/SIMPLE classification (MAP-PLAN handles exploration inline)

#### MAP-PLAN (or MAP + PLAN)
```
Task(
  description='MAP-PLAN for issue N',
  prompt='''You are MAP-PLAN agent.

## Inherited Context
- Issue: #N - {title}
- Branch: feature/issue-N-description
- Stack: {backend|frontend|fullstack}

## Critical Patterns (Always Apply)
1. VERIFICATION_GAP: Verify assumptions by reading actual code
2. ENUM_VALUE: Use VALUES not Python names
3. COMPONENT_API: Read PropTypes before using

## Issue Body
{issue body}

## Instructions
Read agent instructions (check .claude/agents/map-plan.md first, else ~/.claude/agents/map-plan.md).
Write artifact to .agents/outputs/map-plan-N-MMDDYY.md
End with AGENT_RETURN: map-plan-N-MMDDYY.md
'''
)
```

**Validate**: File exists, has AGENT_RETURN directive.

#### TEST-PLANNER (if --with-tests)
```
Task(
  description='TEST-PLANNER for issue N',
  prompt='''You are TEST-PLANNER agent.

## Inherited Context
- Issue: #N - {title}
- Stack: {backend|frontend|fullstack}
- MAP-PLAN: .agents/outputs/map-plan-N-MMDDYY.md

## Critical Patterns
1. VERIFICATION_GAP: Verify assumptions by reading actual code
2. Derive edge cases systematically from formulas

## Instructions
Read agent instructions (check .claude/agents/test-planner.md first, else ~/.claude/agents/test-planner.md).
Read MAP-PLAN artifact for implementation context.
Generate test matrix, edge cases, and test signatures.
Write to .agents/outputs/test-plan-N-MMDDYY.md
End with AGENT_RETURN: test-plan-N-MMDDYY.md
'''
)
```

**Validate**: File exists, has test matrix, has AGENT_RETURN directive.

#### CONTRACT (MANDATORY if fullstack)

**GATE**: If stack is fullstack, CONTRACT MUST run. PATCH will refuse to proceed without the contract artifact.

```
Task(
  description='CONTRACT for issue N',
  prompt='You are CONTRACT agent. Read agent instructions (check .claude/agents/contract.md first, else ~/.claude/agents/contract.md).
  Read PLAN artifact.
  Write to .agents/outputs/contract-N-MMDDYY.md'
)
```

#### PLAN-CHECK (Always runs before PATCH)
```
Task(
  description='PLAN-CHECK for issue N',
  prompt='''You are PLAN-CHECK agent.

## Inherited Context
- Issue: #N - {title}
- Stack: {backend|frontend|fullstack}
- Complexity: {TRIVIAL|SIMPLE|COMPLEX}

## Prior Artifacts
- MAP-PLAN: .agents/outputs/map-plan-N-MMDDYY.md
- CONTRACT: .agents/outputs/contract-N-MMDDYY.md (if fullstack)

## Instructions
Read agent instructions (check .claude/agents/plan-checker.md first, else ~/.claude/agents/plan-checker.md).
Validate plan completeness. Do NOT modify any files.
Write to .agents/outputs/plan-check-N-MMDDYY.md
End with AGENT_RETURN: plan-check-N-MMDDYY.md
'''
)
```

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
```
Task(
  description='PATCH for issue N',
  prompt='''You are PATCH agent.

## Inherited Context
- Issue: #N - {title}
- Branch: feature/issue-N-description
- Stack: {backend|frontend|fullstack}

## Critical Patterns (Always Apply)
1. VERIFICATION_GAP: Verify component APIs by reading actual code
2. ENUM_VALUE: Use VALUES not Python names
3. COMPONENT_API: Read PropTypes, never invent props

## Prior Artifacts
- MAP-PLAN: .agents/outputs/map-plan-N-MMDDYY.md
- TEST-PLAN: .agents/outputs/test-plan-N-MMDDYY.md (if exists)
- CONTRACT: .agents/outputs/contract-N-MMDDYY.md (if fullstack)
- PLAN-CHECK: .agents/outputs/plan-check-N-MMDDYY.md

## Prior Failure (if re-attempt)
{injected from failures.jsonl if this issue was previously BLOCKED, else "First attempt"}

## Instructions
Read agent instructions (check .claude/agents/patch.md first, else ~/.claude/agents/patch.md).
Implement changes per MAP-PLAN.
Implement tests following TEST-PLAN signatures (if exists).
Write to .agents/outputs/patch-N-MMDDYY.md
End with AGENT_RETURN: patch-N-MMDDYY.md
'''
)
```

#### PATCH (Parallel Fullstack — when CONTRACT exists)

When STACK=fullstack and CONTRACT artifact exists, split PATCH into two parallel tasks.
CONTRACT defines the API boundary — backend and frontend implement against it independently.

```
# Spawn in parallel (single message, two Task calls):
Task(
  description='PATCH-backend for issue N',
  prompt='''You are PATCH agent (BACKEND ONLY).

## Inherited Context
- Issue: #N - {title}
- Branch: feature/issue-N-description
- Stack: fullstack (backend portion)
- SCOPE: Only implement backend/ changes from MAP-PLAN

## Prior Artifacts
- MAP-PLAN: .agents/outputs/map-plan-N-MMDDYY.md
- CONTRACT: .agents/outputs/contract-N-MMDDYY.md (AUTHORITATIVE for API surface)
- TEST-PLAN: .agents/outputs/test-plan-N-MMDDYY.md (if exists)

## Prior Failure (if re-attempt)
{injected from failures.jsonl or "First attempt"}

## Instructions
Read agent instructions (check .claude/agents/patch.md first, else ~/.claude/agents/patch.md).
Implement ONLY backend/ changes per MAP-PLAN. Use CONTRACT for API shapes.
Run backend gates: ruff check . && pytest -q
Write to .agents/outputs/patch-backend-N-MMDDYY.md
End with AGENT_RETURN: patch-backend-N-MMDDYY.md
'''
)

Task(
  description='PATCH-frontend for issue N',
  prompt='''You are PATCH agent (FRONTEND ONLY).

## Inherited Context
- Issue: #N - {title}
- Branch: feature/issue-N-description
- Stack: fullstack (frontend portion)
- SCOPE: Only implement frontend/ changes from MAP-PLAN

## Prior Artifacts
- MAP-PLAN: .agents/outputs/map-plan-N-MMDDYY.md
- CONTRACT: .agents/outputs/contract-N-MMDDYY.md (AUTHORITATIVE for API surface)

## Critical Patterns
1. ENUM_VALUE: Use VALUES from CONTRACT, not Python names
2. COMPONENT_API: Read PropTypes before using existing components

## Instructions
Read agent instructions (check .claude/agents/patch.md first, else ~/.claude/agents/patch.md).
Implement ONLY frontend/ changes per MAP-PLAN. Use CONTRACT for API shapes and enum VALUES.
Run frontend gates: npm run lint && npm run build
Write to .agents/outputs/patch-frontend-N-MMDDYY.md
End with AGENT_RETURN: patch-frontend-N-MMDDYY.md
'''
)
```

**After both complete**: Validate no file conflicts between the two artifacts.
Merge into single `patch-N-MMDDYY.md` summary artifact for PROVE.

**Skip parallel PATCH** when:
- Shared utility files appear in both backend and frontend plans (merge conflict risk)
- Issue involves fewer than 3 files per side (overhead exceeds benefit)
- No CONTRACT artifact exists (synchronization point missing)
```

#### PROVE
```
Task(
  description='PROVE for issue N',
  prompt='''You are PROVE agent.

## Inherited Context
- Issue: #N - {title}
- Stack: {backend|frontend|fullstack}

## Critical Patterns to Verify
1. ENUM_VALUE: grep for enum strings, verify VALUES used
2. COMPONENT_API: grep PropTypes, verify props match
3. TODO/STUB: grep for incomplete code

## Prior Artifacts
- PATCH: .agents/outputs/patch-N-MMDDYY.md
- MAP-PLAN: .agents/outputs/map-plan-N-MMDDYY.md

## Instructions
Read agent instructions (check .claude/agents/prove.md first, else ~/.claude/agents/prove.md).
Run verification commands (ruff, pytest, npm lint, npm build).
Record outcome to .claude/memory/metrics.jsonl
If BLOCKED, record to .claude/memory/failures.jsonl
Write to .agents/outputs/prove-N-MMDDYY.md
End with AGENT_RETURN: prove-N-MMDDYY.md
'''
)
```

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

```
# Spawn in parallel:
Task(description='PLAN-CHECK for issue N', ...)    ← validation
Task(description='PATCH for issue N', ...)          ← speculative implementation
```

**After both complete**:
- If PLAN-CHECK **passed**: PATCH result is valid. Proceed to PROVE. Saved one full agent cycle.
- If PLAN-CHECK **found issues**: Discard PATCH result. Report PLAN-CHECK issues to user. Re-run PATCH after plan revision.

**Enable speculative PATCH** when:
- Issue is TRIVIAL or SIMPLE (low plan-rejection risk)
- No prior PLAN-CHECK failures on this issue
- Backend-only change (simpler, lower conflict risk)

**Disable speculative PATCH** when:
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
