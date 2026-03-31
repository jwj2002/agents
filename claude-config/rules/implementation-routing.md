# Implementation Routing: Task Assessment → Workflow → Codex Delegation → Review

When given any task, assess complexity and route to the right workflow. Maximize use of Codex (GPT) for tasks within its capability — reviews, parallel implementation, debugging, and background work. **Make the call yourself — do not ask the user which mode to use.**

## Step 1: Assess and Route

**Assess BEFORE entering any mode.** Read the issue/task, check files involved, then decide.

| Complexity | Files | Criteria | Route To | Codex Role |
|------------|-------|----------|----------|-----------|
| **TRIVIAL** | 1 | Typo, config, rename, obvious fix | `/quick` | None |
| **SIMPLE** | 1-3 | Clear requirements, single subsystem | Plan Mode | Offer review after |
| **MODERATE** | 4-5 | Clear pattern, single subsystem | `/orchestrate` (SIMPLE tier) | Review (recommended) |
| **COMPLEX** | 6+ | Cross-cutting, architectural decisions | `/orchestrate` (COMPLEX tier) | Review (automatic) + delegate subtasks |
| **FULLSTACK** | Any | Backend + frontend changes | `/orchestrate` + CONTRACT | Review (enum/API focus) + parallel implementation |
| **PRIOR FAIL** | Any | Re-attempt of a BLOCKED issue | `/codex:rescue` first, then `/orchestrate` | Primary implementer (different model) |

**Modifiers:**
- **Multiple independent issues** → add `--parallel` (worktree isolation, separate tabs)
- **Interrupted workflow** → add `--resume` (skip completed phases)
- **Subtasks within an issue** → delegate independent subtasks to Codex via `/codex:rescue --background`

## Step 2: Maximize Codex Delegation

After routing the primary workflow, identify work that Codex should handle. Codex (GPT) runs **in background** — Claude continues working in parallel.

### When to Delegate to Codex

```
┌──────────────────────────────────────────────────────────────┐
│                  CODEX DELEGATION RULES                       │
│                                                               │
│  DELEGATE TO CODEX when:                                      │
│  ├── Task is independent (doesn't block Claude's work)       │
│  ├── Prior attempt by Claude was BLOCKED (try different model)│
│  ├── Fullstack: frontend can run parallel to Claude's backend│
│  ├── Debugging: test failures, regression investigation      │
│  ├── Refactoring: mechanical changes (rename, extract, move) │
│  └── Review: any MODERATE+ task after implementation         │
│                                                               │
│  KEEP IN CLAUDE when:                                         │
│  ├── Task requires orchestrate pipeline state (MAP→PATCH)    │
│  ├── Task needs MCP server access (vault-metrics, etc.)      │
│  ├── Task involves project-specific rules/patterns           │
│  ├── Task is the primary implementation thread                │
│  └── Architectural decisions that need deep context           │
└──────────────────────────────────────────────────────────────┘
```

### Delegation Patterns

#### Pattern 1: Parallel Fullstack Split
Claude handles backend (needs MCP, rules, patterns). Codex handles frontend in background.

```
Claude: PATCH backend (services, models, routes)
  │
  └── /codex:rescue --background --write \
        "Implement frontend component per CONTRACT:
         - Component: PaymentForm at frontend/src/components/
         - API endpoint: POST /api/payments (see contract artifact)
         - Enum VALUES: STATUS='pending','completed','failed'
         - Run: npm run lint && npm run build when done"
  │
  ├── Claude continues with backend tests
  └── /codex:status → check when frontend is done
```

#### Pattern 2: Debug Delegation
Claude is implementing issue A. Tests for issue B start failing. Delegate debugging to Codex.

```
Claude: working on issue A...
  │
  └── /codex:rescue --background \
        "Investigate why tests in backend/auth/tests/ are failing.
         Started failing after commit abc123. Find root cause and fix."
  │
  ├── Claude continues issue A
  └── /codex:result → review Codex's fix when done
```

#### Pattern 3: Prior Failure Escalation
Claude's PATCH was BLOCKED. Instead of re-running Claude with failure context, try Codex first (different model = different approach).

```
PROVE: BLOCKED (root cause: MULTI_MODEL — forgot to update related model)
  │
  ├── OLD: re-run Claude PATCH with failure context
  │
  └── NEW: /codex:rescue --write --effort high \
        "Fix issue #184. Prior attempt failed with MULTI_MODEL error:
         forgot to update Advisor model when changing User.
         See .agents/outputs/patch-184-032626.md for what was tried.
         Fix the multi-model coordination."
```

#### Pattern 4: Mechanical Refactoring
Large rename, extract, or move operations that don't require architectural judgment.

```
Claude: planning the refactor...
  │
  └── /codex:rescue --background --write \
        "Rename all occurrences of 'UserAccount' to 'Account' across
         backend/backend/ directory. Update imports, type hints, and
         test references. Run ruff check . when done."
  │
  ├── Claude works on the architectural changes
  └── /codex:status → merge Codex's renames with Claude's work
```

#### Pattern 5: Test Writing
Claude implements the feature. Codex writes the tests.

```
Claude: PATCH completes feature implementation
  │
  └── /codex:rescue --background --write \
        "Write tests for the new payment processing module.
         Source: backend/backend/payments/services.py
         Test file: backend/backend/payments/tests/test_services.py
         Use pytest + pytest-asyncio. SQLite in-memory only.
         Cover: success cases, validation errors, edge cases.
         Run: cd backend && pytest -q when done."
  │
  ├── Claude continues to PROVE phase
  └── /codex:result → incorporate tests before commit
```

## Step 3: Announce Your Decision

State the routing decision AND any Codex delegation briefly:

> **Quick** — typo in README, 1 file. No Codex.

> **Plan mode** — 2 files, clear requirements. Will offer Codex review after.

> **Orchestrate (MODERATE)** — 4 files, backend-only. Codex review after PROVE.

> **Orchestrate (COMPLEX, fullstack)** — new module + frontend. Claude handles backend, delegating frontend to Codex in background. Adversarial review automatic.

> **Codex-first** — issue 184 failed twice. Sending to `/codex:rescue` before re-attempting with Claude.

> **Parallel** — Issues 42 and 57 independent. `--parallel` in separate tabs. Codex reviews both in background.

The user can override any routing or delegation decision.

## Step 4: Apply Codex Review

After implementation (regardless of workflow), apply review based on risk:

| Risk Level | Codex Action | Command |
|------------|-------------|---------|
| **TRIVIAL** | Skip entirely | — |
| **SIMPLE** | Offer (don't force) | "Want a cross-model review?" |
| **MODERATE** | Run after implementation | `/codex:review --background` |
| **COMPLEX** | Run adversarial after PROVE | `/codex:adversarial-review --background` |
| **FULLSTACK** | Run with enum/API focus | `/codex:adversarial-review --background "Focus on: enum value mismatches, API contract compliance, access control"` |
| **PRIOR FAIL** | Run before commit | `/codex:adversarial-review --wait "Focus on: {prior root cause}"` |

### Review Integration with Orchestrate

For MODERATE+ tasks, Codex review runs **after PROVE passes**:

```
PATCH → PROVE passes → /codex:adversarial-review --background
                               │
                          findings?
                          ├── No  → /pr
                          └── Yes → fix → re-run PROVE → /pr
```

## Codex Model Selection Guide

| Task Type | Recommended Model | Effort | Why |
|-----------|------------------|--------|-----|
| Quick review | `gpt-5.4-mini` | `medium` | Fast, cheap, sufficient for review |
| Adversarial review | `gpt-5.4` | `high` | Needs reasoning depth to challenge decisions |
| Bug investigation | `gpt-5.4-mini` | `medium` | Read-only diagnosis, speed matters |
| Feature implementation | `gpt-5.4` | `high` | Write-capable, needs quality |
| Mechanical refactoring | `gpt-5.4-mini` | `low` | Repetitive, pattern-following |
| Test writing | `gpt-5.4` | `medium` | Needs understanding of code but not deep reasoning |
| Prior failure rescue | `gpt-5.4` | `xhigh` | Maximum reasoning for stuck problems |

## Workflow Flows

### Quick (`/quick`)

For TRIVIAL tasks. No pipeline, no agents, no GitHub issue required.

1. Load critical patterns
2. Make the change directly
3. Verify (lint/test if applicable)
4. Report what was done

### Plan Mode

For SIMPLE tasks. Plan before implementing.

1. Enter plan mode (`EnterPlanMode`)
2. Explore codebase, read relevant files
3. Write implementation plan to plan file
4. Exit plan mode — present plan with options:

```
Options:
1. "Compact and implement" (Recommended) — Compact context and implement the plan
2. "Implement now" — Implement immediately without compacting
3. "Revise plan" — Adjust the approach before implementing
```

5. After implementation, **offer** Codex review.

### Orchestrate

For MODERATE, COMPLEX, and FULLSTACK tasks. Full agent pipeline.

```
TRIVIAL pipeline:  MAP-PLAN → PATCH → PROVE-lite
SIMPLE pipeline:   MAP-PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE
COMPLEX pipeline:  MAP → PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE
```

Use `/orchestrate <issue-number>` with optional flags: `--with-tests`, `--resume`, `--parallel`.

During PATCH phase, identify subtasks to delegate to Codex (see Delegation Patterns above).

## Examples

### Quick
- "Fix the typo in the README" → **Quick**, no Codex

### Plan Mode
- "Add feature flag to config.py" → **Plan mode**, offer review after

### Orchestrate + Codex Delegation
- "Add validation endpoint with tests" → **Orchestrate MODERATE**. Claude implements endpoint, `/codex:rescue --background` writes tests. Codex review after.
- "Create fact_vocabulary table + service + seed data + tests" → **Orchestrate COMPLEX**. Claude handles all (single subsystem). Automatic adversarial review.
- "Implement payment form with backend API" → **Orchestrate FULLSTACK**. Claude does backend, Codex does frontend in background via `/codex:rescue`. Automatic review with enum/API focus.

### Codex-First (Prior Failure)
- "Issue 184 has failed twice" → `/codex:rescue --effort xhigh` first. If Codex succeeds, review with Claude. If not, escalate to human.

### Parallel + Codex
- "Implement issues 42, 57, and 63":
  - 42 and 57 independent → `--parallel` in separate tabs
  - Both get Codex adversarial review in background
  - 63 depends on 42 → sequential after 42 merges
