# agents — Consolidation Plan

> Living document. Tracks the multi-phase work to slim the Claude/Codex
> config and consolidate project-state tooling onto Knowledge MCP.

**Modeled on:** `~/projects/content-brain/PLAN.md`

---

## Why this exists

The agent infrastructure had grown to ~10k+ lines of meta-tooling spread
across two parallel project-tracking stacks (Knowledge MCP + Flotilla)
with overlapping responsibilities, plus a 60+ artifact Claude config
(sub-agents, commands, skills, hooks, rules). Daily friction was rising,
maintenance cost was outpacing the value being added, and the
"see context of all active projects" workflow required two services to
be running.

Goal: collapse to one source of truth for project state, slim the config
to artifacts that earn their cost, keep what compounds (Knowledge MCP,
Codex delegation, content-brain-style phase discipline).

## Architecture (target state)

```
                       ┌────────────────────┐
       /dashboard ───▶ │  Knowledge MCP     │  source of truth
                       │  (YAML in git)     │  decisions, patterns,
                       └─────────┬──────────┘  rules, project context
                                 │
                  + git/gh overlay per project
                  (last commit, open issues, captures)

                       ┌────────────────────┐
                       │  Codex delegation  │  parallel work,
                       │  (rescue/review)   │  reviews, rescue
                       └────────────────────┘
```

Multi-agent channels were dropped in Phase 2 (Option B). Codex delegation
is the converged multi-agent pattern.

Phase 6 will collapse the project-state interface to Python CLIs over
filesystem YAMLs and retire the Knowledge MCP server (TypeScript). After
Phase 6C, the diagram above simplifies to **YAMLs ← Python CLIs ← thin
Claude-skill wrappers + Codex delegation**.

Reference specs:
- `specs/phase0-usage-report.md` — what got measured, what didn't, why Phase 3 was deferred
- `specs/toolchain-consolidation.md` — Phase 6 decision record (Option 3: collapse to Python CLIs)

---

## Phase 0 — Measure usage ✅ DONE (2026-04-19)

Mined 90 days of `~/.claude/projects/**/*.jsonl` for slash command,
sub-agent, skill, hook, and Codex usage.

**Validated findings:**
- Codex: 1,379 invocations / 90d. Untouchable.
- Hooks: all 9 fire heavily (verify_completion 4,286×). Untouchable.

**Methodology gap:** sub-agent/command counting via `subagent_type` and
`<command-name>` only — missed the dispatch pattern where orchestrate calls
agents as `Task(description='MAP for issue N', ...)` against the
general-purpose agent. Phase 3 cuts deferred until a structured logger
exists.

---

## Phase 1 — Consolidate `/dashboard` to Knowledge MCP ✅ DONE (2026-04-19)

**What shipped:**
- `claude-config/skills/dashboard/SKILL.md` v5 — drops Flotilla API as a
  data source; uses Knowledge MCP for project state + `git`/`gh` overlay
  per project (resolved via `~/projects/{name}` convention).
- WIP / agent-work tracking dropped — no Flotilla equivalent worth
  re-adding. Use `git branch --list 'feature/*'` if a fallback is needed.
- Per-project graceful degradation when repo path doesn't follow convention.

**Exit criteria:**
- [x] Knowledge MCP is the only required service for `/dashboard` to render
- [x] Convention validated against active projects (flotilla, buddy,
      mymoney-dev, temper, content-brain) — all resolve correctly
- [x] Skill version bumped (v4 → v5) with notes

**Learnings:**
- Skill rewrite is non-destructive — Flotilla still runs, /dashboard just
  no longer queries it. Phase 2 is now safe to plan independently.
- `content-brain` lives at `~/projects/content-brain` but its github slug
  is `jwj2002/gpt-researcher` (forked) — origin URL parsing handles it
  correctly.

---

## Phase 2 — Channels decision ✅ DONE (2026-05-06) — Option B

**Decision:** Drop multi-agent channels. Archive Flotilla.

**Rationale:**
- 90 days of session history shows **0 real `channel-mcp` tool invocations**
  (`send_message`, `check_messages`, `report_status`).
- Flotilla central server was not running; `channel-mcp` was not registered
  in any `settings.json`. The infrastructure was effectively cold.
- Codex delegation (`/codex:rescue`, `/codex:adversarial-review`) — 1,379
  invocations over 90d per Phase 0 — is the converged multi-agent pattern.
  Channels was the speculative design that lost to it.
- Option A (slim Flotilla to transport-only) would have been ~1–2 days of
  cuts to keep a capability nothing was using. Net negative.

**What shipped:**
- `~/projects/flotilla` archived (moved to `~/projects/_archived/flotilla`).
- `channel-mcp` archived with the Flotilla repo (lived inside it).
- Knowledge MCP: `flotilla` project flipped to `done`; `agents` project
  blockers + channels-related open questions cleared.

**Exit criteria:**
- [x] Decision recorded with usage data.
- [x] Flotilla local clone archived (GitHub repo retained as history).
- [x] PLAN.md target architecture diagram updated (Channel MCP box dropped).
- [x] `/dashboard` continues to function — Phase 1 already unwired Flotilla.

---

## Phase 3 — Trim Claude config artifacts ⏸ DEFERRED

Original plan (12→6 sub-agents, 16→8 commands, etc) was guesswork-heavy
once the measurement methodology gap surfaced. Right move: add a
structured usage logger to the orchestrate skill (one JSONL line per
agent dispatch), let it accumulate, then revisit cuts with real data.

**Tasks (when revisited):**
- Add usage logger to orchestrate (write to `~/.claude/usage.jsonl`)
- Run for 30+ days
- Re-run audit with reliable signal
- Archive cold artifacts to `claude-config/_archived/`

---

## Phase 4 — Compress orchestrate pipeline ✅ DONE (2026-04-19)

**What shipped:**
- SIMPLE/MODERATE pipeline drops PLAN-CHECK. Default cost: 3 phases
  (MAP-PLAN → PATCH → PROVE) instead of 5–6.
- COMPLEX/FULLSTACK pipeline unchanged — full rigor retained where the
  failure cost justifies the cost.
- Codex adversarial review (post-PROVE, automatic for MODERATE+) covers
  what PATCH missed on SIMPLE work.
- Updated: `claude-config/skills/orchestrate/SKILL.md`,
  `ORCHESTRATE_REFERENCE.md`, `claude-config/rules/implementation-routing.md`

**Exit criteria:**
- [x] SIMPLE pipeline reflects new shape in all three files
- [x] Routing rule explains the rationale
- [x] Escape hatch documented (PATCH can create PLAN-CHECK on demand)

---

## Phase 6 — Toolchain consolidation (Python CLIs, retire MCP server) ⏳ PLANNED

Decision: collapse to one canonical interface — Python CLIs over the
filesystem YAMLs that already are the source of truth. Knowledge MCP
server (TypeScript) retires once every caller has a CLI counterpart.

Full decision record: `specs/toolchain-consolidation.md`.

**Three sub-phases (each independently shippable):**
- **6A** — port `/dashboard` to a Python CLI; skill becomes thin wrapper. Tracked as A-010.
- **6B** — audit remaining `mcp__knowledge__*` consumers; per-tool decide port / keep / kill. Tracked as A-011.
- **6C** — archive `~/agents/knowledge-mcp/`; drop MCP from `settings.json`; update target architecture. Tracked as A-012, gated on 6B.

Sequencing: 6A first (prototype + parallel-period validation); 6B only
after 6A is in real use ≥1 week; 6C once 6B's inventory shows zero
programmatic callers.

---

## Phase 5 — PLAN.md discipline ✅ DONE (template); ongoing per project

**What shipped:**
- `claude-config/templates/PLAN.md.template` — modeled on
  `~/projects/content-brain/PLAN.md`. Phased structure, exit criteria,
  "What we're NOT building" section, open decisions, sequencing discipline.
- `~/agents/PLAN.md` (this file) — first adoption.

**Adoption (opt-in per project, do not auto-create):**
- [x] `~/agents` (this file)
- [x] `content-brain` (already had one — the model)
- [ ] `flotilla` — pending Phase 2 decision
- [ ] `buddy` — adopt when next worked
- [ ] `mymoney-dev` — adopt when next worked
- [ ] `temper` — adopt when next worked

---

## What we're NOT building

- A new project tracker. Knowledge MCP is the source of truth, period.
- A replacement for Flotilla's React UI. Terminal is the dashboard.
- A custom multi-agent framework. Codex delegation + channel-mcp (if
  retained) handles all current needs.
- A unified observability stack. Per-project `/dashboard` view is enough.
- Auto-generation of PLAN.md across projects. Adoption is opt-in.

## Open Decisions

- [ ] **Usage logger design** (Phase 3 prerequisite). When/how to add.
- [ ] **Per-project PLAN.md rollout cadence.** Adopt as projects come up
      in active rotation, or seed all at once?

## Sequencing Discipline

Phases 0, 1, 2, 4, 5 shipped. Phase 3 explicitly deferred to give
measurement infrastructure time to mature. Phase 6 planned —
implementation begins with 6A (dashboard CLI).

Pre-consolidation rollback SHAs (per `specs/phase0-usage-report.md`):
- `~/agents` HEAD pre-Phase 1: `fec005d`
- `~/projects/flotilla` HEAD pre-archival: `e786eac`
- `~/agents` HEAD pre-Phase 6: TBD at start of 6A.
