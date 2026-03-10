# Implementation Routing: Plan Mode vs Orchestrate

When implementing GitHub issues, choose the right workflow based on complexity and confidence.

## Decision Matrix

**Assess BEFORE entering any mode.** Read the issue, check files involved, then decide.

| Signal | Plan Mode | Orchestrate |
|--------|-----------|-------------|
| Files to modify | 1-3 | 4+ |
| Subsystems touched | 1 (backend OR frontend) | 2+ (cross-cutting) |
| Requirements clarity | Clear, specific | Ambiguous, needs investigation |
| Schema changes | None or simple ALTER | New tables + migrations + seed data |
| Test complexity | Add to existing test file | New test infrastructure needed |
| Dependencies | None or 1 prior issue | Multiple blocking issues |
| Estimated complexity | TRIVIAL / SIMPLE | MODERATE / COMPLEX |
| Confidence to complete | High (>80%) | Lower (<80%) |

**Rule of thumb:** If you can hold the entire change in your head and write it without extensive exploration, use plan mode. If you need to investigate, coordinate across files, or might get blocked — use orchestrate.

## Plan Mode Flow

1. Enter plan mode (`EnterPlanMode`)
2. Explore codebase, read relevant files
3. Write implementation plan to plan file
4. Exit plan mode — present plan with options:

**CRITICAL — Always present these options after showing the plan:**

```
Options:
1. "Compact and implement" (Recommended) — Compact context and implement the plan
2. "Implement now" — Implement immediately without compacting
3. "Revise plan" — Adjust the approach before implementing
```

The top option should always be "Compact and implement" with "(Recommended)" — this clears context overhead from planning exploration before the implementation pass, giving maximum context for coding.

## Orchestrate Flow

Use `/orchestrate <issue-number>` which runs the full MAP → PLAN → PATCH → PROVE pipeline with agent spawning and artifact tracking.

## Announce Your Decision

When starting an issue, state your routing decision briefly:

> **Plan mode** — 2 files (entity_grid.py, config.py), clear requirements, high confidence.

or

> **Orchestrate** — new service module + schema + integration into 3 existing files + tests. Need structured investigation.

Do NOT ask the user which mode to use — make the call and state it. The user will see the decision in the plan or orchestrate output and can override if they disagree.

## Examples

### Plan Mode
- "Add feature flag to config.py" (1 file, obvious)
- "Wire resolve_fact_key() into upsert_fact()" (2 files, clear integration point)
- "Fix bug in direct_fact_lookup regex" (1 file, targeted fix)
- "Add 3 new seed vocabulary entries" (1 file, data addition)

### Orchestrate
- "Create fact_vocabulary table + service + seed data + tests" (new module, 5+ files)
- "Implement migrate_fact_keys() with conflict resolution" (touches schema, service, audit, tests)
- "Full Phase 1 vocabulary foundation" (entire phase, 8+ files)
- "Redesign extraction pipeline with vocabulary constraints" (cross-cutting, multiple services)
