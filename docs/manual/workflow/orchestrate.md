# Orchestrate Workflow

The orchestrate command is your primary tool for implementing GitHub issues. You give it an issue number — it investigates the codebase, plans the changes, implements them, verifies they work, and reports the result. You don't need to choose which agents run or in what order; the system handles that based on task complexity.

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
/orchestrate 184 --discuss              # Add DISCUSS phase before investigation
```

If no issue number is provided, you will be prompted to create one with `/feature` or `/bug`.

## Flags

| Flag | Purpose |
|------|---------|
| `--with-tests` | Adds TEST-PLANNER agent after MAP-PLAN. Recommended for calculations, formulas, or complex business logic. |
| `--resume` | Skips already-completed phases. Reads state from `PERSISTENT_STATE.yaml`. |
| `--parallel` | Creates an isolated git worktree (`.worktrees/issue-{N}/`). Enables concurrent orchestrate sessions on independent issues. |
| `--discuss` | Adds DISCUSS agent before MAP-PLAN/MAP to capture design decisions and trade-offs before investigation begins. |

## Pipeline Overview

```
GitHub Issue
     |
     +-- TRIVIAL --> rejected; /orchestrate redirects to /quick
     |
     +-- SIMPLE ---> [DISCUSS] --> MAP-PLAN --> [TEST-PLANNER] --> CONTRACT* --> PATCH --> PROVE
     |
     +-- COMPLEX --> [DISCUSS] --> MAP --> PLAN --> [TEST-PLANNER] --> CONTRACT* --> PLAN-CHECK --> PATCH --> PROVE

     * CONTRACT is MANDATORY for fullstack (PATCH will STOP without it)
       CONTRACT-lite (inline) for simple fullstack (0 new endpoints, <=2 frontend files)
     [ ] = Optional (requires --with-tests or --discuss flag)

     PLAN-CHECK runs only on the COMPLEX pipeline (per PR #93). SIMPLE relies on PATCH
     to catch plan defects and Codex adversarial review (post-PROVE) for the rest.
```

## Complexity Classification

???+ example "How complexity routing works"

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
          rejected;       [DISCUSS]          [DISCUSS]
          go to /quick         |                |
          (PR #94)        MAP-PLAN        MAP --> PLAN
                               |                |
                          +----+----+      +----+----+
                          |fullstack|      |fullstack|
                          +----+----+      +----+----+
                          yes  | no        yes  | no
                               v                v
                          CONTRACT(*)       CONTRACT
                               |                |
                               |           PLAN-CHECK
                               |                |
                               v                v
                             PATCH            PATCH
                               |                |
                               v                v
                             PROVE            PROVE
                               |                |
                               +----- /pr ------+

         (*) CONTRACT-lite if 0 new endpoints + <=2 frontend files
             CONTRACT-full otherwise
    ```

### Classification Criteria

| Level | Files | Criteria | Workflow |
|-------|-------|----------|----------|
| **TRIVIAL** | 1-2 | Docs, config, obvious fixes | Rejected by `/orchestrate`; redirected to `/quick` (per PR #94) |
| **SIMPLE** | 3-5 | Clear pattern, single subsystem | MAP-PLAN → [CONTRACT*] → PATCH → PROVE (no PLAN-CHECK) |
| **COMPLEX** | 6+ | Endpoints, migrations, architectural | MAP → PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE |

??? info "Detailed step-by-step process"

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
| **DISCUSS** | 0.5 | Yes | Capture design decisions (optional, `--discuss`) |
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

State is managed by `state_manager.py` and persists in `.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`. The module provides functions for updating phases, clearing active work, querying completed phases, and locating worktrees.

!!! tip "See also"
    For the full YAML schema, function reference, and fallback behavior, see [State Manager](../hooks/state-manager.md).

## Resume Mode

When `--resume` is provided:

1. Loads state from `PERSISTENT_STATE.yaml`
2. Reads `completed_phases` to determine where to continue
3. Verifies artifacts exist for all completed phases
4. Resumes from the next incomplete phase

SIMPLE pipeline (no PLAN-CHECK):

| Last Completed | Next Phase |
|----------------|------------|
| (none) | MAP-PLAN |
| MAP-PLAN | CONTRACT (if fullstack) or PATCH |
| CONTRACT | PATCH |
| PATCH | PROVE |
| PROVE | Done |

COMPLEX pipeline (PLAN-CHECK still in chain):

| Last Completed | Next Phase |
|----------------|------------|
| (none) | MAP |
| MAP | PLAN |
| PLAN | CONTRACT (if fullstack) or PLAN-CHECK |
| CONTRACT | PLAN-CHECK |
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

??? info "Advanced: Implementation routing and Codex delegation"

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

    | Complexity | Files | Route | Codex Role |
    |------------|-------|-------|-----------|
    | **TRIVIAL** | 1 | `/quick` | None |
    | **SIMPLE** | 1-3 | Plan Mode | Offer review |
    | **MODERATE** | 4-5 | `/orchestrate` SIMPLE | Review (recommended) |
    | **COMPLEX** | 6+ | `/orchestrate` COMPLEX | Review (automatic) + delegate subtasks |
    | **FULLSTACK** | Any | `/orchestrate` + CONTRACT | Review (enum/API) + parallel frontend |
    | **PRIOR FAIL** | Any | `/codex:rescue` first | Primary implementer |

    ## Codex Integration (Review + Delegation)

    Codex serves two roles: **reviewer** (after implementation) and **implementer** (parallel to Claude during PATCH).

    ### Automatic Review

    After PROVE passes on MODERATE+ tasks:

    ```
    PATCH → PROVE passes → /codex:adversarial-review --background
                                   │
                              findings?
                              ├── No  → /pr
                              └── Yes → fix → re-run PROVE → /pr
    ```

    ### Advisory Review Gate in /pr

    Independent of the post-PROVE review above, the `/pr` command (per PR #95) detects COMPLEX-tier signals — file count > 5, migration paths, auth code, data models, cross-cutting refactors — and prompts you to run `/codex:adversarial-review` before squash-merge. This gate is **advisory, not blocking**: you can decline and proceed, but for COMPLEX or fullstack changes the second opinion typically catches enum, contract, and access-control drift that PROVE does not gate on.

    ### Parallel Delegation During PATCH

    For COMPLEX and FULLSTACK tasks, Claude delegates independent subtasks to Codex in background:

    ```
    MAP-PLAN identifies subtasks
         │
         ├── Backend → Claude PATCH (primary thread)
         │       │
         │       ├── /codex:rescue --background --write (frontend)
         │       ├── /codex:rescue --background --write (tests)
         │       └── Claude continues implementing...
         │
         ▼
    /codex:status → collect results → PROVE → review → /pr
    ```

    !!! tip "Why cross-model delegation matters"
        Claude and GPT have different strengths. Claude excels at architectural reasoning and orchestration. GPT handles mechanical implementation, test writing, and debugging well. Using both in parallel maximizes throughput without sacrificing quality.

    See [Codex Plugin](../integrations/codex-plugin.md) for all delegation patterns and model selection guide.
