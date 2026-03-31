# Agent System Overview

When you run `/orchestrate`, a team of specialized agents handles your issue. Each agent has one job — investigate, plan, implement, or verify. Only one agent (PATCH) writes code. The rest are read-only, which means they can't break anything while they work.

## Agent Roles

| Agent | Phase | Role | Read-Only? | Target / Max Lines |
|-------|-------|------|------------|-------------------|
| MAP | 1 | Investigator (COMPLEX pipeline only) | Yes | 150 / 200 |
| MAP-PLAN | 1+2 | Investigator + Architect (TRIVIAL/SIMPLE pipeline) | Yes | 400 / 500 |
| PLAN | 2 | Architect (COMPLEX pipeline only) | Yes | 400 / 500 |
| TEST-PLANNER | 2 | Test matrix designer | Yes | 250 / 350 |
| CONTRACT | 2.5 | Interface designer (fullstack) | Yes | 200 / 300 |
| PLAN-CHECK | 2.8 | Plan validator | Yes | 80 / 120 |
| PATCH | 3 | Implementer | **No** | 300 / 400 |
| PROVE | 4 | Verifier + outcome recorder | Metrics only | 250 / 350 |

!!! warning "Separation of Concerns"
    Only PATCH writes code. Only PROVE records metrics. Investigation agents must never start implementing. Verification agents must never start fixing.

## Pipeline Flow

!!! info "Pipeline tiers vs routing tiers"
    This page describes the **pipeline tiers** — which agents run inside `/orchestrate`. For the full **routing model** (how tasks are classified and directed to `/quick`, Plan Mode, or `/orchestrate`), see the [Orchestrate Pipeline](../workflow/orchestrate.md) page.

When `/orchestrate` runs, it selects one of three pipeline tiers:

```
TRIVIAL pipeline:  MAP-PLAN ─────────────────────────────── PATCH ── PROVE-lite
SIMPLE pipeline:   MAP-PLAN ── [TEST-PLANNER] ── CONTRACT* ── PLAN-CHECK ── PATCH ── PROVE
COMPLEX pipeline:  MAP ── PLAN ── [TEST-PLANNER] ── CONTRACT* ── PLAN-CHECK ── PATCH ── PROVE

* = mandatory for fullstack only
[ ] = optional, enabled with --with-tests
```

```
                  +----------------+
                  | /orchestrate   |
                  +-------+--------+
                          |
                +---------+---------+
                | Select Pipeline   |
                +---------+---------+
           +----------+----------+----------+
           v          v                     v
     TRIVIAL       SIMPLE              COMPLEX
     pipeline      pipeline            pipeline
           |          |                     |
       MAP-PLAN   MAP-PLAN             MAP -> PLAN
           |          |                     |
           |     CONTRACT* / PLAN-CHECK  CONTRACT / PLAN-CHECK
           |          |                     |
        PATCH      PATCH                 PATCH
           |          |                     |
      PROVE-lite   PROVE                 PROVE
```

## Artifact Chains and Validation

Each agent produces a named artifact following the pattern `{agent}-{issue}-{mmddyy}.md` stored in `.agents/outputs/`. Every agent validates that its required predecessor artifact exists before starting work.

| Agent | Required Predecessor | Stops If Missing? |
|-------|---------------------|-------------------|
| MAP / MAP-PLAN | None (first agent) | N/A |
| PLAN | MAP artifact | Yes |
| TEST-PLANNER | MAP or MAP-PLAN | Yes |
| CONTRACT | PLAN or MAP-PLAN | Yes |
| PLAN-CHECK | PLAN or MAP-PLAN; CONTRACT if fullstack | Yes |
| PATCH | PLAN or MAP-PLAN; CONTRACT if fullstack; PLAN-CHECK | Yes |
| PROVE | PATCH artifact | Yes |

```
map-plan-184-030826.md
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

    All agents inherit from `_base.md` (v3.0), which provides:

    **Pre-flight checks** -- Before any work begins, agents load learned failure patterns (via MCP `failure_patterns()` or file fallback), search for similar past artifacts, and verify project constraints.

    **Artifact naming** -- `{agent}-{issue}-{mmddyy}.md` in `.agents/outputs/`.

    **Size compliance** -- Each agent has target and max line counts. Artifacts over max must be compressed before submission using a priority checklist: replace code quotes with line references, remove restated acceptance criteria, consolidate duplicates, remove appendices.

    **Verification commands** -- Standardized gates for backend (`ruff check . && pytest -q`) and frontend (`npm run lint && npm run build`).

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
"agent_versions": {"map-plan": "1.0", "patch": "1.2", "prove": "1.3"}
```

??? info "Root cause classification codes"

    ## Root Cause Classification

    Failures are classified using 12 canonical root cause codes. These codes feed back into the learning loop: `/learn` clusters failures by root cause, extracts prevention patterns, and updates agent definitions.

    !!! tip "See also"
        For the complete taxonomy with descriptions, typical causes, and detection agents, see [Failure Patterns -- Full Root Cause Taxonomy](../learning/failure-patterns.md#full-root-cause-taxonomy).
