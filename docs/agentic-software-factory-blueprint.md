# Agentic Software Factory — State of the Art + Build Blueprint (2025–2026)

> Research deliverable. Generated 2026-06-15 via the `deep-research` harness
> (28 sources fetched, 139 claims extracted, 25 adversarially verified → 18
> confirmed, 7 killed). Confidence tags and vote counts are carried inline.
> **Re-verify all pricing, model versions, and tier names before quoting** —
> the discourse moves fast and several figures had already drifted at capture.

## Goal anchor

Build an agentic software factory that (a) delivers bespoke custom software for
external clients (agency/consultancy delivery model) AND (b) is potentially
productizable so customers could run their own instance. Stack anchor: **Claude
Code + Codex (OpenAI) working together** — Claude as primary
implementer/orchestrator, Codex as adversarial reviewer / second-model rescue.

## What we already have (this is mostly an assembly job)

The `~/agents` stack is already ~70% of a factory. It has an evidence-gated
pipeline (`MAP→PLAN→PATCH→PROVE`), cross-model adversarial review (Claude
implements, Codex reviews via `/codex:adversarial-review`), blocking gates
(`agent-git readiness/ship`, behavioral evals E01–E15), telemetry
(`state_manager` hooks, failure corpus), and vendor-agnostic governance
(`AGENTS.md` + `CLAUDE.md` adapter). The research **validates these exact
choices**. The build is: harden it, wrap a tenancy/intake boundary around it,
and productize.

---

## 1. What an "agentic software factory" means in 2026

A coordinated **multi-agent pipeline where a spec goes in and working software
comes out** — agents handle planning, coding, testing, debugging, and delivery.
The shift is from *writing code* to *operating fleets of parallel agents*, each
with a task, a toolbelt (repos, test runners, deploy scripts, docs), context
(specs, architecture, constraints), and a feedback loop. Each agent typically
gets its own git worktree/branch/PR. Categorically distinct from inline
autocomplete (Copilot). [high, 3-0 — Addy Osmani/Google Chrome eng lead Feb
2026; MindStudio]

**Reference architecture — four baseline layers:**
1. **Orchestrator** ("the conductor") — *the hardest piece to build well*. A
   weak one produces chaotic pipelines where agents repeat work, miss steps, or
   spin indefinitely.
2. **Code-generation agents** ("the workers")
3. **Testing/validation agents**
4. **Deployment/monitoring agents**

Caveat: four layers is *one* decomposition. LangChain uses a richer 7-stage
pipeline (requirements/design/dev/security/test/deploy/ops). Treat four layers
as a baseline. [high, 3-0 — MindStudio; corroborated Praetorian, LangChain]

---

## 2. Orchestration patterns (the validated core)

**Evidence-gated phased pipeline.** No phase completes without documented,
verifiable evidence. Governing maxims, verbatim from real installable systems:
*"No evidence = no completion"* and *"narrative claims are not proof."* [high,
3-0 — agentic-os; metaswarm]

Two concrete reference implementations to study:
- **agentic-os** (github.com/KbWen/agentic-os):
  `Bootstrap→Plan→Implement→Review→Test→Ship` with a gate engine, backed by real
  tooling (pytest.ini, validate.sh) — not just markdown.
- **metaswarm** (Dave Sifry / Technorati founder): 11-phase pipeline with a
  **parallel 6-agent Design Review Gate** (PM, Architect, Designer, Security,
  UX, CTO — *all six must approve before implementation starts*), and an
  execution loop of `IMPLEMENT→VALIDATE→ADVERSARIAL REVIEW→COMMIT` that directly
  parallels `PATCH→PROVE`.

**Orchestrator vs. worker separation.** Codex-class coding models are **not**
the top-level orchestrator — they're embedded *inside* worker agents as
code-gen/reasoning engines. Top-level orchestration is a distinct "leader" role.
[high, 3-0 — LangChain]

⚠️ **Topology is genuinely unsettled.** "Lean 2-agent reviewer-critic beats
6-agent swarms" was **refuted (1-2)**. "Leader/Worker gives the largest
improvement" was **refuted (0-3)**. → Don't over-invest in a specific topology
being optimal. Keep it swappable.

---

## 3. Quality, verification & guardrails — *where the value actually lives*

> **Verification, not generation, is now the bottleneck.** [high, 3-0 — Osmani]

The most consistently corroborated, lowest-risk part of the blueprint is the
verification harness. Four mandates:

1. **Blocking gates, never advisory.** Hard state transitions with *no FAIL→COMMIT
   path* — FAIL means retry or escalate. Enforce at multiple points (pre-push
   hooks, CI, agent-completion gates) reading a **single source of truth**, and
   the orchestrator *runs gates directly, never trusting subagent self-reports.*
   [high, 3-0 — metaswarm]

2. **Cross-model adversarial review — never self-review.** The writer is
   *always* reviewed by a different model. *"A coding agent reviewing its own
   output has an inherent bias."* [high, 3-0 — metaswarm]

3. **Design for evidence-grounded disagreement, not consensus.** Multi-agent
   review fails via "false-consensus" (sycophancy / herd convergence). Reviewer
   roles must be prompted to *disagree with evidence*, not ratify. [high, 3-0 —
   Adversarial Review paper + 3 corroborating arXiv papers]

4. **TDD + non-optional human review.** A comprehensive test-first/red-green
   suite is *"by far the most effective lever."* Human review is *"not optional
   overhead — it is the safety system."* [high, 3-0 — Osmani; corroborated Endor
   Labs, Qodo (>75% won't ship AI code without human checks), Amazon mandating
   senior-eng approval]

⚠️ **Refuted:** "spec quality *almost entirely* determines output" (1-2). Treat
spec-driven development as a **co-equal lever with TDD**, not the sole
determinant.

---

## 4. Economics & ROI — read before selling it

| Finding | Number | Source |
|---|---|---|
| Companies achieving AI value **at scale** | ~5% (35% partial, 60% none) | BCG 2025, n=1,250 [high, 3-0] |
| AI POCs **scrapped before production** | ~46% avg | S&P Global, n=1,000+ [high, 3-0] |
| Experienced devs **slower** with AI in an RCT | **−19%** (they *believed* +20%) | METR RCT, 16 devs/246 tasks [high, 3-0] |
| Error compounding, unverified 3-agent chain @70% each | ~34% success (0.7³) | Fiddler [medium, 3-0] |

The METR finding is the most important for the business model: **human
throughput gains are not automatic, and self-reported productivity is
unreliable** → instrument *objective* telemetry. Error-compounding math is the
quantitative argument for short, verified loops over long autonomous chains. The
46%-scrapped pilot-to-production gap is exactly what the gating/verification
machinery exists to close.

⚠️ **Refuted hype — do NOT repeat in a sales deck:** "agents fail 70–95% in
production" (0-3), "88% demo-to-production gap" (0-3). The real risk is the
ROI/scaling gap, not catastrophic failure rates.

---

## 5. Productization (deliver-for-clients **and** sellable instance)

- **Vendor-agnostic Markdown governance is the proven portability mechanism.**
  Ship the *same* workflow rules to every model: shared `AGENTS.md` (loaded
  every turn — gates, state model) + per-model adapters (`CLAUDE.md`). Proven
  across Claude Code, Codex, Cursor, Copilot, Antigravity. This is the
  customers-run-their-own-instance story, and the structure already exists.
  [high, 3-0 — agentic-os]
- **Price on consumption, not seats.** Devin's ACU model: ~1 ACU ≈ 15 min of
  active agent work; entry from $20, pay-as-you-go ~$2.25/ACU, up to 10
  concurrent sessions. [medium, 3-0 on the *pattern*; 2-1 on numbers] ⚠️ Tier
  names already drifted (Core→Pro); "$500 Team plan" specifics **refuted (0-3)**.
  Adopt the consumption *pattern*; re-verify live numbers.

**Open question the research could not close:** per-customer isolation /
multi-tenancy (data/secret isolation, per-tenant model keys, sandbox
boundaries, repo/credential scoping) was *not* covered by any verified source.
Single biggest design unknown for the productized path — budget real design time.

---

## 6. Phased roadmap (anchored on Claude + Codex)

**Phase 0 — Harden what exists.** Audit every gate in `~/agents` for FAIL→COMMIT
leaks; confirm the orchestrator runs gates directly (no subagent self-reports).
Make Codex adversarial review *non-skippable* on risk-class diffs.

**Phase 1 — Single-tenant client delivery.** Run the existing pipeline against
one real client engagement. Instrument **objective** telemetry (cycle time, gate
pass/fail, human-review minutes, rework rate) — because METR shows perceived
speedup lies. Goal: prove POC→production conversion on one repo.

**Phase 2 — Intake + spec layer.** Add the front door: client requirement →
structured spec → spec-review gates. Co-equal investment in spec quality *and*
TDD scaffolding.

**Phase 3 — Parallel fleet.** Scale to multiple concurrent agents via git
worktrees. Keep loops short and verified; add retry/escalate on every gate.

**Phase 4 — Tenancy boundary (hard, under-researched).** Per-tenant isolation:
credentials, model keys, sandboxes, repo scoping. Genuine R&D spike — no
validated playbook exists.

**Phase 5 — Productize.** Package `AGENTS.md`/adapter governance as the portable
artifact; instrument ACU-style consumption metering; re-verify pricing.

---

## Confidence map

- **Trust most (primary/empirical):** METR RCT, BCG/S&P ROI numbers,
  verification-harness design. Lowest-risk part of the blueprint.
- **Trust as design patterns (practitioner docs):** four-layer architecture,
  gated pipelines, agentic-os/metaswarm — authoritative for *how systems are
  built*, not efficacy benchmarks.
- **Least proven:** productization economics; any ROI for a Claude+Codex factory
  *specifically* (none exists — metaswarm's "127 PRs in a weekend" is
  self-reported); multi-tenancy mechanics (uncovered).
- **Time-sensitive:** all pricing, model versions, tier names.

---

## Key sources

- Addy Osmani (Google Chrome eng lead), "The Factory Model" — addyosmani.com/blog/factory-model/
- MindStudio, "What is a Dark Factory AI Agent" — mindstudio.ai/blog/what-is-a-dark-factory-ai-agent
- agentic-os — github.com/KbWen/agentic-os (primary)
- metaswarm (Dave Sifry) — dsifry.github.io/metaswarm/
- LangChain, "Agentic Engineering" — langchain.com/blog/agentic-engineering-redefining-software-engineering
- "Adversarial Review" — openreview.net/forum?id=fOHvpLs6zp (primary, under review)
- METR RCT — metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ (primary)
- BCG "Build for the Future 2025" (n=1,250); S&P Global VotE AI & ML 2025 (n=1,000+)
- Devin pricing — docs.devin.ai/admin/billing, devin.ai/pricing

## Open questions (research could not close)

1. Measured ROI/throughput of a real Claude+Codex adversarial-review factory in
   client delivery — all efficacy evidence is self-reported or about
   single-developer use (METR showed a *slowdown*).
2. How per-customer isolation/multi-tenancy works in practice (data/secret
   isolation, per-tenant keys, sandbox boundaries, repo/credential scoping).
3. Right human-in-the-loop checkpoint placement/cost to keep review
   "non-optional" without erasing throughput gains.
4. Which orchestration topology actually performs best — comparative efficacy is
   genuinely open (two leading claims were refuted).
