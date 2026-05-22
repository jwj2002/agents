# agents — Consolidation Plan

> Living document. Tracks the multi-phase work to slim the Claude/Codex
> config and consolidate project-state tooling onto filesystem YAMLs +
> Python CLIs (Phase 6 retired the Knowledge MCP server).

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

## Architecture (current state, post-Phase 8 / Path B)

```
   ┌──────────────────────────┐   ┌──────────────────────────────┐
   │  Obsidian vaults         │   │  Per-repo ACTIONS.md         │
   │  ~/vaults/<name>/        │   │  (in each project's repo)    │
   │                          │   │                              │
   │  Projects/<name>.md      │   │  action/cli.py writes        │
   │  (human-edited fm)       │   └──────────────────────────────┘
   │  Decisions/D-NNN.md      │
   │  (MADR frontmatter+body) │
   │  Daily/<date>.md         │
   │  (Templater + Dataview)  │
   │  Projects/_pulse/        │   ┌──────────────────────────────┐
   │  <project>--<host>.md    │←──┤  pulse refresh               │
   │  (machine-derived,       │   │  (git + gh + ACTIONS.md +    │
   │   single-writer/host)    │   │   lib/host_resolver SSH)     │
   └────────┬─────────────────┘   └──────────────────────────────┘
            │ reads
   ┌────────┴─────────────────┐
   │  Python CLIs             │  action, project, decision,
   │  (~/agents/)             │  pulse, email-digest
   └────────┬─────────────────┘
            │ shell-out (where wrapped)
   ┌────────┴─────────────────┐
   │  Thin Claude             │  /action, /project (others legacy)
   │  skill wrappers          │
   └──────────────────────────┘

   ┌──────────────────────────┐
   │  Codex delegation        │  parallel work, reviews, rescue
   │  (rescue/review)         │
   └──────────────────────────┘
```

Multi-agent channels were dropped in Phase 2 (Option B). Codex delegation
is the converged multi-agent pattern. The Knowledge MCP server retired in
Phase 6C (#146); its source is archived at `_archived/knowledge-mcp/`.
Path B (Phase 8) moved projects/decisions from YAML to Obsidian vaults and
retired the `dashboard` + `review_session` CLIs in favor of Templater +
Dataview rendering inside Obsidian and the `pulse` CLI for sidecar refresh.
Surface map and scoping rules: `specs/knowledge-surfaces.md`. Path B
decision record: `specs/path-b-migration.md`.

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

## Phase 6 — Toolchain consolidation (Python CLIs, retire MCP server) ✅ DONE (2026-05-07)

Decision: collapsed to one canonical interface — Python CLIs over the
filesystem YAMLs that already are the source of truth. Knowledge MCP
server (TypeScript) retired once every caller had a CLI counterpart.

**Phase 6 is single-machine.** Cross-device project state is Phase 7.

Full decision record: `specs/toolchain-consolidation.md`.
Knowledge surface map: `specs/knowledge-surfaces.md` (Phase 6 follow-up).

**Sub-phases (all shipped):**
- **6A** — `/dashboard` ported to `dashboard/cli.py`; skill becomes thin wrapper. (A-010, #134, #136)
- **6B** — Audit + ports of remaining `mcp__knowledge__*` consumers. (A-011 audit in #138; A-015/A-016 cancelled — capture/inbox killed in #139; A-017 = `/project` port in #141; A-018 = `/review-session` port in #143.)
- **6C** — Archived `~/agents/knowledge-mcp/`; dropped `knowledge` from `~/.claude.json`; migrated `session_end_context_update.py` from sqlite to YAML reads; updated target architecture. (A-012 + bundled A-021, #146.)

After 6C: zero programmatic or hook-level callers of `mcp__knowledge__*`
or `knowledge.db`. Vault-metrics MCP remains (separate server, unrelated).

---

## Phase 7 — Cross-device project state ✅ DONE (2026-05-08, Phase 7.1) + superseded by Phase 8

Phase 7.1 shipped: `host:` schema field on every project record, plus
`~/.claude/host-name` per-machine canonical-name file. See
`specs/cross-device-state.md`.

Phase 7.2 (SSH bridge) was absorbed and redesigned by Path B (Phase 8) —
implemented as per-host sidecars at
`<vault>/Projects/_pulse/<project>--<host>.md` written by `pulse refresh`,
under a single-writer-per-host convention. See `specs/path-b-migration.md`.

Original Phase 7 investigation text retained below for historical context:

---

(historical) The dashboard CLI ported in Phase 6A is **local-only** — it reads files
on the machine it runs on. Cross-device visibility (e.g., seeing jbox06
project state from the laptop) needs separate design work; the MCP→CLI
swap by itself does not address it.

**What partially works today (via git sync of the agents repo):**
- `knowledge/projects/*.yaml` — focus, blockers, next-steps, status —
  syncs across machines that pull `~/agents/`. Already cross-device
  visible from any machine that pulled.

**What does NOT work today and Phase 6A won't add:**
- Per-project `ACTIONS.md` from a project repo cloned only on the other
  machine (e.g., laptop wanting to see jbox06's `~/app-repos/<name>/ACTIONS.md`).
- `git log` / open-issue counts from the remote project repo.
- A subscription model that distinguishes which-host a project lives on.

**Solution shapes to evaluate (in A-013):**
- **A. Git-as-sync** — extend the "agents repo carries state" pattern;
  cheapest, partially already in place; doesn't cover ACTIONS.md when
  the project repo isn't cloned locally.
- **B. SSH-based remote read** — `dashboard --host jbox06`; CLI
  installed on both machines; subscriptions take host qualification
  (`jbox06:agents`); medium effort.
- **C. Centralized store** — each machine writes state to a shared
  location; heaviest; only justifies for ≥3 devices or web-aggregation
  needs.

**Tracked as:** A-013 (investigation). **Gated on:** Phase 6A complete
(need a clean local CLI to extend before introducing remote concerns).

**Exit criteria:**
- [ ] Cross-device requirements articulated (which projects, which
      direction, which fields).
- [ ] Decision recorded at `specs/cross-device-state.md` (modeled on
      `specs/toolchain-consolidation.md`).
- [ ] Implementation actions filed for the chosen option.

---

## Phase 8 — Path B (Obsidian + multi-vault topology) ✅ DONE (2026-05-13)

Full architectural decision record: `specs/path-b-migration.md`.

**What shipped (umbrella #170, 16 commits, +9000 LOC):**

| Component | Issue | Module |
|---|---|---|
| Pre-flight YAML→Obsidian migration manifest | #165 | `scripts/migration-manifest.py` |
| Obsidian Templater + Dataview templates + sync script | #163 | `templates/obsidian/`, `templates/sync-templates.sh` |
| `obsidian_md` lib (frontmatter + section helpers) | #166 | `lib/obsidian_md.py` |
| Vault-aware subscription helpers + auto-migrate | #166 | `lib/project_resolver.py` |
| `project` CLI reshape to Obsidian markdown frontmatter | #166 | `project/cli.py` |
| `decision` CLI reshape to MADR markdown | #166 | `decision/cli.py` |
| One-time per-device bootstrap script | #164 | `bootstrap-laptop.sh` |
| YAML→Obsidian migration + archival cutover | #168 | `scripts/migrate-to-pathb.py`, `scripts/run-pathb-archival.sh` |
| `host_resolver` (git/gh/SSH + cache) | #161 | `lib/host_resolver.py` |
| `pulse refresh / report / digest / audit / vault offboard` | #161/162 | `pulse/cli.py` |
| `email-digest` preset config + interactive Y/E/S/N + isolation guardrails | #167 | `email-digest/cli.py` |
| Docs cleanup | #169 | this file + the specs |

**Retired (archived to `_archived/`):**
- `dashboard/` CLI — replaced by Obsidian Daily review + Project page Dataview blocks
- `review_session/` CLI — replaced by Daily review's stale-focus + git-hygiene queries
- `knowledge/projects/*.yaml` — moved to `<vault>/Projects/*.md`
- `knowledge/decisions/*.yaml` — archived (not migrated; new decisions go to `<vault>/Decisions/D-NNN.md` via `decision/cli.py`)

**Isolation guardrails landed (per spec §6.5 + Codex F4):**
1. Email-digest preset → vault validation (refuses send on client mismatch)
2. `pulse digest --all-vaults` jns-mac-only (hardcoded check)
3. Pre-send confirmation context line
4. Per-vault git remote allowlist (opt-in via `~/.claude/vault-remotes.yaml`)
5. `pulse audit` subcommand (cron-friendly drift detection)
6. `pulse vault offboard` (single-command vault retirement)
7. FileVault policy (documented; bootstrap checks on macOS)

**Operational guide:**
- Day-to-day project work in Obsidian — open the Daily note (auto-Templater on first open of the day), check stale-focus + activity blocks
- Refresh sidecars on demand: `pulse refresh` (or via launchd/cron every 30 min)
- Generate a digest: `pulse digest --vault JNS-Personal-Vault` (terminal) or `email-digest preset run paul-jason` (interactive send)
- Audit before a client engagement ends: `pulse audit`
- Off-board a client vault: `pulse vault offboard --vault NAME --dry-run` → `--for-real`

**Exit criteria:**
- [x] All 7 project YAMLs migrated to Obsidian project notes (`migrate-to-pathb.py` smoke-verified)
- [x] All 9 decision YAMLs archived
- [x] Retired CLIs archived via `git mv` (history preserved)
- [x] Subscription file in vault-keyed format with backup at `dashboard-subscriptions-pre-pathb.json`
- [x] Templates installed in vault, Dataview queries reference real frontmatter fields (no `this.subscribed` references — Codex F1 fix)
- [x] Per-host sidecars written on `pulse refresh` (verified with real agents + buddy data)
- [x] Email-digest preset config example shipped + vault validation refuses cross-client leakage
- [x] Bootstrap script idempotent + handles macOS / Linux / WSL

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

Phases 0, 1, 2, 4, 5, 6, 7, 8 shipped. Phase 3 explicitly deferred until
the orchestrate usage logger lands. Path B (Phase 8) shipped 2026-05-13.

Pre-consolidation rollback SHAs (per `specs/phase0-usage-report.md`):
- `~/agents` HEAD pre-Phase 1: `fec005d`
- `~/projects/flotilla` HEAD pre-archival: `e786eac`
- `~/agents` HEAD pre-Phase 6: TBD at start of 6A.
- `~/agents` HEAD pre-Path-B (Phase 8) implementation PR: `ff84488`
  (the spec merge commit). Rollback procedure documented in
  `specs/path-b-migration.md` §11.
