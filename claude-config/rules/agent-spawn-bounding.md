# Bounding Agent Spawns Outside a Hardened Pipeline

> Promoted 2026-06-18 from a buddy incident (several ad-hoc agents hung in one
> multi-project session). Companion / provenance:
> `~/.claude/projects/-Users-jasonjob-projects-buddy/memory/feedback-ad-hoc-agent-hangs.md`.

Hardened pipelines (`/orchestrate` for code, `/quick`, `autonomous-run`) rarely
hang because they encode **termination** (bounded phases) and **verification** (a
test oracle = an unambiguous "done"). Any agent spawned **outside** a hardened
pipeline — a raw `Agent`/Task spawn, an ad-hoc `impl`/`ops`/`research` worker —
does NOT inherit that structure. You must replicate the bounding by hand or the
agent can hang.

## The hang vector

**Open-ended task + no definition-of-done + no iteration cap → loop.** Worst on
**ops/infra, data-prep, and exploratory/glue work**, where there is no
pass/fail oracle. (Canonical case: "slice this JSON to match the expected
structure" without being *given* the structure → the agent loops trying to
discover it.) A code PATCH agent rarely hangs because "tests green" is a clear
stop; an ops/data agent often has no equivalent.

## Coverage is uneven — the hardened pipeline is CODE-centric

| Action type | Hardened pipeline |
|---|---|
| Code issue | `/orchestrate`, `/quick` ✅ |
| Multi-issue autonomous | `autonomous-run` ✅ |
| Code/spec review | `adversarial-review-gated`, codex gates 🟡 |
| Research | `deep-research`, research agent 🟡 |
| Ops / infra / data-prep / glue | none ❌ — bound manually |

The ❌ rows are where hangs happen. Until those get hardened flows, bound them
by hand with the rules below.

## Rules for any non-pipeline spawn

1. **Prefer the hardened pipeline when one fits.** Don't reach for a raw spawn
   just because it's quicker — that trades away the guardrails.
2. **Bound the prompt:** an explicit STOP-condition + iteration cap +
   definition-of-done. e.g. "If the slice doesn't validate in 2 attempts, STOP
   and report — do not keep trying." (Same discipline as `autonomous-run`:
   budget cap, no open loops.)
3. **Give a test oracle or the exact target spec.** Never make an agent
   *discover* a data shape, schema, or structure — hand it the target.
4. **Pre-flight environmental dependencies before dispatch.** Most stalls are
   missing prerequisites (absent fixtures/data, unbuilt artifacts, malformed
   inputs, missing creds). Verify they exist first.
5. **Don't background exploratory data/infra work unsupervised.** Scope it
   tightly or run it with a human in the loop.
6. **Liveness tripwire.** Monitor the agent's output-file mtime; a stale/idle
   agent (no output for many minutes, no matching process running) is likely
   hung. Stop it and finish the remaining step deterministically — its committed
   work survives the stop.

## Why this matters more now

Running **multiple projects/tasks in one session** removes the implicit bound
that "one Claude session per project" used to provide (one focused context,
serialized, watched). With a single orchestrator juggling many action *types*,
more work falls outside the hardened (code) path and no human watches every
thread — so the bounding must be explicit. See also `agent-delegation-contract.md`
(quality contract across the spawn boundary) and `implementation-routing.md`
(tier/risk routing). The structural fix for the multi-project load is a
coordinated multi-orchestrator topology, not unbounded fan-out in one session.
