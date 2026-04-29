# Agent System Overview

When you run `/orchestrate`, a team of specialized agents handles your issue. Each agent has one job — investigate, plan, implement, or verify. Only one agent (PATCH) writes code. The rest are read-only, which means they can't break anything while they work.

## Agent Roster

There are **12 agent definitions** in `claude-config/agents/`. Nine participate in the orchestrate pipeline; three are dispatched by other commands (`/spec-review`, `/pr`).

### Pipeline Agents (9)

| Agent | Phase | Role | Read-Only? | Target / Max Lines |
|-------|-------|------|------------|-------------------|
| DISCUSS | 0.5 | Decision Capturer (optional, `--discuss`) | Yes | 80 / 120 |
| MAP | 1 | Investigator (COMPLEX pipeline only) | Yes | 150 / 200 |
| MAP-PLAN | 1+2 | Investigator + Architect (SIMPLE pipeline) | Yes | 400 / 500 |
| PLAN | 2 | Architect (COMPLEX pipeline only) | Yes | 400 / 500 |
| TEST-PLANNER | 2 | Test matrix designer | Yes | 250 / 350 |
| CONTRACT | 2.5 | Interface designer (fullstack) | Yes | 200 / 300 |
| PLAN-CHECK | 2.8 | Plan validator (COMPLEX pipeline only) | Yes | 80 / 120 |
| PATCH | 3 | Implementer | **No** | 300 / 400 |
| PROVE | 4 | Verifier + outcome recorder | Metrics only | 250 / 350 |

### Dispatched Agents (3)

| Agent | Dispatched By | Role | Read-Only? |
|-------|---------------|------|------------|
| spec-reviewer | `/spec-review` | Spec analysis and gap classification | Yes |
| plan-checker | `/orchestrate` (COMPLEX) | Plan validator (alias for PLAN-CHECK) | Yes |
| pr-fresh-reviewer | `/pr` | Pre-merge fresh-eyes diff review | Yes |

Plus the shared `_base.md` definition (not an agent itself, but inherited by all).

!!! warning "Separation of Concerns"
    Only PATCH writes code. Only PROVE records metrics. Investigation agents must never start implementing. Verification agents must never start fixing.

## Pipeline Flow

!!! info "Pipeline tiers vs routing tiers"
    This page describes the **pipeline tiers** — which agents run inside `/orchestrate`. For the full **routing model** (how tasks are classified and directed to `/quick`, Plan Mode, or `/orchestrate`), see the [Orchestrate Pipeline](../workflow/orchestrate.md) page.

When `/orchestrate` runs, it selects one of two pipeline tiers. TRIVIAL classifications are rejected — `/orchestrate` redirects them to `/quick` (no pipeline).

```
SIMPLE pipeline:   [DISCUSS] ── MAP-PLAN ── [TEST-PLANNER] ── CONTRACT* ── PATCH ── PROVE
COMPLEX pipeline:  [DISCUSS] ── MAP ── PLAN ── [TEST-PLANNER] ── CONTRACT* ── PLAN-CHECK ── PATCH ── PROVE

* = mandatory for fullstack only
[ ] = optional, enabled with --with-tests or --discuss
```

PLAN-CHECK was removed from the SIMPLE pipeline in v5 — the cost of a separate validation phase did not justify the savings on small changes. PATCH catches plan defects fast enough on SIMPLE work, and Codex adversarial review (post-PROVE) picks up the rest. COMPLEX retains PLAN-CHECK because the cost of a botched multi-file PATCH is much higher.

```
                  +----------------+
                  | /orchestrate   |
                  +-------+--------+
                          |
                  +-------+--------+
                  | Classify Tier  |
                  +-------+--------+
              +-----+-----+-----+
              v           v     v
          TRIVIAL       SIMPLE  COMPLEX
              |           |       |
         [reject;        |  [DISCUSS]
          tell user      |       |
          to use     [DISCUSS] MAP -> PLAN
          /quick]        |       |
                     MAP-PLAN  CONTRACT* / PLAN-CHECK
                         |       |
                     CONTRACT* PATCH
                         |       |
                       PATCH   PROVE
                         |
                       PROVE
```

## Artifact Chains and Validation

Each agent produces a named artifact following the pattern `{agent}-{issue}-{mmddyy}.md` stored in `.agents/outputs/`. Every agent validates that its required predecessor artifact exists before starting work.

| Agent | Required Predecessor | Stops If Missing? |
|-------|---------------------|-------------------|
| DISCUSS | None (optional first agent) | N/A |
| MAP / MAP-PLAN | None (or DISCUSS artifact) | N/A |
| PLAN | MAP artifact | Yes |
| TEST-PLANNER | MAP or MAP-PLAN | Yes |
| CONTRACT | PLAN or MAP-PLAN | Yes |
| PLAN-CHECK | PLAN; CONTRACT if fullstack (COMPLEX only) | Yes |
| PATCH | PLAN or MAP-PLAN; CONTRACT if fullstack; PLAN-CHECK if COMPLEX | Yes |
| PROVE | PATCH artifact | Yes |

SIMPLE artifact chain:

```
map-plan-184-030826.md
    |
    +-- contract-184-030826.md (if fullstack)
            |
            +-- patch-184-030826.md
                    |
                    +-- prove-184-030826.md
```

COMPLEX artifact chain:

```
map-184-030826.md
    |
    +-- plan-184-030826.md
            |
            +-- contract-184-030826.md (if fullstack)
                    |
                    +-- plan-check-184-030826.md
                            |
                            +-- patch-184-030826.md
                                    |
                                    +-- prove-184-030826.md
```

!!! note "Blocking on Missing Artifacts"
    If PATCH detects fullstack work but cannot find a CONTRACT artifact, it stops immediately with `BLOCKED: CONTRACT artifact required for fullstack`. No assumptions, no proceeding without explicit input.

??? info "Shared agent behaviors (_base.md)"

    ## Shared Behaviors from _base.md

    All agents inherit from `_base.md` (v4.1, 265 lines — trimmed from 399 in PR #97). It provides:

    **Pre-flight checks** -- Before any work begins, agents load learned failure patterns (via MCP `failure_patterns_v1()` or file fallback), search for similar past artifacts, and verify project constraints.

    **Artifact naming** -- `{agent}-{issue}-{mmddyy}.md` in `.agents/outputs/`.

    **Size compliance** -- Each agent has target and max line counts. Artifacts over max must be compressed before submission using a priority checklist: replace code quotes with line references, remove restated acceptance criteria, consolidate duplicates, remove appendices.

    **Verification commands** -- Standardized gates for backend (`ruff check . && pytest -q`) and frontend (`npm run lint && npm run build`). The full command catalog now lives in `claude-config/snippets/verify-commands.md`; `_base.md` references the snippet rather than enumerating commands inline.

    **AGENT_RETURN directive** -- Every agent must end output with `AGENT_RETURN: {filename}` to signal completion to the orchestrator.

    **Failure context awareness** -- When spawned with a `## Prior Failure` block, the agent applies the prevention recommendation before starting and explicitly verifies the prior failure point is addressed.

    **Escalation protocol** -- Agents stop and report to the orchestrator if complexity seems wrong, information is missing, constraints would be violated, or scope is ambiguous.

## Agent Versioning

All agents include `version: X.Y` in their YAML frontmatter.

| Change Type | Version Bump | Examples |
|-------------|-------------|----------|
| Minor (1.0 to 1.1) | Pattern additions, wording changes | Add new enum check reminder |
| Major (1.0 to 2.0) | Restructure, new sections, workflow changes | Add Mandatory Verification Protocol |

Versions are recorded in `metrics.jsonl` via the `agent_versions` field, enabling correlation between agent versions and success rates through the `/metrics` command.

```json
"agent_versions": {"map-plan": "1.1", "patch": "1.5", "prove": "1.5"}
```

??? info "Root cause classification codes"

    ## Root Cause Classification

    Failures are classified using 12 canonical root cause codes. These codes feed back into the learning loop: `/learn` clusters failures by root cause, extracts prevention patterns, and updates agent definitions.

    !!! tip "See also"
        For the complete taxonomy with descriptions, typical causes, and detection agents, see [Failure Patterns -- Full Root Cause Taxonomy](../learning/failure-patterns.md#full-root-cause-taxonomy).
