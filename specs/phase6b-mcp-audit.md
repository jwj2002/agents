# Phase 6B — Knowledge MCP Consumer Audit

> Investigation output for A-011. Inventories every caller of
> `mcp__knowledge__*` and decides per tool: **PORT** (to CLI),
> **KEEP** (on MCP), or **KILL** (no callers, drop).

**Status:** Complete 2026-05-07.
**Result:** 5 of 20 tools have real callers; 15 are dead surface.
**Implication:** Phase 6C archival is small once 4 sub-PRs land.

---

## Methodology

Read-only investigation:

1. Inventoried all 20 tools registered by `~/agents/knowledge-mcp/index.ts`
   (one `server.tool(...)` block per tool).
2. Greppped `mcp__knowledge__<tool>` across:
   - `claude-config/skills/**/SKILL.md`
   - `claude-config/commands/**/*.md`
   - `claude-config/agents/**/*.md`
   - `claude-config/hooks/`, `claude-config/rules/`, `claude-config/templates/`
   - `~/.claude/plugins/cache/`, `~/.claude/plugins/marketplaces/`
   - `~/.claude.json`, `~/.claude/settings*.json`,
     `~/agents/claude-config/settings*.json`
3. For each hit, read the consumer to distinguish **programmatic call**
   (skill/command instructs Claude to invoke the MCP tool) from
   **doc reference** (skill mentions the tool by name in prose without
   asking Claude to call it).
4. For commands without MCP refs but in scope of "knowledge consumer"
   (`/learn`, `/discover-patterns`, `/metrics`), read end-to-end to
   confirm they read filesystem directly, not via MCP.

---

## Tool inventory (20)

```
get_patterns                    get_dashboard
get_pattern_detail              get_project_context
search_decisions                update_project_context
get_decision                    capture
get_learning_rules              triage_inbox
get_velocity                    get_inbox
save_decision                   get_journal
save_learning_rule              get_recent
save_velocity                   update_project_summary
get_project_summary             get_all_project_summaries
```

---

## Per-tool consumer matrix

| Tool | Real callers | Doc mentions | Decision |
|------|--------------|--------------|----------|
| **`get_inbox`** | `/inbox` SKILL.md | — | **PORT** |
| **`triage_inbox`** | `/inbox` SKILL.md | — | **PORT** |
| **`capture`** | `/capture` SKILL.md | dashboard SKILL.md (post-wrapper, doc only) | **PORT** |
| **`get_project_context`** | `/project` SKILL.md | — | **PORT** |
| **`update_project_context`** | `/project` + `/review-session` SKILL.md | — | **PORT** |
| `get_dashboard` | none (dashboard CLI bypasses) | — | **KILL** |
| `get_patterns` | none | — | **KILL** |
| `get_pattern_detail` | none | — | **KILL** |
| `search_decisions` | none | — | **KILL** |
| `get_decision` | none | — | **KILL** |
| `save_decision` | none (`/learn` does NOT call it; doc claim is aspirational) | dashboard SKILL.md (doc only) | **KILL** |
| `get_learning_rules` | none (SessionStart hook reads YAMLs directly) | — | **KILL** |
| `save_learning_rule` | none | — | **KILL** |
| `get_velocity` | none | — | **KILL** |
| `save_velocity` | none | — | **KILL** |
| `update_project_summary` | none | — | **KILL** |
| `get_project_summary` | none | — | **KILL** |
| `get_all_project_summaries` | none | — | **KILL** |
| `get_recent` | none | — | **KILL** |
| `get_journal` | none | — | **KILL** |

**Summary:** 5 PORT, 15 KILL, 0 KEEP. No tool has a property that
genuinely justifies the MCP layer (no long-running streams, no
structured responses Claude needs as objects rather than text — every
real caller passes the result back to the user as text).

### Notes on the doc-mentions

- The `/dashboard` skill (post-6A wrapper) mentions `mcp__knowledge__save_decision`
  and `mcp__knowledge__capture` in its **Notes** section as documented
  "update paths" for those data sources. After Phase 6B migration, the
  notes need updating to reference the new CLIs (`capture` instead of
  `mcp__knowledge__capture`, etc.). This is a small documentation update,
  not a behavior change.
- `/learn` does NOT actually call `save_decision` despite the dashboard
  Notes implying so. `/learn` updates agent files (rules) directly. The
  Notes line is a forward-looking mention from when /learn was scoped,
  not a current invocation.

### Already filesystem-direct (no port needed)

Three commands the issue body listed as port candidates turn out to
already read/write files directly without going through MCP:

| Command | What it actually does |
|---------|------------------------|
| `/learn` | Reads `~/.claude/memory/failures.jsonl`, edits agent files in `claude-config/agents/`. No MCP. |
| `/discover-patterns` | Reads source files in cwd, writes `knowledge/patterns/pat-<slug>.yaml` directly. No MCP. |
| `/metrics` | Reads `metrics.jsonl` and aggregates. No MCP. |

These are already in the right shape. No work for them in Phase 6B/C.

---

## Migration plan (4 sub-PRs)

Each sub-PR ports one skill to a new Python CLI + thin wrapper, matching
the `dashboard` (#134/#136) and `action` patterns. After all four land,
the only programmatic callers of `mcp__knowledge__*` are gone and Phase 6C
can archive the server.

### Sub-action P-1: port `/capture`

**Scope:**
- New `~/agents/capture/cli.py` — `capture <text> [--project P] [--type T]`. Writes a row directly into `knowledge/knowledge.db`'s `inbox` table (the source of truth — see Phase 6A's revised pinned decision). Or writes a JSON sidecar if we're moving inbox to filesystem-native; pick one before writing code.
- New `~/agents/capture/tests/test_cli.py`.
- Replace `claude-config/skills/capture/SKILL.md` (39 lines) with a thin shell-out wrapper.

**Sizing:** SIMPLE — ~150 LOC + tests. One ACID-ish operation (append a row).

### Sub-action P-2: port `/inbox`

**Scope:**
- New `~/agents/inbox/cli.py` — `inbox` (list open), `inbox <id> --action done|dismiss|assign --project P`. Reads/writes `knowledge.db` inbox table.
- New tests.
- Replace `claude-config/skills/inbox/SKILL.md` (60 lines) with a thin shell-out wrapper.
- Probably extracts a small `lib/inbox_db.py` shared with `/capture` so the two CLIs use the same row I/O.

**Sizing:** SIMPLE — ~250 LOC + tests.

### Sub-action P-3: port `/project`

**Scope:**
- New `~/agents/project/cli.py` — `project <name>` (read), `project <name> --focus "..." --status X --add-blocker "..." --subscribe --unsubscribe ...` (write). Reads/writes `knowledge/projects/<name>.yaml` directly + manages `~/.claude/dashboard-subscriptions.json`.
- New tests.
- Replace `claude-config/skills/project/SKILL.md` (89 lines) with a thin shell-out wrapper.

**Sizing:** MODERATE — ~400 LOC + tests. Schema-aware writes to YAML; the picker/registration logic from action/cli.py probably moves into `lib/project_resolver.py` shared with action.

### Sub-action P-4: port `/review-session`

**Scope:**
- New `~/agents/review-session/cli.py` — reads `~/.claude/pending_focus_reviews.json`, computes proposed focus per project, presents with confirmation, calls `project` CLI to apply. Most logic is the proposal computation; the apply step is a delegation to `project` once P-3 lands.
- New tests.
- Replace `claude-config/skills/review-session/SKILL.md` (101 lines) with a thin shell-out wrapper.

**Sizing:** MODERATE — ~300 LOC + tests. Depends on P-3 landing first (uses the `project` CLI as the apply step).

### Sequencing

```
P-1 (capture) ─┐
               ├─ both touch inbox table; P-1 first lays down lib/inbox_db.py
P-2 (inbox)  ──┘
              \
               P-3 (project) — independent, but extracts lib/project_resolver.py
                             from action/cli.py; can run in parallel with P-1/P-2
                             \
                              P-4 (review-session) — gates on P-3
```

Reasonable shipping order: **P-1, then P-3 in parallel, then P-2, then P-4.**

---

## Phase 6C readiness — what's needed before archival

After the 4 sub-PRs above:

- [ ] All `mcp__knowledge__*` programmatic calls in `claude-config/skills/` and `claude-config/commands/` removed (replaced by shell-outs to the new CLIs).
- [ ] dashboard SKILL.md Notes section updated: `mcp__knowledge__save_decision` → no longer relevant (kill); `mcp__knowledge__capture` → `capture` CLI.
- [ ] One final pass to confirm no plugin / hook / external caller remains.
- [ ] Then A-012 (Phase 6C): move `~/agents/knowledge-mcp/` to
      `~/agents/_archived/knowledge-mcp/`, drop `knowledge` from
      `~/.claude.json` `mcpServers`, update `claude-config/install.sh`
      to stop trying to register it, update `PLAN.md` target architecture
      diagram (drop the Knowledge MCP box even if it was already
      conceptually dropped in Phase 6 — make it explicit).

---

## Risks & open questions for the migration sub-PRs

1. **Inbox storage decision deferred.** Currently SQLite-only
   (`knowledge.db` `inbox` table). Two options for the migration sub-PRs:
   - **(a) CLI reads/writes the SQLite table directly.** Cheapest. Schema:
     `CREATE TABLE inbox (id INTEGER PK, content TEXT, project TEXT, type TEXT, status TEXT, created_at TEXT, resolved_at TEXT);` — already exists.
   - **(b) Move inbox to filesystem-native (JSON or YAML per row).**
     Lets the CLI be db-free; matches the rest of the toolchain. ~30
     extra lines per CLI for the migration.

   Recommend **(a)** — pragmatic, keeps the sub-PRs small. The "inbox
   lives in db" exception was already documented in Phase 6A.

2. **`save_decision` dead but `/learn` may want it.** If `/learn` is
   ever updated to actually save decisions to a structured store, it
   should write `knowledge/decisions/D-NNN.yaml` directly (the canonical
   form), not call a port-of-MCP. No work needed in Phase 6B for this.

3. **`update_project_context` write semantics.** The MCP version takes
   structured updates (focus, next_steps as a list, etc.) and applies
   them. The new `project` CLI must replicate this carefully — partial
   updates only touch the named field; full-replace for arrays vs append
   needs an explicit flag (`--add-blocker` vs `--set-blockers`).
   Specify this in P-3's PR.

4. **`/review-session` is interactive.** The current skill prompts the
   user for y/n/r per project. The CLI needs an interactive mode. Pattern
   exists already (`action --interactive` from Phase 6A precursor).

---

## What we're NOT doing

- **Reviving or porting the 15 KILL tools.** They had no callers; bringing them along into the new CLI architecture would just preserve dead surface in a different language. If a future need arises, build it then; the YAMLs are still on disk and trivially readable.
- **Extracting a kitchen-sink "knowledge_lib".** Each CLI does its own focused YAML/db I/O. Shared utilities cross the boundary only if two CLIs need the same code (e.g., `lib/inbox_db.py` if P-1 and P-2 both touch the inbox table). Otherwise stay local.
- **Adding new behavior in any sub-PR.** Each is a re-platforming, not a feature add. Existing skill behavior is the contract.

---

## Action breakdown

After this audit lands, file:
- **A-015**: P-1 — port `/capture` to Python CLI
- **A-016**: P-2 — port `/inbox` to Python CLI (gates on A-015 if shared `lib/inbox_db.py`)
- **A-017**: P-3 — port `/project` to Python CLI
- **A-018**: P-4 — port `/review-session` to Python CLI (gates on A-017)

A-012 (Phase 6C archive) stays gated on all four landing.
