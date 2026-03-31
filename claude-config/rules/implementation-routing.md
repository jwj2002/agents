# Implementation Routing: Task Assessment → Workflow → Review

When given any task, assess complexity and route to the right workflow with the right review level. **Make the call yourself — do not ask the user which mode to use.**

## Step 1: Assess and Route

**Assess BEFORE entering any mode.** Read the issue/task, check files involved, then decide.

| Complexity | Files | Criteria | Route To | Codex Review |
|------------|-------|----------|----------|-------------|
| **TRIVIAL** | 1 | Typo, config, rename, obvious fix | `/quick` | Skip |
| **SIMPLE** | 1-3 | Clear requirements, single subsystem | Plan Mode | Offer after implementation |
| **MODERATE** | 4-5 | Clear pattern, single subsystem | `/orchestrate` (SIMPLE tier) | Recommended |
| **COMPLEX** | 6+ | Cross-cutting, architectural decisions | `/orchestrate` (COMPLEX tier) | Automatic |
| **FULLSTACK** | Any | Backend + frontend changes | `/orchestrate` + CONTRACT | Automatic (focus: enums/API) |
| **PRIOR FAIL** | Any | Re-attempt of a BLOCKED issue | `/orchestrate` + failure context, or `/codex:rescue` | Automatic |

**Modifiers:**
- **Multiple independent issues** → add `--parallel` (worktree isolation, separate tabs)
- **Interrupted workflow** → add `--resume` (skip completed phases)
- **Stuck after re-attempt** → try `/codex:rescue` before escalating to human

## Step 2: Announce Your Decision

State the routing decision briefly before starting:

> **Quick** — typo in README, 1 file, obvious fix.

> **Plan mode** — 2 files (entity_grid.py, config.py), clear requirements, high confidence.

> **Orchestrate (SIMPLE)** — 4 files, backend-only, clear pattern to follow. Codex review recommended.

> **Orchestrate (COMPLEX, fullstack)** — new module + schema + frontend integration. CONTRACT required. Codex adversarial review automatic.

> **Parallel** — Issues 42 and 57 are independent. Recommending `--parallel` in separate tabs.

The user can override: "just do it" (downgrade to quick/plan) or "orchestrate this" (upgrade).

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

5. After implementation, **offer** Codex review: "Want a cross-model review? I can run `/codex:adversarial-review`."

### Orchestrate

For MODERATE, COMPLEX, and FULLSTACK tasks. Full agent pipeline.

```
TRIVIAL tier:  MAP-PLAN → PATCH → PROVE-lite
SIMPLE tier:   MAP-PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE
COMPLEX tier:  MAP → PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE
```

Use `/orchestrate <issue-number>` with optional flags: `--with-tests`, `--resume`, `--parallel`.

## Step 3: Apply Codex Review

After the task is implemented (regardless of workflow), apply review based on risk:

| Risk Level | Codex Action | Command |
|------------|-------------|---------|
| **TRIVIAL** | Skip entirely | — |
| **SIMPLE** | Offer (don't force) | "Want a cross-model review?" |
| **MODERATE** | Run after implementation | `/codex:review --background` |
| **COMPLEX** | Run adversarial after PROVE | `/codex:adversarial-review --background` |
| **FULLSTACK** | Run with enum/API focus | `/codex:adversarial-review --background "Focus on: enum value mismatches, API contract compliance, access control"` |
| **PRIOR FAIL** | Run before commit | `/codex:adversarial-review --wait "Focus on: {prior root cause}"` |

### Codex Review Integration with Orchestrate

For MODERATE+ tasks routed through `/orchestrate`, Codex review runs **after PROVE passes**:

```
PATCH completes → PROVE passes → /codex:adversarial-review --background
                                         │
                                    findings?
                                    ├── No  → /pr
                                    └── Yes → fix issues → re-run PROVE → /pr
```

### Codex Rescue (Fallback)

When a task has been attempted and BLOCKED:

1. First re-attempt: `/orchestrate` with failure context injection (standard)
2. Still BLOCKED: `/codex:rescue "investigate and fix {description}"` (different model, different approach)
3. Still BLOCKED: escalate to human

## Examples

### Quick
- "Fix the typo in the README" → **Quick**, skip review
- "Update the env example with new variable" → **Quick**, skip review

### Plan Mode
- "Add feature flag to config.py" → **Plan mode**, offer review
- "Wire resolve_fact_key() into upsert_fact()" → **Plan mode**, offer review

### Orchestrate
- "Add validation endpoint with tests" → **Orchestrate SIMPLE**, recommended review
- "Create fact_vocabulary table + service + seed data + tests" → **Orchestrate COMPLEX**, automatic adversarial review
- "Implement payment form with backend API" → **Orchestrate FULLSTACK**, automatic review with enum/API focus

### Parallel
- "Implement issues 42, 57, and 63" → Assess independence:
  - 42 and 57 independent → `--parallel` in separate tabs
  - 63 depends on 42 → sequential after 42 merges

### Rescue
- "Issue 184 has failed twice" → `/codex:rescue` before re-attempting with Claude
