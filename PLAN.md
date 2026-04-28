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

                       ┌────────────────────┐
                       │  Channel MCP       │  inter-agent comms
                       │  (TBD — see Phase 2)│  awaiting decision
                       └────────────────────┘
```

Reference specs:
- `specs/phase0-usage-report.md` — what got measured, what didn't, why Phase 3 was deferred

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

## Phase 2 — Channels decision ⏸ BLOCKED (awaits user input)

**Issue:** `channel-mcp/index.ts` requires `CENTRAL_SERVER_URL` and is a
client of the Flotilla central server. Archiving Flotilla also kills
inter-agent channel communication.

**Options on the table:**
- **A. Slim Flotilla to transport-only** (~8k → ~1.5k lines). Keep
  channels working. Strip dashboard.py, captures*, daily_summary,
  planned_work, project_metrics, devices, terminal, scaffold,
  github_sync, health_monitor, tech_stack, migration, React UI.
- **B. Drop multi-agent channels entirely.** Archive Flotilla wholesale.
- **C. Defer.** Leave Flotilla as-is. /dashboard already unhooked.

**Decision needed:** A vs B vs C — see "Open Decisions" below.

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

- [ ] **Channels: A vs B vs C** (Phase 2 blocker). User input required.
- [ ] **Usage logger design** (Phase 3 prerequisite). When/how to add.
- [ ] **Per-project PLAN.md rollout cadence.** Adopt as projects come up
      in active rotation, or seed all at once?

## Sequencing Discipline

Phases 0, 1, 4, 5 shipped this session. Phase 2 awaits user decision on
channels. Phase 3 explicitly deferred to give measurement infrastructure
time to mature.

Pre-consolidation rollback SHAs (per `specs/phase0-usage-report.md`):
- `~/agents` HEAD pre-Phase 1: `fec005d`
- `~/projects/flotilla` HEAD: `e786eac`
