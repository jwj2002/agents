# Orchestrate Workflow

The `/orchestrate` command runs a multi-agent pipeline to implement GitHub issues. It classifies complexity, spawns specialized agents in sequence, tracks state across context compactions, and records outcomes for the learning system.

!!! info "Automatic Routing"
    You don't need to decide when to use `/orchestrate` vs Plan Mode vs `/quick`. Claude automatically assesses every task and routes to the right workflow based on complexity, then announces the decision. See [Implementation Routing](#implementation-routing) at the bottom of this page.

## Usage

```bash
/orchestrate 184                        # Standard execution
/orchestrate #184                       # With hash prefix
/orchestrate 184 --with-tests           # Include TEST-PLANNER phase
/orchestrate 184 --resume               # Resume from last completed phase
/orchestrate 184 --parallel             # Run in isolated worktree
/orchestrate 184 --parallel --resume    # Resume in existing worktree
```

If no issue number is provided, you will be prompted to create one with `/feature` or `/bug`.

## Flags

| Flag | Purpose |
|------|---------|
| `--with-tests` | Adds TEST-PLANNER agent after MAP-PLAN. Recommended for calculations, formulas, or complex business logic. |
| `--resume` | Skips already-completed phases. Reads state from `PERSISTENT_STATE.yaml`. |
| `--parallel` | Creates an isolated git worktree (`.worktrees/issue-{N}/`). Enables concurrent orchestrate sessions on independent issues. |

## Pipeline Overview

```
GitHub Issue
     |
     +-- TRIVIAL --> MAP-PLAN --> PATCH --> PROVE-lite
     |
     +-- SIMPLE ---> MAP-PLAN --> [TEST-PLANNER] --> CONTRACT* --> PLAN-CHECK --> PATCH --> PROVE
     |
     +-- COMPLEX --> MAP --> PLAN --> [TEST-PLANNER] --> CONTRACT* --> PLAN-CHECK --> PATCH --> PROVE

     * CONTRACT is MANDATORY for fullstack (PATCH will STOP without it)
       CONTRACT-lite (inline) for simple fullstack (0 new endpoints, <=2 frontend files)
     [ ] = Optional (requires --with-tests flag)
```

## Complexity Classification

### Decision Flow

```
                    +---------------+
                    | GitHub Issue  |
                    +-------+-------+
                            |
                 +----------+----------+
                 | Classify Complexity |
                 +----------+----------+
                            |
           +----------------+----------------+
           |                |                |
      +---------+     +----------+     +----------+
      | TRIVIAL |     |  SIMPLE  |     | COMPLEX  |
      | 1-2 file|     | 3-5 file |     | 6+ files |
      +----+----+     +----+-----+     +----+-----+
           |               |                |
           v               v                v
      MAP-PLAN         MAP-PLAN        MAP --> PLAN
           |               |                |
           |          +----+----+      +----+----+
           |          |fullstack|      |fullstack|
           |          +----+----+      +----+----+
           |          yes  | no        yes  | no
           |               v                v
           |          CONTRACT(*)       CONTRACT
           |               |                |
           |          PLAN-CHECK       PLAN-CHECK
           |               |                |
           v               v                v
        PATCH            PATCH            PATCH
           |               |                |
           v               v                v
      PROVE-lite         PROVE            PROVE
      (gates only)         |                |
           |               v                v
           +------------- /pr --------------+

     (*) CONTRACT-lite if 0 new endpoints + <=2 frontend files
         CONTRACT-full otherwise
```

### Classification Criteria

| Level | Files | Criteria | Workflow |
|-------|-------|----------|----------|
| **TRIVIAL** | 1-2 | Docs, config, obvious fixes | MAP-PLAN, skips PLAN-CHECK, PROVE-lite |
| **SIMPLE** | 3-5 | Clear pattern, single subsystem | MAP-PLAN with full verification |
| **COMPLEX** | 6+ | Endpoints, migrations, architectural | Separate MAP and PLAN phases |

## Step-by-Step Process

### Step 0: Verify Issue

```bash
gh issue view $ISSUE --json number,title,body
```

If the issue does not exist, the workflow stops.

### Step 1: Classify and Detect Stack

The orchestrator reads the issue body and classifies complexity. After MAP-PLAN (or MAP) completes, it auto-detects the stack by scanning the plan artifact for `backend/` and `frontend/` references:

- Both present: `fullstack` (CONTRACT becomes mandatory)
- Only one: `backend` or `frontend`

### Step 1.6: CONTRACT Weight Assessment

For fullstack issues, decide between inline and full contract:

| Signal | CONTRACT-lite (inline) | CONTRACT-full (agent) |
|--------|------------------------|-----------------------|
| New endpoints | 0 | 1+ |
| Enum changes | 0-1 | 2+ |
| Breaking API changes | No | Yes |
| Frontend files touched | 1-2 | 3+ |

CONTRACT-lite embeds the contract directly in the PATCH prompt. CONTRACT-full spawns a dedicated agent that produces its own artifact.

### Step 1.7: Conflict Check

Before branching, checks for file conflicts with open PRs and active worktrees:

```bash
# Files from open PRs
gh pr list --state open --json files --jq '.[].files[].path'

# Compare against planned files from MAP-PLAN artifact
```

If conflicts are found, the orchestrator warns but does not block. You decide whether to proceed or wait.

### Step 2: Create Feature Branch

```bash
git fetch origin && git checkout -b feature/issue-$ISSUE-description origin/main
```

Skipped when `--parallel` is used (the worktree setup handles branch creation).

### Step 3: Spawn Agents

Each agent is spawned via the Task tool with inherited context:

```markdown
## Inherited Context (DO NOT re-read these files)
- Issue: #184 - Add payment module
- Branch: feature/issue-184-payment-module
- Stack: backend
- Complexity: SIMPLE

## Prior Artifacts
- map-plan-184-032626.md
```

Every agent validates that predecessor artifacts exist before starting. If an artifact is missing, the agent stops immediately.

### Step 4: Report Status

```
Workflow complete for issue #184

Artifacts:
- map-plan-184-032626.md
- patch-184-032626.md
- prove-184-032626.md

PROVE status: PASS

Next: /pr 184 to create pull request
```

## Agent Roles

| Agent | Phase | Read-Only | Purpose |
|-------|-------|-----------|---------|
| **MAP** | 1 | Yes | Investigate codebase (COMPLEX only) |
| **MAP-PLAN** | 1+2 | Yes | Investigate + plan (TRIVIAL/SIMPLE) |
| **PLAN** | 2 | Yes | File-by-file implementation plan (COMPLEX) |
| **TEST-PLANNER** | 1.5 | Yes | Test matrix with edge cases (optional) |
| **CONTRACT** | 2.5 | Yes | Backend/frontend API contract (fullstack) |
| **PLAN-CHECK** | 2.8 | Yes | Validate plan completeness |
| **PATCH** | 3 | No | Implement changes |
| **PROVE** | 4 | No | Verify and record outcome |

!!! warning "CONTRACT is mandatory for fullstack"
    If the detected stack is `fullstack`, PATCH will refuse to proceed without a CONTRACT artifact. This prevents enum value mismatches and API contract violations.

## State Tracking

State persists in `.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`:

```yaml
active_work:
  issue: 184
  branch: feature/issue-184-payment-module
  phase: PATCH
  last_action: Starting PATCH phase
  completed_phases: [MAP-PLAN, PLAN-CHECK]
  worktree_path: null
meta:
  updated: '2026-03-26'
```

The `state_manager.py` module provides:

| Function | Used By |
|----------|---------|
| `update_phase()` | Orchestrate (before each agent) |
| `clear_active()` | Orchestrate (after completion) |
| `get_completed_phases()` | `--resume` flag |
| `get_active_work()` | SessionStart hook |
| `get_worktree_for_issue()` | `--parallel` flag |

## Resume Mode

When `--resume` is provided:

1. Loads state from `PERSISTENT_STATE.yaml`
2. Reads `completed_phases` to determine where to continue
3. Verifies artifacts exist for all completed phases
4. Resumes from the next incomplete phase

| Last Completed | Next Phase |
|----------------|------------|
| (none) | MAP-PLAN or MAP |
| MAP-PLAN | PLAN-CHECK (or CONTRACT if fullstack) |
| PLAN-CHECK | PATCH |
| PATCH | PROVE |
| PROVE | Done |

## Failure Handling

If any agent fails:

1. Workflow stops immediately
2. Reports which agent failed and the expected artifact path
3. Does not proceed to the next phase

!!! note "Prior failures are injected"
    If an issue was previously attempted and PROVE recorded BLOCKED, the failure context (root cause, details, prevention) is injected into the next PATCH prompt to avoid repeating the same mistake.

## Artifacts

All outputs go to `.agents/outputs/` with the naming pattern `{agent}-{issue}-{mmddyy}.md`:

| Artifact | Agent |
|----------|-------|
| `map-plan-184-032626.md` | MAP-PLAN |
| `test-plan-184-032626.md` | TEST-PLANNER |
| `contract-184-032626.md` | CONTRACT |
| `plan-check-184-032626.md` | PLAN-CHECK |
| `patch-184-032626.md` | PATCH |
| `prove-184-032626.md` | PROVE |

Each agent validates the chain: PROVE checks for PATCH, PATCH checks for MAP-PLAN (and CONTRACT if fullstack), and so on.

## Implementation Routing

Claude automatically assesses every task and routes to the right workflow. You describe what you want; the routing rule decides how to do it.

```
┌──────────────────────────────────────────────────────────────┐
│                    IMPLEMENTATION ROUTING                      │
│                                                               │
│  Assess Task                                                  │
│       │                                                       │
│       ├─ TRIVIAL ──→ /quick ──────────────→ done              │
│       │                                                       │
│       ├─ SIMPLE ───→ Plan Mode ───────────→ done              │
│       │                  └─ offer codex review                │
│       │                                                       │
│       ├─ MODERATE ─→ /orchestrate ────────→ codex review      │
│       │              (SIMPLE tier)          (recommended)      │
│       │                                                       │
│       ├─ COMPLEX ──→ /orchestrate ────────→ codex review      │
│       │              (COMPLEX tier)         (automatic)        │
│       │                                                       │
│       ├─ FULLSTACK ─→ /orchestrate ───────→ codex review      │
│       │               + CONTRACT            (enum/API focus)  │
│       │                                                       │
│       └─ PRIOR FAIL → /orchestrate ───────→ codex review      │
│                       + failure context     (automatic)        │
│                       or /codex:rescue                        │
│                                                               │
│  + --parallel for 2+ independent issues                       │
│  + --resume for interrupted workflows                         │
└──────────────────────────────────────────────────────────────┘
```

| Complexity | Files | Route | Codex Review |
|------------|-------|-------|-------------|
| **TRIVIAL** | 1 | `/quick` | Skip |
| **SIMPLE** | 1-3 | Plan Mode | Offer |
| **MODERATE** | 4-5 | `/orchestrate` SIMPLE | Recommended |
| **COMPLEX** | 6+ | `/orchestrate` COMPLEX | Automatic |
| **FULLSTACK** | Any | `/orchestrate` + CONTRACT | Automatic (enum/API focus) |
| **PRIOR FAIL** | Any | `/orchestrate` + context or `/codex:rescue` | Automatic |

## Codex Review Integration

After PROVE passes on MODERATE+ tasks, a cross-model review runs automatically:

```
PATCH → PROVE passes → /codex:adversarial-review --background
                               │
                          findings?
                          ├── No  → /pr
                          └── Yes → fix → re-run PROVE → /pr
```

!!! tip "Why cross-model review matters"
    Claude and GPT have different blind spots. ENUM_VALUE errors (26% of fullstack failures) are caught more reliably when a different model reviews the code. Claude writes it, Codex reviews it — genuinely adversarial, not the same model checking its own work.
