---
description: "The quality contract a spawned/delegated agent must honor — three flavors (implementation/research/ops), each derived from code-quality-standards.md, never duplicating it"
paths: ["**"]
---

# Agent Delegation Contract

When you spawn an agent (Agent/Task tool, `/orchestrate` worker, a
`general-purpose` worker, or any delegated unit of work), the *same* quality bar
that applies to you applies to it. This rule is the thin contract that carries
that bar across the spawn boundary.

**Single source of truth.** This file does not restate quality standards — it
**points** to the canonical ones so they cannot drift:

- Quality gates: `rules/code-quality-standards.md` (coverage, ruff, LR-001,
  types, behavioral evals, secrets, runtime smoke — each with its exact check).
- Completion semantics: `rules/git-workflow.md` → "Completion Gates".
- Verification discipline: `rules/core-patterns.md` → VERIFICATION_GAP.
- Tier/risk routing: `rules/implementation-routing.md`.

Pick the flavor that matches the spawned agent's job. When in doubt, the more
demanding flavor wins (implementation > ops > research).

---

## Flavor: implementation (writes code)

For any agent that edits, adds, or deletes code.

- **Apply `rules/code-quality-standards.md` in full** — coverage must not
  decrease, `ruff check`/`ruff format --check` clean on changed files, LR-001
  (no bare `except:`/blind `except Exception` outside sanctioned fail-open
  surfaces), behavioral evals clean on the diff, and a passing **runtime smoke**
  for any runnable surface. Run the exact commands that rule names; do not
  invent per-PR rules.
- **Honor the completion gate** (`rules/git-workflow.md`): a task is done only
  when it is implemented → **wired through its intended entrypoint** → exercised
  by automated or manual validation → observed with command output/artifact
  evidence. Files merely present on disk is NOT done.
- **Verify, don't assume** (VERIFICATION_GAP, `rules/core-patterns.md`): read
  the actual code before asserting anything about it; a new field means grepping
  every consumer. Cite evidence as `path:line`.
- **Conventional Commits**, one issue per commit. **Never** silence checks with
  `--no-verify`, `--force`, or `bypassPermissions` to get green.
- **Report what was NOT done** — partial ACs, deferred work, and anything you
  could not verify, explicitly.

## Flavor: research / read-only (no writes)

For any agent that investigates, searches, or reviews without mutating state.

- **Read before you assert** (VERIFICATION_GAP): every claim about code, config,
  or data is grounded in a file you actually read this session — **no claims
  from memory or from the prompt's framing.** Cite as `path:line`.
- Return a **compact, honest verdict** — the conclusion the caller needs, not a
  file dump.
- **Flag verified-vs-untested** explicitly: separate what you confirmed by
  reading/running from what you are inferring.

## Flavor: ops / prod-write (infra & production data)

For any agent that writes to production: DBs, schemas, hosts, services, secrets.

- **Single owner per resource** — never two agents writing the same DB/schema,
  branch, or host concurrently (`autonomous-run` §5). Memory/SQL writes are
  SEQUENTIAL.
- **Soft-delete, never destructive SQL** — prefer `is_active=false`/archive over
  `DELETE`/`DROP`. (See buddy's `memory-seed` skill for the canonical pattern.)
- **Confirm before any hard-to-reverse op** — destructive migrations, data-loss,
  secret rotation are stop gates (`autonomous-run` §4): STOP and report, do not
  proceed unattended.
- **Verify after writing** — re-read/audit the resource to confirm the change
  landed as intended; record the evidence.
- **Don't guess** — on an unexpected state, STOP and report rather than
  improvising a fix on production.

---

## Bounding & coordination (all spawns)

- **Coordinator, not conductor.** Delegate the *orchestration* of a unit of work,
  not just its implementation. Running a pipeline (`/orchestrate`, a multi-step
  ops sequence, a review loop) inline makes you the per-project orchestrator —
  itself a delegated role. Spawn a fresh agent to conduct it; stay at the
  coordination layer. A fresh agent loads its contract front-of-context and does
  not decay the way a long orchestrator session does — **delegation is a fidelity
  mechanism, not just parallelism.**
- **Bound every spawn outside a hardened pipeline.** `/orchestrate`, `/quick`,
  `autonomous-run` encode termination + a test oracle; a raw `Agent`/Task spawn
  does not. Give it: a STOP-condition + iteration cap, a test oracle or the EXACT
  target spec (never make an agent *discover* a data shape/schema), pre-flighted
  env deps, no unsupervised exploratory data/infra work, and a liveness tripwire
  (stall + no matching process → kill, finish deterministically). Open-ended task
  + no definition-of-done = hang. **Hardened pipelines are code-centric —
  ops/data/glue have none, so bound them by hand.**
- **Concurrency** (`rules/orchestration-concurrency.md`): per project ≤2
  work-items in flight + a pull queue; ≤3 active projects; **one owner per mutable
  resource** (branch/DB/file) — shared-resource work serializes; worktree-isolate
  parallel code agents; soft tripwire ~6 concurrent agents.

## Honest reporting (all flavors)

Every spawned agent ends its work the same way:

- **State confidence** — what is proven vs. inferred vs. assumed.
- **Surface blockers** loudly — do not bury a failure in a success-shaped report.
- **STOP rather than guess** — when the right action is genuinely ambiguous or
  irreversible, report the ambiguity and the options; do not pick silently and
  present it as done. (AMBIGUITY_UNRESOLVED, `rules/core-patterns.md`: if you
  must pick, pick ONE, document it, and flag the alternative.)
