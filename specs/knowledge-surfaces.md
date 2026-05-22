# Knowledge Surfaces — Authority Map & Scoping Rules

> **Status (2026-05-13)**: Two surfaces moved in the Path B migration
> (see `specs/path-b-migration.md`):
>
> - `knowledge/projects/<name>.yaml` → `<vault>/Projects/<name>.md` (Obsidian
>   markdown frontmatter). The legacy YAMLs are archived at
>   `_archived/projects-pre-pathb/`. `project/cli.py` now mutates the MD
>   frontmatter via `lib/obsidian_md.py`.
> - `knowledge/decisions/D-NNN.yaml` → `<vault>/Decisions/D-NNN.md` (MADR
>   format). The legacy YAMLs + `index.yaml` are archived at
>   `_archived/decisions-pre-pathb/`. `decision/cli.py` reshaped to write
>   the MADR markdown; no more `index.yaml` (replaced by Dataview queries).
>
> Every other surface in the table below is unchanged.
>
> **Historical context** (FINAL — 2026-05-07): Phase 6 follow-up. After
> collapsing the Knowledge MCP into filesystem-native CLIs, knowledge state
> was spread across multiple directories with no single source of truth doc.
> This spec mapped every surface to "authoritative for X / written by Y /
> read by Z," locked in the per-project vs. global scoping rules, and
> standardized a `schema_version` field for forward compatibility.

---

## TL;DR

| Surface | Scope | Status | Authoritative for |
|---|---|---|---|
| `<vault>/Projects/<name>.md` | per-project | ALIVE (Path B, since 2026-05-13) | project tracker (focus, host, client, kind, status, blockers, next_steps, open_questions, stack, repo_path, repo_remote). Frontmatter mutated by `project/cli.py`. `host:` declares which host owns the project. |
| `<vault>/Projects/_pulse/<project>--<host>.md` | per-(project, host) sidecar | ALIVE (Path B) | machine-derived state: last_commit, commits_24h/7d, open_actions/issues, branch hygiene. Written by `pulse refresh` exclusively (single-writer-per-host); never hand-edited. |
| `<vault>/Decisions/D-NNN.md` | per-project (`project:` frontmatter) | ALIVE (Path B) | architecturally significant decisions in MADR format. Frontmatter + body sections mutated by `decision/cli.py`. |
| `~/agents/_archived/projects-pre-pathb/<name>.yaml` | per-project | ARCHIVED — pre-Path-B history | (read for historical reference only; do not write) |
| `~/agents/_archived/decisions-pre-pathb/D-NNN.yaml` | per-project | ARCHIVED — pre-Path-B history | (read for historical reference only; do not write) |
| `knowledge/patterns/pat-<slug>.yaml` | global (no `project:` field) | CATALOG-ONLY — no live reader | reusable code patterns + lifecycle (pilot → validated) |
| `knowledge/learning-rules/LR-NNN.yaml` | global | DORMANT — no recent writer | failure-derived rules surfaced at SessionStart |
| `~/.claude/memory/patterns-critical.md` | global, per-machine | ALIVE — loaded by SessionStart | "Top 3 critical patterns" injection |
| `~/.claude/projects/<…>/memory/MEMORY.md` | per-Claude-session, per-machine | ALIVE — auto-memory | conversation-spanning user/feedback/project memories |
| `<repo>/ACTIONS.md` | per-repo | ALIVE — `action` CLI writes | open and recently-closed actions |
| `<repo>/specs/*.md` | per-repo | ALIVE — hand-edited | architectural decision docs (this file is one) |
| `<repo>/PLAN.md` | per-repo | ALIVE — hand-edited | phased delivery plan |
| `~/.claude/dashboard-subscriptions.json` | per-machine | ALIVE — `project --subscribe` writes | which projects this machine sees in `/dashboard` |
| `~/.claude/pending_focus_reviews.json` | per-machine | ALIVE — session-end hook writes | session activity awaiting focus update |
| `knowledge.db` (+ `.db-shm`, `.db-wal`) | DB | DEAD — dies in 6C | (no live readers; archived with knowledge-mcp/) |
| `knowledge/velocity/V-*.yaml` | per-project | DEAD — no writer or reader | (cancelled — drop) |
| `knowledge/project-summaries/` | empty | DEAD | (drop) |
| `knowledge/specs/` | orphan | DEAD — design docs from before | (move or drop in 6C cleanup) |

---

## Audit findings (2026-05-07)

| Surface | File count | Most recent write | Notes |
|---|---|---|---|
| `knowledge/projects/` | 7 | 2026-05-06 | Schema: project, status, focus, next_steps, blockers, open_questions, specs, dependencies, updated_at, updated_by |
| `knowledge/decisions/` | 9 D-NNN + index.yaml | 2026-04-17 (D-098) | Already has `project:` field. Last written 20 days ago. **No writer in claude-config/skills/ or any CLI.** |
| `knowledge/patterns/` | 40+ pat-*.yaml | 2026-04-28 (mass restore) | No `project:` field. Rich lifecycle states. **SessionStart loads `patterns-critical.md` (hardcoded MD), not these YAMLs.** |
| `knowledge/learning-rules/` | 6 LR-NNN | 2026-04-07 (LR-006) | Schema: id, rule, source, confidence, applies_to, approved, created_at |
| `knowledge.db` (WAL alone is 4MB) | DB tables | 2026-05-06 (timestamp) | Phase 6B audit: 18/20 MCP tools have zero callers; remaining 2 are now ported. **Dies in 6C.** |
| `knowledge/velocity/` | 2 V-NNN | 2026-04-06 | No writer, no reader, drop. |
| `knowledge/project-summaries/` | 0 | — | Empty directory, drop. |
| `knowledge/specs/` | 2 *.md | 2026-04-28 (timestamp) | Old knowledge-base design docs from pre-Phase 6. **Not the same as `~/agents/specs/`.** Move or drop. |

**Two structural gaps to surface:**

1. **No writer for decisions.** Last `D-NNN.yaml` was 20 days ago. The `save_decision` MCP tool had zero callers in the Phase 6B audit (`specs/phase6b-mcp-audit.md`); the documented fallback is "hand-edit," and at the rate decisions are made, that's not happening. Without a writer the `decisions/` surface decays into a graveyard.
2. **No reader for the pattern catalog.** SessionStart hook loads `~/.claude/memory/patterns-critical.md` (a curated markdown file) but never opens `knowledge/patterns/*.yaml`. The lifecycle (`status: pilot|validated|deprecated`, `consecutive_successes` counter) is unused — patterns can be marked validated but nothing acts on the marking.

These are filed as follow-up actions (A-019, A-020). They are **out of scope for this spec PR**, which is decision-only.

---

## Scoping rules (FINAL)

These rules are observed in the existing data and codified here so future work doesn't drift.

### Per-project surfaces

A surface is **per-project** if its records are scoped to a single project's lifecycle.

| Surface | Mechanism |
|---|---|
| `<vault>/Projects/<name>.md` | Filename = project name. One file per project. (Path B; previously `knowledge/projects/<name>.yaml`.) |
| `<vault>/Decisions/D-NNN.md` | `project:` frontmatter field inside each MD (e.g. D-042 → `docketiq`). Cross-references via `linked.related_decisions`. (Path B; previously `knowledge/decisions/D-NNN.yaml` + `index.yaml`. Dataview queries replace the index.) |
| `<repo>/ACTIONS.md` | Lives in the project repo. |
| `<repo>/specs/`, `<repo>/PLAN.md` | Live in the project repo. |

**Rule for new decisions:** every `D-NNN.md` MUST have a `project:` frontmatter field. If a decision spans projects, list the primary project and reference others via `linked.related_decisions`.

### Global surfaces

A surface is **global** (cross-project) if its records describe knowledge that applies across multiple projects.

| Surface | Mechanism |
|---|---|
| `knowledge/patterns/pat-<slug>.yaml` | No `project:` field. Patterns are intentionally project-agnostic; `when_to_use` describes applicability. |
| `knowledge/learning-rules/LR-NNN.yaml` | No `project:` field. `applies_to` is a free-text scope (e.g. `"all projects with frontend + API"`). |
| `~/.claude/memory/patterns-critical.md` | Hardcoded "Top 3" curated for global injection. |

**Rule for new patterns:** never add a `project:` field. If a pattern is genuinely project-specific, it belongs in `<repo>/knowledge/patterns/` (per-repo via `/discover-patterns`), not in the agents-repo central catalog.

### Per-machine surfaces

These never get committed; they describe the local view, not shared knowledge.

| Surface | Why per-machine |
|---|---|
| `~/.claude/dashboard-subscriptions.json` | Each laptop subscribes to a different subset |
| `~/.claude/pending_focus_reviews.json` | Session-end hook writes from this machine's commit history |
| `~/.claude/projects/<…>/memory/MEMORY.md` | Auto-memory tied to this machine's Claude sessions |

These are intentionally NOT in `~/agents/` — they don't sync via git. This was the explicit Phase 6A decision and stays.

---

## Schema versioning (FINAL)

Every YAML form gets a `schema_version` field. Reasoning: the schemas WILL evolve (the `dependencies` and `specs` arrays in project YAMLs are already underused; pattern lifecycle may consolidate states). Without a version field, tooling can't tell v1 from v2 records, and migrations become guesswork.

### Decision

Add `schema_version: 1` as the **first non-comment field** of every record:

- `<vault>/Decisions/D-NNN.md` — frontmatter (Path B; previously `knowledge/decisions/D-NNN.yaml`)
- `knowledge/patterns/pat-*.yaml`
- `knowledge/learning-rules/LR-NNN.yaml`

Project notes (`<vault>/Projects/<name>.md`) intentionally **omit
`schema_version`** post-Path-B — the Obsidian frontmatter shape is
authoritative and Dataview queries that rely on stable field names would
break on a version bump anyway. Migration script `migrate-to-pathb.py`
drops `schema_version` from each project YAML when converting.

### Writer responsibility

- `lib/project_resolver.register_project()` (called by `project` CLI auto-register and by future scaffolders) must write `schema_version: 1` on creation.
- Any future decision-writer (A-019) must write `schema_version: 1`.
- `/discover-patterns` skill must write `schema_version: 1` in new pattern files.

### Backfill

Existing files get `schema_version: 1` injected at the top, in this PR's follow-up implementation work (separate from this decision doc, per the decision-first workflow).

### When to bump

- `schema_version` increments **only when fields are removed or their meaning changes**.
- Adding new optional fields → no bump.
- Renaming a field → bump.
- Changing a field's type or semantics → bump.

When bumping, writers must emit the new version; readers must accept both during a deprecation window (≥30 days).

---

## What stays / what dies

### Stays (alive or fixable)

| Surface | Action |
|---|---|
| `knowledge/projects/` | No change. Add `schema_version`. |
| `knowledge/decisions/` (D-NNN + index) | **Fix the writer gap** (A-019). Add `schema_version`. |
| `knowledge/patterns/` | **Fix the reader gap** (A-020). Add `schema_version`. |
| `knowledge/learning-rules/` | Reader: SessionStart already loads via state_manager (verify in A-020 work). Add `schema_version`. |
| `~/.claude/memory/patterns-critical.md` | Curated injection layer. Stays. |

### Dies (with Phase 6C archive, A-012)

| Surface | Disposition |
|---|---|
| `knowledge.db` + `.db-wal` + `.db-shm` | Archived with `~/agents/knowledge-mcp/` (A-012). No data migrated; the audit confirmed no live readers. |
| `knowledge/velocity/` | Drop directory. |
| `knowledge/project-summaries/` | Drop empty directory. |
| `knowledge/specs/` (the orphan one inside knowledge/) | Move surviving content (if any) to `~/agents/specs/` or drop. |
| `knowledge/sync.py`, `knowledge/schema.sql` | Drop with the MCP server in 6C. |
| `knowledge/.agents/`, `knowledge/.pytest_cache/`, `knowledge/__pycache__/` | Drop with the MCP server in 6C. |

These dispositions are bundled into the A-012 archival PR; not this spec.

---

## Follow-up actions (file separately)

These are scoped here so the gaps don't become permanent and the spec PR stays decision-only.

### A-019 — build a decision-writer

**Why:** the `decisions/` surface decays into a graveyard without a writer. Last D-NNN.yaml was 20 days ago.

**Options:**

- **(a)** New `decision` CLI: `decision new --project X --topic auth --title "..." --context "..."` → writes `knowledge/decisions/D-NNN.yaml` and updates `index.yaml`.
- **(b)** `--decide` subcommand on `action` CLI: reuses the YAML-write plumbing already there, plus the project resolver.
- **(c)** Lightweight `/decision` skill that prompts the user through fields and writes the YAML. (Most discoverable but heaviest to maintain.)

**Recommendation:** (a) — same shape as `action`/`project`/`dashboard`/`review-session`. Keeps the converged-pattern story clean.

**Sizing:** SIMPLE — ~250 LOC + tests. Reuses `lib/project_resolver.py`.

### A-020 — connect SessionStart to YAML patterns

**Why:** the `lifecycle` and `consecutive_successes` machinery in `knowledge/patterns/*.yaml` is theoretical until something reads it.

**Scope:** extend `claude-config/hooks/sessionstart_restore_state.py` to:

1. Read `knowledge/patterns/*.yaml` filtered by `tier: critical` AND `lifecycle.status in (validated, pilot)`.
2. Emit a compact summary into the SessionStart context (next to `patterns-critical.md`).
3. Keep the hardcoded `patterns-critical.md` as the curated injection (the YAMLs are richer reference, not replacement).

**Sizing:** SIMPLE — hook edit + one new function. Need to verify token budget impact (SessionStart aims for ~500 tokens total).

### A-021 — clean up the dead knowledge/ subdirs

**Why:** `velocity/`, `project-summaries/`, `knowledge/specs/` are confusing dead surfaces.

**Scope:** drop these in the same PR as 6C archival (A-012), since they're all retired together.

**Sizing:** TRIVIAL — `git rm -r`.

---

## Out of scope for this spec

- Cross-device project state (Phase 7 / A-013). Per-machine surfaces are intentional; the cross-device problem is a separate decision in `specs/cross-device-state.md` if/when that work happens.
- Splitting `<repo>/knowledge/patterns/` (per-repo) from `~/agents/knowledge/patterns/` (central) into a unified catalog. Today these are independent. If pattern fragmentation becomes a real pain, a future spec can address it.
- Migrating any data out of `knowledge.db` before 6C archive. The audit confirmed nothing in there is being read; the user can extract specific tables manually if anything is wanted.

---

## Acceptance

- [x] Audit captured (this doc).
- [x] Scoping rules formalized (per-project / global / per-machine).
- [x] `schema_version` decision recorded (start at 1; bump only on breaking changes).
- [x] Writer/reader gaps explicitly named (A-019, A-020).
- [x] Dead surfaces explicitly named for 6C cleanup (A-021).

## Sign-off

Decision-only. No code in this spec PR. Implementation rolls in:

- This PR (or a follow-up): `schema_version: 1` backfill across all alive forms + writer updates.
- A-019 PR: decision writer.
- A-020 PR: pattern-catalog reader at SessionStart.
- A-012 / A-021: drop dead surfaces alongside 6C archival.
