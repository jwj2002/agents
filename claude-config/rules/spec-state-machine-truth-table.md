---
paths: ["**/specs/**", "**/.agents/**"]
---

# Spec State-Machine Truth Table — Mandatory For Multi-Section Contracts

**When a spec defines a state contract that spans 2 or more sections,
write the truth table explicitly in the spec.** Every cell must be
filled or marked N/A with reason.

This rule covers a class of spec defects that
`spec-review-workflow.md` §3.2 ("execution-order trace") doesn't catch
because §3.2 is single-call-path-focused. Multi-section state
contracts contradict each other not via execution flow but via
implicit assumptions about what each section means by "state."

---

## When this rule fires

Your spec has 2 or more sections that interact via state. Common shapes:

| Shape | Sections that need to agree |
|---|---|
| Voice tool payload → frontend dispatcher → WS frame | Tool schema §, frontend action handler §, WS frame contract § |
| Backend insert → supervisor transition → external state mapping | Schema §, supervisor hook §, view-type endpoint § |
| Phase enum → derived display state → user mutation | Domain phase enum §, view derivation §, mutation API § |
| Initial state → conflict-resolution algorithm → fallback | Default state §, conflict resolution §, fallback handling § |

If you can describe your spec with the phrase "and then it
transitions to..." across 2 or more `##` headings, **write the truth
table.**

---

## The truth table format

A truth table is a markdown table whose **rows are states** (or
transitions) and whose **columns are perspectives** (each `##`
section that touches the state).

Required columns:
1. **State / Transition** — the row name (e.g., `queued`, or
   `voice → frontend → WS`).
2. **One column per section the state touches** — what THIS section
   says happens / what value this state has.
3. **Notes** — any cell that's load-bearing or non-obvious.

Every cell must be:
- Filled with the verbatim section's stated value, OR
- Marked **N/A** with a one-line reason why the section doesn't apply.

Empty / "TBD" / "see §X" cells fail the check.

---

## Worked example — agent-job kanban column (would have prevented R1 K3)

The AggregateKanban V1 spec said in §5.1: "When `start_job` spawns
with `project_slug`, insert a `tasks` row at `kanban_column='doing'`."
It also said in §5.2: "worker_state→column mapping: `queued → inbox`,
`running → doing`." `start_job` actually creates `worker_jobs` rows in
state `queued`. The spec contradicted itself.

The truth table that would have surfaced this BEFORE R1:

| worker_state | §5.1 says column is | §5.2 says column is | §7.1 KanbanCard kind | §AC1 says | Resolved value |
|---|---|---|---|---|---|
| queued | `doing` (hardcoded insert) | `inbox` (mapping) | `agent_job` | `doing` | **CONFLICT** — pick one |
| running | n/a | `doing` | `agent_job` | n/a | `doing` |
| paused | n/a | `waiting` | `agent_job` | n/a | `waiting` |
| completed | n/a | `done` | `agent_job` | n/a | `done` |
| failed | n/a | `done` (badge: failed) | `agent_job` | n/a | `done` |
| cancelled | n/a | `done` (badge: cancelled) | `agent_job` | n/a | `done` |
| reaped | n/a | **MISSING** | **MISSING** in WorkerState type | n/a | **CONFLICT** — type rejects valid response |

Two `CONFLICT` rows visible in 5 minutes of table-writing. Without the
table, the spec author (me) read §5.1 + §5.2 + §7.1 + §AC1 in separate
passes and never noticed the queued-row contradiction.

---

## Worked example — nav-conflict resolution (would have prevented R1 W3)

Workspace V1 §8.3 said "frontend consumes `workspace_navigate` and
calls `setActiveTab` immediately." §8.5 said "user navigation within
500ms wins because Mavis navigate is briefly enqueued." The truth
table:

| Event sequence | §8.3 algorithm | §8.5 algorithm | Resolved |
|---|---|---|---|
| Mavis nav at t=0, no user action | setActiveTab(target) immediately | enqueue; apply at t=500ms | **CONFLICT** |
| Mavis nav at t=0, user nav at t=100ms | switched at t=0, then user wins → switched back at t=100ms | enqueue at t=0; user-nav cancels enqueue at t=100ms; only user-nav applies | **CONFLICT** — UX is double-switch vs single-switch |
| Mavis nav at t=0, user nav at t=600ms | switched at t=0, switched again at t=600ms | applied at t=500ms, switched again at t=600ms | Same end state, different intermediate UX |
| Two Mavis navs at t=0 and t=300ms | both apply (no debounce) | first enqueued, second... what? | **UNDEFINED for §8.5** |

Three rows produce contradictions or undefined behavior. The truth
table makes them visible.

---

## How to write the truth table efficiently

1. **List the sections** that touch the contract. 2-4 is typical.
2. **List the states / transitions / inputs** as rows. Be exhaustive
   — every value the upstream type can produce.
3. **For each row × column cell**, copy the verbatim language from
   that section.
4. **Look for contradictions** — same cell, two different values is
   a blocker.
5. **Look for empty cells** — section doesn't address this state.
   Either add a clause to the section OR mark N/A with reason.
6. **Resolve the conflicts in-spec.** The table doesn't have to live
   in the spec body (it can live in a `__truth-tables.md` companion
   file), but the resolved values DO.

---

## When to skip

Single-section state machines (one `##` heading defines and uses the
state internally) do not need a truth table. Examples:
- A repository class with `_pending`/`_running`/`_done` private state.
- A frontend reducer that doesn't expose its internal state to
  another section.

If two readers can disagree about what state X means, write the
table.

---

## What this rule would prevent — beyond R1 W3 + K3

Across the 2026-06-03 R1 review:

- **W2** — `workspace_navigate` payload table (one row per tab x mode,
  columns: required selection fields, optional fields, default values).
- **W7** — Email mutation table (one row per endpoint, columns:
  optimistic update?, provider write-through?, rollback shape?, audit
  required?).
- **K5** — Mission proposal kanban card table (one row per proposal
  state, columns: has task_id?, KanbanCard.kind value?, can be
  rendered?, can be moved?).
- **K8** — Linked-ref mutation table (one row per linked-ref
  operation, columns: WS frame fired?, re-render trigger?, AC
  reference?).

All four were spec gaps that 5 minutes of truth-table writing would
have surfaced.

---

## How this rule was born

**2026-06-03 Mavis Workspace V1 + AggregateKanban V1 R1.** Five of 21
blocking findings (W2, W3, W7, K3, K5) were multi-section state
contradictions where each section read in isolation seemed correct
but the cross-section state machine contradicted itself.

Classified in
`~/projects/buddy/.agents/outputs/r1-root-cause-analysis.md` as
"Group C — process-too-weak." `spec-review-workflow.md` §3.2
("execution-order trace") wasn't strong enough because it focused on
single-call-path tracing, not on multi-section state shapes.

This rule fills the gap. Promoted to global from project-local lesson
per Proposal 3 of `r1-corrective-proposals.md`.

## Companion rules

- `~/.claude/rules/spec-self-review.md` — calls this rule out in Check 3.
- `~/.claude/rules/spec-review-workflow.md` §3.2 — single-call-path
  execution trace (the discipline this rule complements).
- `~/.claude/rules/spec-schema-collision-check.md` — for schema-level
  collisions (a different failure mode).
