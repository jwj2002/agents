---
description: Execute MAP → PLAN → PATCH → PROVE workflow for GitHub issues
argument-hint: [issue-number] [--with-tests] [--discuss] [--resume] [--parallel]
---

# Orchestrate Command

**Role**: Conductor (ORCHESTRATION ONLY — never implement features yourself).

---

## Usage

```bash
/orchestrate 184
/orchestrate 184 --with-tests    # Include TEST-PLANNER phase
/orchestrate 184 --discuss       # Identify gray areas before planning
/orchestrate 184 --resume        # Resume from last completed phase
/orchestrate 184 --parallel      # Run in isolated worktree
/orchestrate 184 --parallel --resume  # Resume in existing worktree
```

If no issue provided, instruct user to create one with `/feature` or `/bug`.

**Flags**:
- `--with-tests`: Run TEST-PLANNER agent after MAP-PLAN (recommended for calculations/formulas)
- `--discuss`: Run DISCUSS agent before MAP-PLAN. Recommended for COMPLEX and FULLSTACK
- `--resume`: Resume an interrupted workflow from the last completed phase
- `--parallel`: Run workflow in an isolated git worktree (`.worktrees/issue-{N}/`)

---

## Workflow

```
TRIVIAL:        MAP-PLAN → PATCH → PROVE-lite
SIMPLE:         [DISCUSS] → MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PATCH → PROVE
COMPLEX:        [DISCUSS] → MAP → PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
```

- `TRIVIAL` skips PLAN-CHECK and uses PROVE-lite
- `[TEST-PLANNER]` runs if `--with-tests` is provided
- `CONTRACT*` is **MANDATORY** if fullstack — PATCH will STOP without it

---

## Reference Files (load on demand)

When the workflow reaches Step 3, load the relevant reference:

| Reference | Loaded for |
|-----------|------------|
| `templates/orchestrate-pipeline.md` | Per-agent prompt templates, validation gates, failure-context injection |
| `templates/orchestrate-parallel.md` | MAP fan-out, speculative PATCH, worktree mode, resume mode |
| `templates/agent-prompt.md` | The base agent prompt template (variable substitution) |

Don't pre-load all of these. Read only what the current phase needs.

---

## Agent Resolution (Global + Project Override)

Agent instructions are loaded with project-first fallback:

1. `.claude/agents/{agent}.md` (project-specific override)
2. `~/.claude/agents/{agent}.md` (global default)

**Examples**:
- Project has custom `patch.md` → uses project version
- Project has no `map-plan.md` → uses global version
- Artifacts ALWAYS go to project-local `.agents/outputs/`

```bash
AGENT="map-plan"
if [ -f ".claude/agents/${AGENT}.md" ]; then
  AGENT_PATH=".claude/agents/${AGENT}.md"
else
  AGENT_PATH="~/.claude/agents/${AGENT}.md"
fi
```

---

## State Tracking (CRITICAL for Context Continuity)

**Purpose**: Persist orchestrate state so it survives context compaction.

**State file**: `.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`

### Update State Before Each Phase

**MUST** run BEFORE spawning each agent:

```bash
python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import update_phase; from pathlib import Path; update_phase(Path('.'), $ISSUE, '$BRANCH', '$PHASE', 'Starting $PHASE phase')"
```

Variables: `$ISSUE` (issue number), `$BRANCH` (current branch), `$PHASE` (`MAP-PLAN`, `PATCH`, `PROVE`, etc.).

### Clear State After Completion

```bash
python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import clear_active; from pathlib import Path; clear_active(Path('.'), $ISSUE)"
```

For `--resume` and `--parallel` semantics: see `templates/orchestrate-parallel.md`.

---

## Process

### Step 0: Verify Issue

```bash
gh issue view $ISSUE --json number,title,body
```

If not found, STOP.

### Step 0.5: Scan Seeds

Check if any dormant seeds match this issue:

```bash
if [ -d ".planning/seeds" ]; then
  ISSUE_TITLE=$(gh issue view $ISSUE --json title --jq '.title')
  for seed in .planning/seeds/SEED-*.md; do
    [ -f "$seed" ] || continue
    STATUS=$(grep "^status:" "$seed" | awk '{print $2}')
    if [ "$STATUS" = "dormant" ]; then
      TRIGGER=$(grep "^trigger_when:" "$seed" | cut -d'"' -f2)
      SEED_NAME=$(grep "^# " "$seed" | head -1 | sed 's/^# //')
      SEED_ID=$(grep "^id:" "$seed" | awk '{print $2}')
      echo "Checking $SEED_ID: $SEED_NAME (trigger: $TRIGGER)"
    fi
  done
fi
```

If seeds match, report before proceeding. If no `.planning/seeds/`, skip silently.

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

After MAP-PLAN (or MAP), scan its artifact for stack scope:

```bash
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

**If STACK=fullstack**: CONTRACT is MANDATORY. Report:

```
Stack auto-detected: fullstack (plan touches backend/ and frontend/)
CONTRACT agent will run before PLAN-CHECK.
```

### Step 1.6: CONTRACT Weight Assessment (fullstack only)

| Signal | CONTRACT-lite (inline) | CONTRACT-full (agent) |
|--------|------------------------|----------------------|
| New endpoints | 0 | 1+ |
| Enum changes | 0-1 | 2+ |
| Breaking API changes | No | Yes |
| Frontend files touched | 1-2 | 3+ |

**CONTRACT-lite**: Skip the CONTRACT agent. Add an inline contract section to the PATCH prompt instead.
**CONTRACT-full**: Spawn CONTRACT agent (see pipeline reference).

### Step 1.7: Check for File Conflicts with Open PRs

```bash
OPEN_PR_FILES=$(gh pr list --state open --json files --jq '.[].files[].path' 2>/dev/null | sort -u)
PLAN_FILES=$(grep -oP '`[^`]+\.(py|jsx?|tsx?|md|json)`' .agents/outputs/{map-plan,plan}-${ISSUE}-*.md 2>/dev/null | tr -d '`' | sort -u)
CONFLICTS=$(comm -12 <(echo "$OPEN_PR_FILES") <(echo "$PLAN_FILES"))

if [ -n "$CONFLICTS" ]; then
  echo "WARNING: File conflicts with open PRs:"
  echo "$CONFLICTS"
fi
```

Also check active worktrees for file overlap (especially in `--parallel` mode) using `worktree_manager.check_file_conflicts`. Warn but don't block.

### Step 2: Create Feature Branch

If `--parallel`: Branch was already created by worktree setup. Skip.

Otherwise:

```bash
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ]; then
  git checkout -b feature/issue-$ISSUE-description
fi
```

### Step 3: Spawn Agents (Task Tool)

**CRITICAL**: Use the Task tool to spawn each agent with inherited context.

For per-agent prompt templates, validation gates, and failure-context injection, **read `templates/orchestrate-pipeline.md`**.

For parallel patterns (MAP fan-out, speculative PATCH, parallel fullstack PATCH, worktree setup, resume mode), **read `templates/orchestrate-parallel.md`**.

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

## Failure Handling

If any agent fails:

1. STOP workflow
2. Report which agent failed
3. Show expected artifact path
4. Do NOT proceed

If PROVE returns BLOCKED, the failure is recorded to `.claude/memory/failures.jsonl`. Subsequent runs of `/orchestrate $ISSUE` automatically inject failure context into the PATCH prompt.

---

## Artifacts

All outputs go to `.agents/outputs/`:
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
