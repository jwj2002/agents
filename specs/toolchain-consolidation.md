# Toolchain Consolidation — Phase 6

> Decision record for collapsing the project-state toolchain to a single
> Python-CLI surface. Knowledge MCP server retires once all callers have
> CLI counterparts.

**Status:** Decided 2026-05-07. Phase 6A pending implementation.
**Modeled on:** `~/projects/content-brain/PLAN.md` decision-doc style.

---

## Why this exists

`agents` consolidation Phases 0–5 collapsed two project-state stacks onto
Knowledge MCP and slimmed `~/agents/claude-config/` to artifacts that earn
their cost. After Phase 2 (Flotilla archived) and the recent
`cap → action --new` consolidation, the converged pattern across all
shipped work is **Python CLI + thin Claude-skill wrapper that shells out**.

`/dashboard` is the only large-scale Claude skill that still implements
its own logic in markdown rather than delegating to a CLI. It calls
`mcp__knowledge__*` tools (TypeScript MCP server) and runs ~620 lines of
spec each invocation. This costs Claude tokens on every call, runs only
inside Claude sessions (no shell / cron / status-bar callers), and
duplicates state-reading logic that already exists in the `action` CLI's
project resolver.

Phase 6 finishes the consolidation: collapse to one canonical interface
(Python CLIs over filesystem YAMLs), retire the duplicate (TypeScript MCP
server), and let Claude skills reduce to thin shell-outs.

---

## Decision

**Adopt the "Python CLI + thin Claude-skill wrapper" pattern as the
canonical interface for all project-state operations on this machine.**
Filesystem YAMLs (and per-project `ACTIONS.md`) remain the single source
of truth. Python CLIs read and write them directly. Claude skills become
short shell-out wrappers (the `/action` skill is the model: ~5 lines).

The Knowledge MCP server (`~/agents/knowledge-mcp/`, TypeScript) retires
once every caller has a CLI counterpart and nothing programmatic still
talks MCP.

---

## Architecture (target state)

```
            filesystem (canonical, git-tracked)
            ├── knowledge/projects/*.yaml
            ├── knowledge/decisions/*.yaml
            ├── knowledge/patterns/*.yaml
            ├── knowledge/inbox/*.json
            ├── knowledge/learning_rules/*.yaml
            └── ~/projects/<name>/ACTIONS.md
                          │
                          ▼
            ┌──────────────────────────────┐
            │  ~/agents/<tool>/cli.py      │  Python CLIs
            │  (action, dashboard, …)      │
            └──────────────────────────────┘
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
  ┌───────────┐   ┌────────────────┐   ┌──────────────┐
  │ shell /   │   │ Claude Code    │   │ cron / status│
  │ pipes     │   │ skills (thin   │   │ bar / other  │
  │           │   │ wrappers)      │   │ scripts      │
  └───────────┘   └────────────────┘   └──────────────┘
```

The `~/agents/knowledge-mcp/` server is **not** in the target state.

---

## Options considered

### Option 1 — Build dashboard CLI alongside the existing MCP server

Dashboard CLI reads YAMLs directly. MCP server stays for any caller that
wants it. Two readers of the same files, indefinitely.

**Rejected.** Drift trap. Same data flow served by two implementations
in two languages — divergence is only a matter of time. Doesn't match the
consolidation theme of every other shipped phase.

### Option 2 — Shared `knowledge_lib` module; both CLIs and MCP wrap it

Refactor MCP server's YAML reading + filtering into a shared library;
both Python CLIs and the TypeScript MCP server consume it.

**Rejected.** Architecturally pure but expensive: TypeScript MCP would
need either a Python rewrite or a TS↔Python bridge. Significant upfront
work to preserve a server that has few real callers and would itself be
on the chopping block once Claude skills become CLI wrappers.

### Option 3 — Collapse to Python CLIs; retire MCP server (CHOSEN)

Build CLI counterparts for every MCP tool that has a real caller. Migrate
each Claude skill to a thin shell-out wrapper. When nothing calls the
MCP server programmatically, archive it.

**Chosen.** Matches every consolidation we've shipped this session. Drops
TypeScript/Node from the toolchain. Single language across the stack.
Filesystem-as-truth aligns with `PLAN.md`'s stated source-of-truth.

---

## Three-phase rollout

Each phase is independently shippable and gated on real-world use of the
prior phase.

### Phase 6A — `dashboard` CLI

**Tracked as:** A-010

- New `~/agents/dashboard/cli.py` reading `knowledge/projects/*.yaml`,
  per-project `ACTIONS.md`, and `git`/`gh` directly.
- Refactor `action`'s ACTIONS.md parser into a shared module (e.g.
  `~/agents/lib/actions_md.py`) that both CLIs consume.
- `/dashboard` skill becomes a thin wrapper (~5 lines, `/action` model).
- Multi-project mode: subscription-filtered (already authoritative per
  `#129/#130`).
- Single-project mode: full deep-view, unchanged behavior.
- Output formats: terminal cards + markdown digest (existing contract).
- Parallelize per-project `git`/`gh` with `concurrent.futures` so the
  CLI matches the skill's natural parallelism.
- Tests: per-mode rendering snapshots; window/owner/status filters;
  subscription-filter error cases.

**Sizing:** ~600–700 lines + ~150 lines of tests. MODERATE tier.

**Exit criteria:**
- [ ] `dashboard` CLI matches the existing skill's output for a defined
      set of fixture projects.
- [ ] `/dashboard` skill is a thin wrapper.
- [ ] Side-by-side comparison run for ≥1 week against real projects;
      no behavior regressions noted.
- [ ] `knowledge.db` decision pinned (see Open Decisions).

### Phase 6B — Audit & port remaining MCP consumers

**Tracked as:** A-011

- Inventory every caller of `mcp__knowledge__*` tools across:
  - `~/agents/claude-config/skills/` (every SKILL.md)
  - `~/agents/claude-config/commands/`
  - `~/agents/claude-config/agents/` (orchestrate sub-agents)
  - Any plugin under `~/.claude/plugins/`
  - Settings files (`~/.claude/settings*.json`)
- Per tool: decide **port-to-CLI / keep-on-MCP / kill**.
- Likely candidates for port: `/project`, `/capture`, `/inbox`, `/learn`,
  `/discover-patterns`, `/metrics`.
- Output: a follow-up plan listing each MCP tool, decision, and
  destination. May spawn one or more PRs of its own.

**Sizing:** SIMPLE — investigation + planning, not implementation.

**Exit criteria:**
- [ ] Complete inventory of MCP consumers documented.
- [ ] Per-tool decision recorded in this spec or a follow-up.
- [ ] Migration plan for any MCP tool slated for port.

### Phase 6C — Archive `knowledge-mcp/`

**Tracked as:** A-012, gated on 6B.

- Verify zero remaining programmatic callers.
- Move `~/agents/knowledge-mcp/` to `~/agents/_archived/knowledge-mcp/`
  (parallel to Flotilla's archival).
- Drop the MCP server registration from `~/.claude/settings.json` (and
  `claude-config/settings.json` source-of-truth).
- Update `PLAN.md` target architecture diagram — replace the
  `Knowledge MCP server` box with `filesystem YAMLs` directly.
- Update any docs that still reference `mcp__knowledge__*` as a
  programmatic interface.

**Sizing:** SIMPLE.

**Exit criteria:**
- [ ] No `mcp__knowledge__*` tool calls in any active code path.
- [ ] MCP server registration removed from settings.
- [ ] `~/agents/knowledge-mcp/` archived; `claude-config` settings clean.
- [ ] `PLAN.md` reflects post-MCP architecture.

---

## Risks

1. **External callers we don't know about.** Codex plugins or other tools
   in `~/agents/` might call knowledge MCP. Phase 6B's audit must be
   exhaustive — false-clean = breakage on archive.
2. **MCP-only features.** Some MCP tools may do something a CLI can't
   match cleanly (long-running streams, structured tool responses Claude
   needs as objects rather than text). Phase 6B will surface these. If
   any exist and matter, they stay on MCP and Phase 6C narrows scope to
   "archive everything else."
3. **Phase 6A scope creep.** Tempting to refactor the world while
   building the dashboard CLI. Discipline: just dashboard. The shared
   `actions_md.py` module is in scope; rewriting the `action` CLI is
   not.
4. **`knowledge.db` ambiguity.** SQLite cache is rebuilt by the
   post-merge hook. CLIs need a decision: read from `knowledge.db` (fast,
   needs cache freshness logic) or from YAMLs (canonical, slower for
   bulk queries). See Open Decisions.
5. **Side-by-side period regression risk.** During the ≥1-week parallel
   period in Phase 6A, the user may notice rendering drift. Mitigation:
   define a fixture-based output comparison early; rerun before merge.

---

## What we're NOT doing

- **Building new project-state features.** This is a re-platforming, not
  a feature push. Existing `/dashboard` behavior is the contract.
- **Rewriting `action`.** `action` already follows the target shape.
  Refactor for shared helpers only.
- **Replacing Knowledge MCP with a different MCP server.** The point is
  to drop the MCP layer, not swap implementations.
- **Touching the obsidian-agent.** `~/agents/obsidian-agent/` reads the
  vault, not the knowledge YAMLs. Out of scope.
- **Auto-archiving the Knowledge MCP GitHub repo (if any).** If it's a
  separate repo, that's a manual cleanup decision after Phase 6C lands.

---

## Open Decisions

- [ ] **`knowledge.db` role for CLIs.** Primary read path or query
      optimization? Recommend YAMLs primary, `knowledge.db` only if
      profile shows a real hot path. Pin in Phase 6A.
- [ ] **Migration strategy for Phase 6A.** Big-bang (CLI + skill-as-wrapper
      in one PR, like `cap → action`) or parallel period (ship CLI
      alongside, compare for a week, then collapse)? Recommend **parallel
      period for a 600-line replacement**. Pin before Phase 6A starts.
- [ ] **Shared library home.** `~/agents/lib/`, `~/agents/_lib/`, or
      `~/agents/common/`? Affects import paths. Pin in Phase 6A.
- [ ] **Test fixtures location.** Per-tool `tests/fixtures/` or a shared
      `~/agents/tests/fixtures/`? Affects how tests share project YAML
      mocks. Pin in Phase 6A.

---

## Sequencing Discipline

Phase 6A ships first because everything else gates on it: the dashboard
CLI is the prototype for "MCP-tool-replaced-by-Python-CLI", and its
real-world behavior under a parallel period is the signal for whether
the pattern holds. Phase 6B is investigation and may surface findings
that change Phase 6C's scope. Phase 6C is mechanical once 6B's
inventory is clean.

Do **not** start Phase 6B before Phase 6A's CLI is being used in real
flows for ≥1 week — premature audit would be planning against an
unverified pattern.

Pre-Phase-6 SHAs (for rollback):
- `~/agents` HEAD pre-6A: TBD at start of A-010 implementation.
