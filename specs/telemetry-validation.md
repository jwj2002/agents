# Telemetry Validation — Spec (DRAFT)

**Date:** 2026-06-05
**Author:** scratch, with Jason. Grounded in the 2026-06-04 `/learn` findings + a verified
audit of the current telemetry.
**Status:** DRAFT. **Prerequisite** to the Team Knowledge MVP (the sensor everything else
aims with). The validation *methodology* (§2, §4) is a candidate **public BKM**.

---

## 0. Governing principle — fully automated, or it has gaps

> **Telemetry capture must be fully automated: zero manual steps, and the system must
> detect when it stops capturing.** Every optional or human-dependent telemetry step
> observed this session became a gap — `first_pass_correct`/`duration` unpopulated, the
> `/learn` loop never fired (epoch watermark for months, invisible), the `/correction`
> flip depends on someone *noticing*. **Manual = silent gaps = invalid measurement.**

Three consequences, each load-bearing:

1. **Automated capture.** Instrument at the **session/task level** (a universal Stop /
   PostToolUse hook), not inside the orchestrate pipeline — so *every* unit emits, not just
   orchestrated work (closes selection bias: `/quick`, plan-mode, freeform are currently
   invisible). Decision signals are **derived from artifacts**, never self-reported.
2. **Coverage watchdog (the part people miss — we lived it).** A fully-automated sensor that
   *silently stops* is worse than a manual one, because nobody notices. The telemetry must
   **monitor and alarm on its own coverage**: "0 token records this week," "this host's
   shard hasn't updated in N days," "PROVE outcomes dropped to zero." **An automated sensor
   must prove it is still running.**
3. **"Automated" ≠ "measure everything."** Some work has no valid code-quality measurement
   (§2.5). The system **auto-classifies and *default-excludes*** rather than manufacturing
   garbage. *Measuring the wrong thing is a worse validity failure than not measuring.*

---

## 1. Token capture — a valid efficiency sensor

**Status today: tokens are NOT captured anywhere** (verified — no `token`/`cost`/`usage`
field in any telemetry writer). The entire token-optimization goal currently has **no
sensor.** This is the #1 gap.

### 1.1 Capture the breakdown, not a number
Per **task and per phase** (MAP/PLAN/PATCH/PROVE), capture:
`{input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, model}`.
**Source:** Claude Code's existing OpenTelemetry metrics (`claude_code.token.usage`,
already broken down by type/model) + per-session usage — read by a collector hook and
**attributed to the current task/phase**. We tap an existing sensor; we don't build one.

### 1.2 Cost, not raw tokens (a validity requirement)
With prompt caching, a cache-read token costs ~10% of a fresh input token and output tokens
are most expensive — so **raw token count is not a valid cost measure.** Compute
**price-weighted cost (\$)** from the breakdown × per-model pricing. Cost > token sum.

### 1.3 Raw tokens / cost is a PERVERSE target (Goodhart)
Minimizing tokens → terser prompts, less context, worse code. So **raw tokens and cost are
*diagnostics only*, never targets.**

### 1.4 The reframe that makes token-optimization quality-*aligned*
Phase-attributed capture reveals that **most token waste is *rework*, not verbosity** — a
PROVE bounce, a re-PATCH, re-fed context after a failure burn tokens **and** signal a
quality miss; they are the same event. So the legitimate target is **"eliminate *wasted*
tokens (rework + redundant context),"** which *lowers cost and raises quality together.*

### 1.5 Token metrics + their role
| Metric | Role |
|---|---|
| raw tokens / phase | diagnostic only |
| price-weighted **cost** / task (cache-aware) | diagnostic |
| **waste-token share** (rework + redundant context) | **target** (quality-aligned) |
| **cost per first-pass-correct outcome**, normalized by complexity | **headline efficiency measure** |

---

## 2. Ground-truth anchor — what makes every proxy valid

**The problem:** every quality metric we have (`first_pass_correct`, `status`, ac-audit) is
a **proxy** with unknown construct validity. Without an independent ground-truth you cannot
tell a valid proxy from a gameable one — you might optimize `first_pass_correct` and just be
passing the gate more easily. **The ground-truth anchor converts measurement *theater* into
*valid* measurement.**

### 2.1 Automated ground-truth sources (human dropped from the dependency path)
1. **Post-merge-defect auto-tracing (primary — behavioral, real, automatable).** A script
   detects when a later PR/commit **fixes / reverts / references** a prior change within a
   window (e.g. 2 weeks) → auto-marks the original as defective. **Replaces the manual
   `/correction` flip with automatic detection.** Real-world consequence, derived from
   git/issue history. *(Critical-path build item — the tracing heuristic needs care: match
   on referenced issue, reverts, and same-file corrective edits; tune for precision.)*
2. **Scheduled adversarial-model review (secondary — independent, scalable).** A *different
   model* — **agent-b / GPT-5** — auto-reviews a sample on a cadence (no human). Genuinely
   uncorrelated with the Claude fleet's blind spots. The diversity dividend, on measurement.
3. **Human spot-rating — DROPPED from the dependency path** (full-automation rule). Optional
   periodic calibration only; the system never *depends* on it.

**Honest tradeoff:** automated ground-truth is **behavioral + model-judged, not
human-judged.** That is a net validity *gain* — "did the code actually break and need
fixing?" is more valid than a subjective rating, and it's *complete* instead of sparse.

### 2.2 The proxy-validation loop (the methodology = the BKM)
Proxies are **hypotheses**; ground-truth **tests** them:
1. Collect ground-truth on a sample (auto-traced defects + adversarial review).
2. **Correlate each proxy against it** (does `first_pass_correct` predict low defects? does
   low rework predict high adversarial-review scores?).
3. **Keep proxies that correlate; downweight/discard those that don't** — a proxy that
   doesn't track ground-truth is *not a valid measurement* and must leave the targeting set.
4. **Re-validate on a cadence** — proxies *drift* (valid today, gamed tomorrow). Validity is
   **earned and maintained, not assumed once.**

### 2.3 Cold-start honesty
Ground-truth is **lagging and sparse** (defects take weeks; samples are small). So **v1
ships with *provisional* (unvalidated) proxies + a ground-truth pipeline that progressively
validates/prunes them.** Early validity is weak; it strengthens as data accumulates. Stated
out loud, not pretended away.

---

## 2.5 Work-type classification & scope boundaries

"Fully automated" is **not** "measure everything." Code-quality metrics attach only to work
with a verifiable code outcome. Three work-types, each with different valid metrics:

| Work-type | Examples | Valid metrics |
|---|---|---|
| **Implementation** | issue → code → PR → merge → PROVE | full set (quality + efficiency + defects) |
| **Deliberative** | spec/design/research/review/discussion | **no code-quality metric** — cost-track only; value judged **downstream** |
| **Ops / admin** | git, config, running things | none |

**The auto-classifier (one observable bright line):** *Did this unit produce a code change
that went through PR / merge / PROVE?* Read from entry command (`/orchestrate`/`/quick` vs
freeform/`/spec-review`), whether a code diff was committed/merged, whether PROVE ran, and
whether the only artifact is a doc/conversation. **All observable → auto-routing, not a
manual exception.**

**Deliberative value is measured downstream, never in-session.** A spec/design artifact is
**linked to the implementation tasks it spawns** and judged by *their* outcomes
(first-pass-correctness, defects) — automatically, later. Its value is real but **lagging
and indirect**, never an in-session score. *(Example: a spec session like this one is
cost-tracked as deliberative, not quality-scored; the spec's value shows up when the code
built from it succeeds.)*

**Default-exclude on uncertainty.** Ambiguous units are excluded from quality metrics (raw
cost may still be captured, tagged "unclassified") — **never guessed.**

**Unit boundaries:** implementation auto-bounds on PR/commit/issue; deliberative bounds on a
session or produced doc. Mostly inferable; a real edge to handle.

---

## 3. The validity bar + per-metric verdicts

Every candidate metric must pass four tests: **construct validity** (does it measure the
thing?), **Goodhart/gameability** (does it degrade behavior as a target?), **confounds**
(what else drives it — normalize), **reliability** (enough signal, populated).

| Metric | Verdict |
|---|---|
| `status` PASS/BLOCKED | **WEAK** — "passed gate" ≠ "good code"; gameable |
| `first_pass_correct` | **REASONABLE** *if normalized for difficulty* — but under-captured today |
| `root_cause` / failure class | **VALID diagnostic**, survivorship-biased (can't see good practice) |
| `guards_fired` (self-reported) | **INVALID** — constant-field trap (#223); valid only if artifact-derived |
| `codex_overturned` | **STRONG** — hard to game; currently dormant |
| `duration_seconds` | **WEAK** — confounded by task size; normalize; under-captured |
| `complexity`/`tier_corrected_to` | **PROCESS indicator**, self-reported — not quality |
| prove-log `ac_audit`/`eval_results` | **REASONABLE** — closest to ground-truth, but agent-self-assessed |
| **tokens (in/out/cache per phase)** | **MISSING + CRITICAL**; raw = perverse target; use cost-per-good-outcome (§1) |
| **rework / bounce rate** | **VALID**, hard to game; only partially derivable today; make first-class |
| code-quality signals (lint/type/coverage/complexity) | **MIXED** — lint/type/finding *density* defensible; coverage% & raw complexity gameable (not targets) |
| `pattern_applied` / transfer-with-effect | **STRONGEST** — measures real downstream effect (the gold standard) |

---

## 4. Principles (the spec's spine; also the public BKM)

1. **Normalize everything** — per task-complexity or per good-outcome; never raw counts.
2. **Separate diagnostics from targets** — label each metric's *role*; most are valid
   diagnostics but invalid targets (Goodhart).
3. **Prefer hard-to-game, effect-based metrics** — `codex_overturned`, `pattern_applied`,
   rework-rate, ac-audit > self-reported `guards_fired`, raw tokens, coverage%.
4. **Validate proxies against ground-truth** — don't *assert* validity; *measure* it (§2).
5. **Fix coverage & bias first** — populate the valid fields that exist; close survivorship
   (capture positive signal) and selection (cover all work-types per §2.5).
6. **Capture tokens (cost, normalized) — the critical missing sensor.**
7. **Automate or it has gaps** (§0) — plus a watchdog so silent failure can't hide.

---

## 5. What to build (buildable order)

1. **Universal capture hook** — session/task-level Stop hook; emits for *every* work-type;
   auto-classifies (§2.5).
2. **Token collector** — read OTEL token metrics, attribute per task/phase, compute
   cache-aware cost (§1).
3. **Coverage watchdog** — alarms on capture gaps (§0.2).
4. **Post-merge-defect tracer** — the primary automated ground-truth (§2.1); *critical path*.
5. **Scheduled adversarial review** — agent-b samples + scores (§2.1).
6. **Proxy-validation job** — periodic correlate-and-prune (§2.2).
7. Populate/first-class the under-captured valid metrics (`first_pass_correct`, rework).

## 6. Non-goals / deferred

Human-in-the-loop quality rating (full-automation rule) · perfect deliberative-quality
scoring (judged downstream only) · gameable metrics as targets (coverage%, raw tokens) ·
measuring ambiguous units (default-exclude).

## 7. Relationships

- **Prerequisite to** the Team Knowledge MVP (`specs/team-knowledge-mvp-v1.md`) — it is the
  sensor the patterns/private-review/measurement pillars aim with.
- **Reuses** REC 0 decision fields, the #223 retro-map (failure-derived subset only), the
  existing `state_manager`/`prove-log`/aggregate pipeline.
- **Methodology is a candidate public BKM** — "validate your agent telemetry against a
  ground-truth" is rigor the field largely lacks.
- **Adjacent open spec (flagged by Jason):** git-process consistency — the workflow has been
  inconsistent (post-merge hook breakage, stash-and-forget, telemetry-churn blocking pulls,
  shared-file append conflicts). Its own investigation/spec. *(See task.)*
