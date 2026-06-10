---
paths: ["**/specs/**", "**/db/migrations/**", "**/.agents/**"]
---

# Spec Schema Collision Check — Exhaustive Grep Before Locking

**When a spec drops, renames, consolidates, OR EXTENDS a database
table, enum, or CHECK constraint:** run an exhaustive grep for every
SQL site against the target BEFORE submitting V1.0 for review. Then
cross-reference every shipped column / enum value the spec is
extending to prevent silent collisions.

This rule generalizes the buddy-local lesson
`feedback_spec_grep_every_sql_site.md` and adds the
"extension collision" half learned during the 2026-06-03 R1 review.

---

## When this rule fires

Your spec is doing any of:

- **Drop / Rename / Consolidate** — removing or renaming an existing
  table, column, type, or CHECK value.
- **Extend** — adding a new column to an existing table, adding a new
  value to a CHECK constraint or enum, or adding an index that names a
  field a sibling spec might already index.

The 2026-05-24 Person Consolidation V1 incident covered the first
class. The 2026-06-03 Workspace V1 + AggregateKanban V1 R1 review
proved the second class (extension) is just as failure-prone:
collisions and missed-shipped-values would have caused immediate
migration failure on Supabase.

---

## The two-part procedure

### Part 1 — SQL-site grep (for drops / renames / consolidations)

For every table / type the spec drops, renames, or consolidates:

```bash
# 1a — queries against the target
grep -rn --include='*.py' --include='*.ts' --include='*.tsx' \
    "FROM <table>\b\|JOIN <table>\b\|UPDATE <table>\b\|INSERT INTO <table>\b\|DELETE FROM <table>\b" \
    src/ > /tmp/sql-audit-<table>.txt

# 1b — application-layer DDL that resurrects the target
# (added 2026-06-05 after buddy #1766 — migration dropped a column
# but `_ensure_schema()` in app code recreated it on every pool acquire)
grep -rn --include='*.py' --include='*.ts' --include='*.go' \
    -E "CREATE TABLE IF NOT EXISTS <table>|ALTER TABLE <table>.*ADD COLUMN.*<column>|CREATE INDEX IF NOT EXISTS.*ON <table>|DO \$\$.*<table>" \
    src/ app/ server/ > /tmp/ddl-audit-<table>.txt
```

Categorize each hit:
- **IN-SCOPE** — already covered by some spec phase / PR.
- **OUT-OF-SCOPE** — needs spec expansion OR a follow-up issue.
- **DDL RESURRECTION** (from 1b) — **immediately blocking**. The migration's
  DROP will be silently undone on every server boot. Either delete the
  in-code DDL block AND coordinate the migration drop, OR keep the
  application-layer DDL and skip the migration. NEVER both. See companion
  rule `~/.claude/rules/no-app-layer-ddl.md`.

If OUT-OF-SCOPE > 0, **expand the spec OR file follow-up issues before
locking**. Don't assume "the audits got it all" — implicit topic
scoping is the failure mode that birthed this rule.

### Part 2 — Shipped-state collision check (for extensions)

**EXHAUSTIVENESS REQUIREMENT** (post-2026-06-03 lesson — repeat
incidents proved load-bearing). For every table the spec touches,
inventory the **FULL** shipped column list BEFORE proposing any
addition. Do not grep only the columns you think you're adding —
grep every column the spec mentions ANYWHERE (including comments,
type declarations, voice tool schemas, frontend types).

```bash
# Step 1: list EVERY column shipped on each table the spec mentions.
table_name=tasks  # repeat for every table cited in the spec
psql "$DATABASE_URL" -c "\d $table_name"

# Or read from migration history (offline):
grep -rn "$table_name" db/migrations/ scripts/init-db.sql | grep -E "ADD COLUMN|CREATE TABLE|priority|kind|status" | sort -u
```

Then grep the spec for EVERY column name it touches:

```bash
spec_file=specs/<feature>.md
grep -oE '\`[a-z_][a-z0-9_]*\`' "$spec_file" \
    | sort -u \
    | grep -v '^\`\(specs\|src\|db\|frontend\|backend\|tests\|docs\)' \
    > /tmp/spec-tokens.txt

# Cross-check every token in /tmp/spec-tokens.txt against the
# shipped column list. Any token that matches a shipped column =
# potential collision; verify the shape (type, enum values, CHECK,
# default) before approving the spec's usage.
```

For each column / enum value / CHECK clause your spec proposes adding:

| Check | If yes |
|---|---|
| Does an existing column already exist with the same role? | Reuse it (e.g., `tasks.kanban_blocker` exists; don't add `blocked_on`). Document the reuse decision. |
| Does an existing enum value cover the case? | Reuse it; don't add a duplicate-by-meaning value. |
| Does an existing column have a CONFLICTING shape? (e.g., your spec proposes `priority: low/medium/high/urgent` but shipped is `low/normal/high/urgent`) | Either translate at the boundary OR change the spec to match shipped. **Don't write the shipped column with the new shape — the CHECK will reject it at insert time.** |
| If you're REWRITING a CHECK constraint (DROP + ADD), does your replacement preserve ALL currently-allowed values? | If not, the migration WILL fail on existing rows with the dropped value. Either keep the dropped value OR add a data-migration step. |
| Does the FK column you're adding already have an index via a multi-column composite? | If yes, your new single-column index is redundant. |
| Does a sibling spec (in the same V1 wave) ALSO touch this table? | Coordinate: enumerate columns added by ALL sibling specs before adding yours. (2026-05-24 PersonConsolidation V1 added `tasks.assignee_entity_id`; an unrelated spec drafted before that migration landed would have missed it.) |

**The 2026-06-03 R3 lesson: the grep is exhaustive ONLY if it covers
EVERY column the spec mentions, not just the columns the spec is
proposing to add.** A `priority` enum collision is a CHECK collision
even when the spec doesn't propose adding a `priority` column —
because the spec INSERTS into that column from another source. Same
for `assignee`-shaped fields, `status`-shaped fields, any column the
spec writes-through from another table.

---

## What this rule would have prevented

**2026-05-24 Person Consolidation V1 (Part 1 incident):** 8 PRs +
26 migrations shipped consolidating `relationships` → `entity`. After
"complete," found 6 subsystems still querying the dropped table
across 8 source files, ~20 live SQL sites. Recovery cost: 7 follow-up
PRs + 5 expert audits. Would-have-been-prevented cost: 1 day of grep
+ 1 day of spec expansion.

**2026-06-03 AggregateKanban V1 R1 (Part 2 incidents):**

- **K1** — Spec rewrote `tasks_kind_check` as
  `('todo', 'mission', 'agent_job')` from memory. Missions V1 actually
  shipped `('todo', 'mission', 'agent_job', 'initiative')`. Migration
  would have failed on any `initiative` row.
- **K2** — Spec added `tasks.blocked_on` for waiting-column reason.
  PM V1 already shipped `tasks.kanban_blocker` for exactly this role.
  Two columns would coexist with overlapping meaning.
- **K4** — Spec declared `WorkerState =
  'queued' | 'running' | 'paused' | 'completed' | 'failed' |
  'cancelled'`. Orchestration V1 actually ships 7 values including
  `reaped`. Spec's TypeScript type would reject valid responses.
- **K6** — Spec used `project_slug` filter without resolving how mission
  rows join to projects (PM V1 uses `tasks.project_id`; Missions V1
  carries project association through `mission_meta`). The filter
  would return wrong rows OR no rows for missions.

All four were preventable by running Part 2 against PM V1, Missions
V1, and Orchestration V1 schemas.

---

## How to apply during the four spec-authoring phases

| Phase | Action |
|---|---|
| Drafting (before §3 self-review) | Run Part 1 + Part 2 for every table/enum the spec touches. Cite results in the spec's Migration Risk section. |
| §3 self-review (this rule's parent) | This rule's Check 2 in `spec-self-review.md` re-invokes the procedure. |
| R1 / R2 / R3 adversarial review | Treat "Coverage gap — SQL sites against `<table>` not addressed" OR "Shipped-state collision against `<existing>`" as BLOCKING findings. |
| Pre-merge (after PR ships) | Re-run Part 1 against the current state of `src/`. Any hit is a blocker — either fix in the PR or file a follow-up + add a regression test. |

---

## Anti-patterns

- ❌ "The expert audits covered the schema" — implicit scoping leaves
  gaps. Audits cover what they're asked to cover.
- ❌ "I remembered the column list" — schema drifts; memory doesn't.
  The 2026-06-03 R1 K1/K4 collisions both came from drafting from memory.
- ❌ "We'll find issues when PRs reach PROVE" — PROVE runs against the
  current schema, not the migrated schema. Schema drift is invisible
  until migrations apply.
- ❌ "The constraint dropped a deprecated value" — every shipped value
  is in use somewhere until proven otherwise via Part 1 grep.

---

## Companion files

- `~/.claude/rules/spec-self-review.md` — invokes this rule as Check 2.
- `~/.claude/rules/spec-review-workflow.md` — overall spec workflow (R1-R3).
- `~/.claude/projects/.../memory/feedback_spec_grep_every_sql_site.md`
  — buddy-local back-reference to the 2026-05-24 incident.
- `~/projects/buddy/.agents/outputs/r1-root-cause-analysis.md` —
  2026-06-03 R1 root-cause analysis covering K1/K2/K4/K6.

## How this rule was born

This rule has TWO origin incidents:

1. **2026-05-24 Person Consolidation V1.** Project-local lesson
   captured as `feedback_spec_grep_every_sql_site.md` (buddy memory).
   Covered drops/renames/consolidations.
2. **2026-06-03 Workspace V1 + AggregateKanban V1 R1.** Extension
   collisions surfaced. Project-local lesson would have been
   `feedback-spec-schema-extension-collision-check.md` — instead, both
   lessons promoted to a single global rule here.

The promotion happened because the buddy-local memory was invisible
to other projects, so the lesson was at risk of being relearned
elsewhere. Documented promotion path lives in
`~/.claude/rules/memory-promotion.md` per Proposal 5 of the
2026-06-03 corrective-proposals doc.
