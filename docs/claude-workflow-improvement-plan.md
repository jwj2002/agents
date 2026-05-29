# Claude Coding Process — Full Review & Improvement Plan

**Date:** 2026-05-29
**Author:** Critical review (Claude Opus 4.8), at Jason's request — blunt, evidence-grounded, no ego-management.
**Scope:** Every stage of the coding process — spec → issues → agent prompts → implementation → review → PR → ship → telemetry → learn — across **work** (`~/projects`) and **personal** (`~/agents`) code.
**Supersedes:** the earlier stub of this file.

---

## 0. How to read this

Each process stage below has three blocks: **Current state (verified)** with real file paths, **Critical gaps**, and **Fix**. The plan is grounded in the actual code, not aspiration. Section 5 sequences everything into P0/P1/P2 with acceptance criteria. Section 7 lists what NOT to build — the discipline of *not* adding surface area matters as much as the additions.

---

## 1. Evidence base (verified)

- **Telemetry (vault-metrics MCP, `~/agents/mcp-server/`):** recording is real but **siloed per project**.
  - `~/projects/buddy/.claude/memory/metrics.jsonl` = 95 lines; `failures.jsonl` = 15.
  - `~/projects/mymoney-dev/.claude/memory/metrics.jsonl` = 90 lines; `failures.jsonl` = 23.
  - `~/agents/.claude/memory/metrics.jsonl` = 3 lines.
  - MCP reads via `get_project_memory_dir()` → defaults to **cwd**. There is **no global aggregation**.
- **Reported pass rate 89.5%** (COMPLEX 29/29, SIMPLE 43/44, **UNKNOWN 11/20**) — but this is **PROVE grading its own output**. Post-PROVE correction turns ("forgot to wire X") are **not recorded anywhere**.
- **`/learn` has never run:** no `pattern-events.jsonl` anywhere; `patterns-full.md` missing; `patterns-critical.md` is hand-written. No cron / RemoteTrigger / loop.
- **`/rate-limit-options` = 2,820 of 14,068 history entries (20%).**
- **Git lifecycle stops at the PR.** No `/ship`; no auto commit/merge/squash/prune.
- **Spec discipline is strong for backend, blind for frontend.** Code-reality manifest + 3-round adversarial review exist; no frontend-component or design-token manifest; `discover-patterns` not wired into `spec-draft`.
- **`~/agents` is a real repo** (jwj2002/agents) with CI (`.github/workflows/validate.yml`) and tests (`pytest.ini`, `lib/tests/`) — but **near-zero telemetry** (3 records) and **no spec discipline** (ad-hoc `ACTIONS.md`).

---

## 2. Core diagnosis (three root problems)

**P-A. The instrument lies.** Your headline metric is self-graded by PROVE in the same context that wrote the code. Your real failure mode — integration/wiring gaps you fix in follow-up turns — is structurally invisible. You cannot improve what you cannot see. **The most important single change in this plan is to measure first-pass-correctness.**

**P-B. The loop is open at four joints.** Data is recorded per project but (1) never aggregated to global, (2) `/learn` is never triggered, (3) applied patterns aren't re-injected into agent context per run, (4) `/learn --validate` never runs. You pay for telemetry and harvest nothing.

**P-C. Defects are born upstream and caught downstream.** Your logged failures are spec-drift and live-only (`grid_entity` vs `entity`, asyncpg Pool vs Connection, reserved word `symmetric`, OpenAI strict-schema 400, missing duck-typed methods). Planning doesn't catch these; specs-from-code-reality and an early live reality-check do. And UI inconsistency/duplication is born from specs that never name the components/tokens to reuse.

---

## 3. Process review — stage by stage

### 3.1 Spec development

**Current (verified):** `~/.claude/commands/spec-draft.md` (7-step guided draft, backend pattern grep) → `~/.claude/commands/spec-review.md` (spec-reviewer agent, gap classification) governed by `~/agents/claude-config/rules/spec-review-workflow.md` (§2 code-reality manifest, §3 self-review, §4 adversarial R1/R2/R3 convergence). Template `~/.claude/templates/code-reality-manifest.md` (8 sections) exists and is used by real backend specs.

**Gaps:**
- **Manifest is not mandatory in practice.** You learned it on `owner_onboarding_v1` (8 rounds) and wrote it down — but adherence is optional. This is the biggest defect leak.
- **Frontend/UI is unspecced.** Specs cite backend enums/tables/functions verbatim but never cite **reusable components, prop APIs, state hooks, or design tokens.** → UI inconsistency and re-implemented one-off components.
- **`discover-patterns` is not wired into `spec-draft`** — pattern reuse is not surfaced at draft time.

**Fix:**
1. **Make the code-reality manifest a hard gate** before any V1.0 spec (enforce in `spec-draft` and `spec-review-workflow.md` §5 happy path; refuse to draft without it).
2. **New `~/.claude/templates/frontend-component-manifest.md`** (parallel to code-reality): reusable components + prop contracts, shared hooks, **design tokens** (color/spacing/typography/breakpoints), layout primitives. Required for any UI-touching spec.
3. **Wire `discover-patterns` into `spec-draft` Step 2:** for UI features, prompt "run `/discover-patterns frontend` first" and cite results in the spec.
4. **Add a self-review check** in `spec-review-workflow.md` §3: "frontend component-API verification" (parallel to the execution-order trace).

### 3.2 GitHub issue development

**Current (verified):** `spec-review --create-issues` generates issues referencing commit hash + spec version + line numbers; PM V1 issues carried test ACs lifted from spec §8. Good practice when used.

**Gaps:**
- **Ad-hoc work bypasses issues entirely** → `UNKNOWN` complexity → 55% pass and zero telemetry.
- Test ACs in issues are inconsistent (great for PM V1, absent elsewhere).

**Fix:**
1. **Every non-trivial change gets an issue**, even personal `~/agents` work — that's the unit telemetry attaches to. Trivial work that skips an issue must still emit a metric (see 3.8).
2. **Standardize the issue body:** required "Test ACs" + "Components/patterns to reuse" sections, auto-filled from the spec + manifests.

### 3.3 Agent prompts

**Current (verified):** 12 agents under `~/.claude/agents/` (`_base` + map/map-plan/plan/plan-checker/patch/prove/contract/test-planner/discuss/spec-reviewer/pr-fresh-reviewer). Well-factored, no redundancy. Agents are loaded from disk per dispatch; `load_learning_rules.py` (SessionStart) injects `patterns-critical.md` only.

**Gaps:**
- **PROVE's verification scope misses integration.** It checks "does my code work," not "is every caller wired and every callee present." This is your wiring/integration failure class.
- **Learned patterns aren't re-injected** (`patterns-full.md` not loaded; loop break #3).
- **No early live reality-check** for backend/DB/LLM-schema work.

**Fix:**
1. **Add a Wiring/Integration checklist to `patch.md` + `prove.md`:** callers wired? callees exist (read the class, no duck-typing)? service registered in `ServiceContainer`? enum VALUE not NAME? `Path(...).expanduser()`? data handoff between sequential steps verified?
2. **Add an early reality-check step for backend/DB/LLM work** (enhance MAP/PATCH): connect to **real** Postgres and inspect actual tables (`\d`), confirm Pool-vs-Connection, dry-run any strict JSON schema against the **live** API *before* implementing. This is the one new capability worth building (kills wrong-table, reserved-word, strict-schema, pool-vs-connection at the source).
3. **Encode recurring failure classes as explicit checklist items** in `patch.md` (sourced from `failures.jsonl`): `MISSING_SERVICE_WIRING`, `MISSING_INTERFACE_METHODS`, `ASYNCPG_POOL_VS_CONNECTION`, `SQL_RESERVED_WORD`, `OPENAI_STRICT_SCHEMA`, `PATH_EXPANSION`.

### 3.4 Implementation & the wiring failure class

Already covered by 3.3 fixes. Additional rule: **small PRs.** Person-Consolidation hid 37 regressions in one big diff; adversarial review is only as strong as the diff is small. Enforce "one logical change per PR" (already a git-workflow rule — make it a `/ship` precondition).

### 3.5 Review — adversarial vs approval gate

**Current:** approval gates ("review before PATCH") historically; you've shifted toward Codex/independent-Claude adversarial review. Correct direction.

**Separate the two jobs (they are not the same):**
- **Adversarial review** answers *"is this thing right?"* — correctness, wiring, best-practices. Independent grader, parallelizable. Use heavily, in **two** places: on the **spec** (cheap) and on the **diff/PR** (catches implementation defects). One pass is not enough.
- **The approval gate** answers *"is this the right thing?"* — scope, priority, taste. Irreducibly yours. Keep a *lightweight* gate here only.

**Fix:** standardize "spec adversarial review (loop to low RISK)" + "diff adversarial review on every PR" as pipeline steps, classified BLOCKING/NON-BLOCKING/CLEAN per `implementation-routing.md`.

### 3.6 PR process

**Current (verified):** pre-commit hook (`~/projects/buddy/scripts/pre-commit`) runs `ruff --fix`, `ruff format`, a `relationship_id` grep gate, and version bump — blocks on the gate. `~/.claude/commands/pr.md` runs the pre-PR checklist + `pr-fresh-reviewer` (E01–E15), blocks on CRITICAL, then `gh pr create` and **stops**. `/pr --merge` squash-merges (no `--delete-branch` in buddy), runs post-merge verification, manual prune.

**Gaps:** stops at PR; merge/prune manual; post-merge verification uses `pytest -x` in places (hides regressions — see `feedback_pytest_no_dash_x_for_validation`).

**Fix:** fold into `/ship` (3.7). Replace any `-x` in validation with the full suite.

### 3.7 `/ship` — commit / merge / squash / prune automation

**Goal:** one command from green diff → shipped, plus an **auto tail** for commit→merge→squash→prune.

**`/ship` sequence (new command `~/.claude/commands/ship.md`):**
1. Assert on feature branch (not main); one logical change.
2. Stage + commit (conventional message); pre-commit hook runs (lint/format/version).
3. `git fetch origin && git rebase origin/main` → resolve or abort.
4. `git push --force-with-lease` (safe after rebase).
5. `gh pr create` if absent → `pr-fresh-reviewer` → **block on CRITICAL**; for COMPLEX/risky diffs, `/codex:adversarial-review`.
6. `gh pr checks --watch` → **block on red CI**.
7. **Re-verify PR HEAD == local HEAD** (the `gh pr merge --squash` drops-commits caveat) → if mismatch, push then re-check.
8. `gh pr merge <N> --squash --delete-branch`.
9. Post-merge verification: `git checkout main && git pull`, **full** `ruff` + `pytest tests/` (no `-x`).
10. `git fetch --prune origin`; delete local branch; clean `: gone]` branches.
11. Auto-derive docs: changelog entry from the conventional commit; update affected README/CLAUDE.md if flagged.
12. Record outcome to telemetry (3.8); emit "Shipped ✓ <PR url>".

**Auto tail (the shortcut you asked for):** `/ship --auto` runs steps 8–11 without prompts **only when all guards pass**. Also expose a shell alias (e.g. `gship`) for the tail.

**Guards (non-negotiable for any auto-merge):**
- Never merge red CI; never `--force` (only `--force-with-lease` after rebase); always `--squash`.
- Always rebase + verify HEAD parity before merge (drop-commits caveat).
- Post-merge full-suite verification is mandatory; failure → stop + propose hotfix, do not prune.
- Enable repo "auto-delete head branches"; otherwise `--delete-branch`.
- A kill switch: `/ship` without `--auto` always pauses before the irreversible merge.

### 3.8 Telemetry — must be automated

**Current (verified):** `orchestrate.md` Step 4 calls `record_metrics`/`record_failure` via `~/.claude/hooks/state_manager.py` → per-project `.claude/memory/*.jsonl`. **Only orchestrate runs record.** `/quick`, freeform, and correction turns record nothing. No global aggregation.

**Fix — close the four joints:**
1. **Global aggregation hook** — new `~/.claude/hooks/aggregate_metrics_to_global.py`, wired into the `Stop` hooks in `settings.json`: merge every `~/projects/*/.claude/memory/*.jsonl` and `~/agents/.claude/memory/*.jsonl` → global `~/.claude/memory/{metrics,failures}.jsonl` (idempotent, dedup by issue+date+project).
2. **First-pass-correctness capture (P-A fix, highest value)** — extend the metrics schema with `first_pass_correct: bool` and `corrections: [reason]`. Mechanism: a tiny `/correction <issue> "<what was missed>"` micro-command that flips the record + appends a failure, **plus** a `Stop`-hook heuristic that flags follow-up fix prompts referencing a just-PASSED issue before `/ship`. This makes your real defect rate visible for the first time.
3. **Record `/quick` and freeform outcomes** so `UNKNOWN`-complexity work is measured (today it's a blind spot at 55%).
4. **These feed the automated `/learn` (3.9) and a `/dashboard` subscription** so trends are visible without manual queries.

### 3.9 Learn process — must be automated

**Current (verified):** `~/.claude/commands/learn.md` consumes `{metrics,failures}.jsonl`, produces `patterns.md`, `patterns-critical.md`, `patterns-full.md`, `pattern-events.jsonl`, and (with `--apply`) inserts `## Learned Prevention` sections into agent files + bumps versions. `--cross-project` scans `~/projects/*` and `~/agents`. **100% manual; never run.**

**Fix:**
1. **Schedule it.** A RemoteTrigger/cron routine runs **weekly**: `/learn --apply --cross-project --validate`. (Friday EOD or after every 10 issues, whichever first.)
2. **Re-injection** — update `~/.claude/hooks/load_learning_rules.py` to also load `patterns-full.md`, so applied patterns actually reach PATCH/PROVE on the next run (loop break #3).
3. **Auto-validate** — `--validate` compares success rate before/after each applied pattern; report effectiveness; auto-revert patterns that don't help.
4. **Apply threshold** stays ≥5 occurrences for auto-apply; 2–4 occurrences → surfaced for your review, not auto-applied.
5. **First run now** — run `/learn --cross-project` against the existing 95+90+15+23 records to generate the missing `patterns-full.md` and seed the loop.

### 3.10 Dual-source learning — work (`~/projects`) + personal (`~/agents`)

**Current (verified):** `~/projects/buddy` = full ceremony + rich telemetry; `~/agents` = fast ad-hoc + 3 telemetry records, no specs. `/learn --cross-project` already scans both.

**Principle — keep the two modes, unify the learning:**
- **Do not impose full spec ceremony on `~/agents`.** Personal velocity is a feature. Sample only high-signal work (major refactors get a *lightweight* code-reality manifest; everything else stays fast).
- **Instrument `~/agents` equally.** Wire metrics on every completed action (it already has `.claude/memory/` + CI). Add a `/dashboard` subscription.
- **One global pattern store.** Both sources feed the same `~/.claude/memory/patterns-*.md`, so a bug pattern learned in personal code protects work code and vice-versa — which is exactly the cross-pollination you want.

---

## 4. New artifacts to build (concrete)

| Artifact | Path | Purpose |
|---|---|---|
| `/ship` command | `~/.claude/commands/ship.md` | Green-diff → shipped, with guards + `--auto` tail |
| `gship` alias | `~/.gitconfig` or `~/agents/bin/` | Shell shortcut for the commit→merge→squash→prune tail |
| Global aggregation hook | `~/.claude/hooks/aggregate_metrics_to_global.py` | Per-project jsonl → global store (Stop hook) |
| First-pass capture | `~/.claude/commands/correction.md` + Stop-hook heuristic | Record `first_pass_correct` + correction reasons |
| Frontend-component manifest | `~/.claude/templates/frontend-component-manifest.md` | Force UI specs to cite reusable components/tokens |
| Design tokens reference | `knowledge/design-tokens.yaml` (per project) | Single source for color/spacing/typography/breakpoints |
| Weekly learn routine | RemoteTrigger/cron: `/learn --apply --cross-project --validate` | Closes the loop automatically |
| Reality-check step | enhancement to `map.md`/`patch.md` | Live schema/type/JSON-schema probe before implementing |
| Wiring checklist | additions to `patch.md` + `prove.md` | Kill the integration/wiring failure class |

---

## 5. Sequenced roadmap

### P0 — this week (visibility + the loop)
1. **Run `/learn --cross-project` now** against existing records → generate `patterns-full.md`, seed `pattern-events.jsonl`.
2. **Build the global aggregation hook** + wire into `Stop`. *Accept:* global `metrics.jsonl` reflects all projects after any session.
3. **Add first-pass-correctness capture** (`/correction` + schema field + Stop heuristic). *Accept:* a correction turn shows up as `first_pass_correct=false` in telemetry.
4. **Record `/quick` + freeform outcomes.** *Accept:* `UNKNOWN`-complexity share trends down; no silent work.
5. **Diagnose & kill the 2,820 `/rate-limit-options`.**

### P1 — next 2 weeks (defect prevention + ship)
6. **Make the code-reality manifest a hard gate**; add the wiring checklist to `patch.md`/`prove.md`.
7. **Build the early reality-check** for backend/DB/LLM work.
8. **Build `/ship`** (full + `--auto` tail) with all guards; replace `-x` in validation with full suite.
9. **Frontend-component manifest + design-tokens.yaml + wire `discover-patterns` into `spec-draft`.** *Accept:* next UI spec cites reusable components/tokens by name.

### P2 — this month (automate learning + pay down debt)
10. **Schedule the weekly `/learn --apply --cross-project --validate`** + fix `load_learning_rules.py` to load `patterns-full.md`.
11. **Instrument `~/agents` equally** + `/dashboard` subscription; adopt lightweight manifests for major personal refactors only.
12. **Finish/delete half-built pieces:** upgrade or remove `/review`; resolve missing `/feature`; validate `--resume`/recovery end-to-end.
13. **Portfolio cull** to ≤10 real projects (archive 5 no-git stubs + duplicate maison/generator/real-estate clusters).
14. **(Future) report step** — Telegram/agent notification fired from a Stop hook on `/ship`.

---

## 6. Metrics that prove it's working

| Metric | Now | Target |
|---|---|---|
| **First-pass-correct rate** (no post-PROVE corrections) | **unmeasured** | measured, then ≥80% |
| Overall pass (independently graded) | 89.5% (self-graded) | ≥95% (with diff review) |
| `UNKNOWN`-complexity share of runs | 21% (11/20 fail) | <5% |
| Live-only failures (wrong-table/schema/pool) | recurring | →0 after reality-check |
| `/learn` runs per month | 0 | ≥4 (automated) |
| `~/agents` telemetry records/month | ~1 | ≥ matches activity |
| Manual steps from green-diff → shipped | ~10 | 1 (`/ship`) |

---

## 7. Non-goals (do NOT build)

- **More orchestrate-phase agents.** You have enough; another adds maintenance surface and a bus-factor-of-one risk.
- **Per-project bespoke agents.** Standardize via templates instead.
- **"Accuracy" agents** that duplicate PLAN-CHECK/PROVE. Fix verification *scope*, don't clone the agent.
- **Full spec ceremony in `~/agents`.** Preserve personal velocity; sample high-signal only.
- **Polishing the Telegram report before the spec/telemetry core.** The tail is the cheapest, lowest-value part.

---

## 8. One-line verdict

You don't have an agent shortage — you have an **invisible defect rate**, an **open learning loop**, and **defects born in under-specified specs**. Measure first-pass-correctness, automate telemetry + `/learn` across work *and* personal code, push defect-killing upstream into specs written from code reality (with a frontend manifest for UI/reuse), and collapse the ship tail into one guarded `/ship`. Build exactly the artifacts in §4 — and nothing else.

---

## Appendix A — Opus 4.8 leverage (added 2026-05-29)

Verified against Anthropic's 4.8 release docs. Adopt these alongside the plan; they amplify it, they don't replace it.

### Practices to adopt
- **Effort-by-stage (the real rate-limit lever).** Default effort is `high` everywhere; adaptive thinking only reasons when needed. Run **high effort** for spec / plan / adversarial review; **drop effort** for mechanical work (the `/ship` tail, lint, renames). Lower effort consumes rate limits more slowly — this replaces compulsive `/rate-limit-options` checking (which is 20% of history).
- **Fast mode for the mechanical tail.** 2.5× output, now 3× cheaper (`/fast`). Use for `/quick` and `/ship` steps 8–11; keep off for spec/review.
- **Dynamic Workflows for codebase-scale work.** Plan + hundreds of parallel subagents in one session. Use for the **portfolio cull (§5.13)**, cross-cutting buddy refactors, and the **cross-project `/learn` aggregation (§3.9)**. Opt-in only.
- **Leaner frontend prompting.** 4.8 needs less guidance to avoid generic "AI-slop" UI. Spend prompt budget on *which components/tokens to reuse* (§3.1 frontend manifest), not on coaxing non-generic output.
- **Use 1M context + better compaction.** Load the **whole spec + its code-reality manifest in one context** rather than fragmenting — directly reduces the spec-drift failure class. PreCompact/PERSISTENT_STATE become a safety net, not a crutch.

### Rely on, with one hard caveat
- 4.8 is **~4× less likely to let flaws in its own code pass unremarked** and skips fewer required tool calls (maps to your wiring/integration + "fake success" failures). **Caveat:** a better author is still not an independent grader. First-pass-correctness measurement (§3.8) and diff-level adversarial review (§3.5) **still stand** — treat 4.8 as raising the floor, not relaxing discipline.

### API-code changes (buddy, email-triage, mcp-server)
- **Mid-conversation system messages:** append `role:"system"` after a user turn to update instructions mid-task **without breaking prompt cache** — useful for buddy's long agentic loops.
- **Lower prompt-cache minimum (1,024 tokens):** buddy/email-triage's many small LLM calls now cache for free.
- **Migration hazard (action):** on Opus 4.7+ / 4.8, passing `temperature`/`top_p`/`top_k` or `thinking.budget_tokens` to the Claude API returns **400**.
  - **Scan result (2026-05-29):** `~/agents` clean; email-triage Haiku fallback clean; buddy's Haiku email calls clean.
  - **One latent foot-gun:** `buddy/src/buddy/voice/response_generator.py:84-85` passes `temperature` (`voice_llm_temperature=0.4`, config.py:68) on the Anthropic path. Harmless on Haiku/Sonnet/OpenAI, but **400s the instant `voice_llm_model` is set to an Opus 4.7/4.8 model.** Fix: strip/guard `temperature` for Opus 4.7+ models (model-family check). Track as its own buddy issue.
  - The `claude-api` skill can auto-apply 4.7→4.8 migration across a codebase.
