---
description: "Orchestration concurrency model — WIP caps + pull queue (kanban WIP), single-owner, coordinator-not-conductor, bounded fan-out, and why fresh agents beat long-session inline work. Referenced from agent-delegation-contract.md (always-loaded); read when orchestrating or running parallel agents."
---

# Orchestration Concurrency

How to run multiple agents / projects without the failure modes of an overloaded
orchestrator. The operational essentials live in `agent-delegation-contract.md`
(always-loaded, `paths: ["**"]`); this is the full model + rationale, pulled when
you actually orchestrate.

## Coordinator, not conductor
The top-level session **coordinates; it does not conduct individual pipelines.**
Delegate the *orchestration* of a unit of work to a fresh agent, not just its
implementation. Running a pipeline (`/orchestrate`, a multi-step ops sequence, a
review loop) inline makes you the per-project orchestrator — itself a delegated
role.

**Why this is a fidelity mechanism, not just parallelism:** a fresh agent loads
its contract front-of-context on a small context; a long-running orchestrator
session **decays** — early instructions (BASE.md, this rule) lose salience as the
conversation grows and get compressed at compaction, so adherence degrades
exactly when the session is busiest. Point-of-use loading (fresh subagent + its
contract) is decay-resistant; load-once-at-start is not. Delegate to fresh agents
*for correctness*, not only for speed.

Durable topology: **meta-supervisor** (talks to the human, dispatches, digests) →
**per-project orchestrators** → **workers**. See
`docs/architecture/multi-orchestrator-scaling.md` in projects that ship it.

## WIP limits = kanban pull
- **Per project: ≤2 work-items in "Doing."** Further ready items wait in a Ready
  lane and are PULLED when a slot frees (a kanban WIP limit — one source of
  truth, visible queue depth).
- **≤3 active projects** concurrently; a 4th waits in a project-level Ready lane.
- The cap counts **work-items (cards)**, not agents. Agent fan-out *within* a
  card is governed below.

## Single owner per mutable resource
Never two agents writing the same branch / DB / schema / file concurrently —
those **serialize**. Worktree-isolate parallel code agents (a shared working
tree = HEAD/index collisions). Disjoint resources (different DBs, non-overlapping
files) may run in parallel.

## Agent fan-out within a card
Not a fixed number — bounded by single-owner (above) + verify-every-return +
per-agent budget/iteration caps. **Soft project-wide tripwire ~6 concurrent
agents:** past that, pause and confirm. The real ceiling is the orchestrator's
*verification bandwidth*, not the harness's concurrency.

## Bound every spawn outside a hardened pipeline
`/orchestrate`, `/quick`, `autonomous-run` encode termination + a test oracle; a
raw `Agent`/Task spawn does not. Give every such spawn: a STOP-condition +
iteration cap, a test oracle or the EXACT target spec (never make an agent
*discover* a data shape/schema), pre-flighted env deps, no unsupervised
exploratory data/infra work, and a liveness tripwire (stall + no matching
process → kill, finish deterministically). Open-ended task + no definition-of-done
= hang. **Hardened pipelines are code-centric — ops/data/glue have none, so bound
them by hand** until those pipelines exist. (This subsumes the former
`agent-spawn-bounding` rule, now folded into `agent-delegation-contract.md`.)

## Guidance vs enforcement
A rule is advisory — **loaded ≠ followed.** The non-negotiables (no unbounded
spawn, single-owner, WIP cap) deserve **mechanical enforcement** — a hook in
settings.json the *harness* runs, or the pipeline's own structure — not just this
text. Codify here for availability; enforce structurally for reliability.

---
*Provenance: 2026-06-18 multi-project session — several ad-hoc ops/data agents
hung; root cause was unbounded spawns + conducting inline in one overloaded,
decaying session. Companion: buddy `feedback-ad-hoc-agent-hangs.md`.*
