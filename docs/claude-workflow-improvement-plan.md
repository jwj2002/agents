# Claude Workflow Improvement Plan

**Date:** 2026-05-29
**Author:** Critical review (Claude Opus 4.8) at Jason's request — no sugar-coating.
**Scope:** Jason's Claude Code workflow across `~/projects` (excl. `~/agents`), his
custom Claude infrastructure (`~/agents/claude-config`), and his prompting habits.

---

## 0. Evidence base

- **Telemetry (vault-metrics MCP):** 95 orchestrate runs, 89.5% pass.
  - COMPLEX 29/29 (100%), SIMPLE 43/44 (98%), **UNKNOWN 11/20 (55%)**.
  - by stack: backend 62/63, fullstack 7/7, frontend 4/4, **unknown 11/20**.
  - 15 logged failure causes, nearly all count=1, concentrated in `buddy`.
- **Learning files:** local `metrics.jsonl` = 3 lines; **no `pattern-events.jsonl`
  anywhere; `patterns-full.md` missing** → `/learn` has never closed the loop.
- **History:** 14,068 entries; **2,820 (20%) are `/rate-limit-options`**.
- **Portfolio:** 25 project dirs — 3 active, 18 dormant, 5 no-git stubs;
  duplicate clusters (maison ×4, generators ×3, real-estate ×3); only 5 have a
  full CLAUDE.md + `.claude/` setup.
- **Infra:** 12 agents, 17 commands, 12 rule files (~1,929 lines), 11 hooks.

---

## 1. What is genuinely working (keep, don't touch)

1. **The disciplined pipeline is near-flawless.** Inside `/orchestrate`,
   COMPLEX and SIMPLE work passes ~98–100%. The MAP→PLAN→PATCH→PROVE structure,
   the CONTRACT synchronization point for fullstack, and PLAN-CHECK gating are
   real engineering, not theater. **The framework works.**
2. **Approval gates.** "Review the plan before PATCH. Any questions?" is your
   single best habit — it has caught real bugs before they shipped.
3. **File/issue-anchored prompting.** You pin work to specs and issue numbers;
   agents always know what "done" means. This is why your in-pipeline rate is high.
4. **Security posture.** Secret-guard hook, deny-list for `.env`/keys, allowlist
   for safe commands. Better than most teams.
5. **State continuity.** SessionStart restore + PreCompact checkpoint +
   PERSISTENT_STATE.yaml = work survives compaction. Rare and valuable.

---

## 2. The gaps (ranked by impact)

### GAP 1 — You get burned when you SKIP your own pipeline. (highest ROI)
UNKNOWN-complexity work passes **55%**; pipeline work passes **~98%**. The
failures aren't a Claude problem — they're a *routing* problem. Ad-hoc/freeform
work bypasses MAP (read the code) and PROVE (verify), and that's exactly where
the ~10× higher failure rate lives.
**Action:** make the pipeline the default path, not the disciplined exception.

### GAP 2 — The learning loop is open. You instrument but never learn.
95 runs + 15 failures recorded; `/learn` never run; `patterns-full.md` missing;
no `pattern-events.jsonl`. `patterns-critical.md` is hand-written. You are
carrying the *cost* of telemetry with none of the *compounding benefit*.
**Action:** close the loop on a schedule and actually feed failures back into agents.

### GAP 3 — Your failure DNA is "reality drift," not bad planning.
The 15 failures are overwhelmingly: wrong table name (spec said `grid_entity`,
real table `entity`), asyncpg Pool vs Connection, SQL reserved word `symmetric`,
OpenAI strict-schema rejection, missing duck-typed interface methods, paths
without `.expanduser()`. **None of these are fixed by more planning.** They are
fixed by verifying against *live infrastructure and real types* EARLY. Today your
PROVE phase catches them late ("phase2-live-test", "sprint4-*") after implementation.
**Action:** add an early reality-check, not another planning agent.

### GAP 4 — Portfolio sprawl dilutes everything.
25 dirs, 3 active, 5 zero-git stubs, 3 duplicate clusters. Each new project
reinvents (or skips) the Claude setup — only 5 of 25 are fully set up. Sprawl is
why "consistency across projects" is a pain: there's no consistent baseline to be
consistent *with*.
**Action:** archive aggressively; standardize a project template.

### GAP 5 — A large bespoke framework with half-built edges, maintained by one person.
`/review` is a 21-line wrapper; `/feature` is referenced but missing;
`patterns-full.md` missing; learn loop dormant. The framework's *surface area* now
exceeds what's *validated*. This is a maintenance liability and a single point of
failure (you).
**Action:** finish or delete the half-built pieces; prefer plugins/skills you don't
have to maintain where they exist.

### GAP 6 — Prompting: strong, with three concrete leaks.
- **2,820 `/rate-limit-options` (20% of history).** Either compulsive checking or a
  binding/statusline firing it. Diagnose and kill the noise.
- **Backtracking within a single prompt** ("…do X. Before you finalize, let me ask
  3 questions…"). Front-load the questions or split the turn.
- **Vague terse follow-ups** ("Thoughts?", "Why would you…?") that assume context.
  Anchor to a file/line/output.

---

## 3. Should you build specialized agents?

**Short answer: mostly NO — and that instinct is the trap.** You already have 12
agents and 17 commands; several are half-built. Another *process* agent has near-zero
marginal value and adds maintenance surface (GAP 5).

**Build agents ONLY where they attack your actual failure DNA (GAP 3) or close the
loop (GAP 2). Specifically:**

- ✅ **A reality-check / live-verification step** (enhance PROVE or add a pre-PATCH
  "infra probe"): before implementing DB or LLM-schema code, connect to the real
  Postgres and `\d` the actual tables, confirm Pool-vs-Connection, dry-run the
  OpenAI/LLM JSON schema against the live API. This directly kills wrong-table,
  reserved-word, strict-schema, and pool-vs-connection failures.
- ✅ **An operational `/learn` runner** (a scheduled job, not really a new agent):
  run weekly, cluster failures, propose agent/pattern diffs for your approval.
- ⚠️ **Maybe** a domain "data-layer reviewer" focused on your recurring asyncpg /
  pgvector / migration patterns — but only after the loop is closed and proves the
  pattern persists.
- ❌ **Do NOT** build: more orchestrate-phase agents, per-project bespoke agents,
  or "accuracy" agents that duplicate PLAN-CHECK/PROVE.

The highest-leverage moves are **process and enforcement, not new agents.**

---

## 4. The plan (prioritized, concrete)

### P0 — This week (kills the most failures for the least effort)
1. **Enforce routing.** Make `/orchestrate` (even SIMPLE tier) the default. Treat
   `/quick`/freeform as the rare exception, and when used, still require a MAP read
   + a PROVE verification line. Target: drive UNKNOWN-complexity work toward zero.
2. **Close the learning loop.** Run `/learn` against the existing 95+15 records.
   Generate `patterns-full.md`. Then schedule it: `/loop` weekly or a cron routine.
   Verify `pattern-events.jsonl` starts populating.
3. **Diagnose the 2,820 `/rate-limit-options`.** Find what fires it (keybinding,
   statusline, habit). Kill or automate it.

### P1 — Next 2 weeks (attacks failure DNA + sprawl)
4. **Add an early reality-check for data/LLM-schema work.** A pre-implementation
   probe that reads live schema (`\d`), confirms object types, and dry-runs any
   strict JSON schema against the real API. Wire it into PATCH for backend/DB issues.
   This is the one *new* capability worth building.
5. **Portfolio cull.** Archive the 5 no-git stubs and dormant duplicates (maison ×4
   → 1, generators ×3 → 1, real-estate ×3 → 1). Goal: ≤10 real projects.
6. **Standardize a project baseline.** One `scaffold-project` template that drops a
   CLAUDE.md + `.claude/` (commands, settings, memory) into every new repo, so
   consistency is automatic, not manual.

### P2 — This month (pay down framework debt)
7. **Finish or delete half-built pieces:** upgrade `/review` to be agent/pattern-aware
   *or* delete it in favor of the `code-review` skill; resolve the missing `/feature`;
   remove dead references.
8. **Validate `--resume` and failure recovery** end-to-end; document "what to do when
   PATCH/PROVE fails."
9. **Prompting tweaks:** front-load questions (don't backtrack mid-prompt); anchor
   terse follow-ups to a file/line.

### Metrics to watch (you already collect them — now USE them)
- UNKNOWN-complexity share of runs → trend to 0.
- Overall pass rate → 89.5% → 95%+ as the loop closes and reality-checks land.
- Live-only failures (wrong-table, schema, pool/connection) → trend to 0 after P1.4.
- `/learn` runs per month → ≥4 (was 0).

---

## 5. One-line verdict

Your framework is excellent; your *adherence* and your *feedback loop* are the
problems. Don't build more agents — **enforce the pipeline you have, close the
learning loop, and add exactly one early reality-check** for the live-infra bugs
that planning can't catch.
