# Telemetry Validation — Spec (DRAFT v2)

**Date:** 2026-06-05
**Author:** scratch, with Jason. Fleet-reviewed (agent-b = validity/adjudication, server-a =
capture/transport, laptop-wsl = proxy-validation). Grounded in the 2026-06-04 `/learn`
findings + a verified audit of the current telemetry.
**Status:** DRAFT v2 — incorporates the three lane reviews. **Prerequisite** to the Team
Knowledge MVP (the sensor everything else aims with). The validation *methodology* is a
candidate **public BKM**.

---

## 0. Governing principles

### 0.1 Fully automated, or it has gaps — with a *dead-man's-switch* watchdog
Capture must be fully automated: **zero manual steps.** Every optional/human-dependent step
this session became a silent gap (`first_pass_correct` unpopulated, `/learn` never fired for
months, the `/correction` flip depends on someone noticing).

**The watchdog must be a dead-man's-switch, not a self-check** (server-a — the crux): *no
local mechanism can watch itself; it dies with the thing it watches.* Mechanism: the capture
hook writes a **heartbeat**; the existing **launchd poller (#221, runs every 12h independent
of Claude Code sessions)** checks heartbeat-staleness and **pushes per-host coverage status
to the hub** — **a host that goes silent IS the fleet alarm** (absence is the signal; reuses
REC 0.1's fan-in). Layered: local heartbeat → independent poller → hub escalation.

### 0.2 Agent-agnostic by *design*, Claude-first by *implementation* (NEW — top principle)
The telemetry **schema**, the **adjudication anchor**, and the **validation methodology** are
**agent-agnostic**; **capture is pluggable per-agent via adapters.** The Claude Code capture
here is **the first adapter**, not a baked-in assumption — Cursor/Codex/Aider/etc. plug into
the same schema later (the public version is cross-agent or it's irrelevant).

This isn't only for reach — **it improves validity.** Agent-agnostic capture leans on the
**external, artifact-based signals that exist regardless of agent** (git/PR defects, rework,
CI, linter/type findings, tokens-where-exposed) and away from **agent-internal self-reports**
(phases, decision fields) — which are the weakest, most gameable signals. *Agent-agnostic and
high-validity point the same direction.* Sequencing mirrors the trust profile: agnostic by
design now (cheap), Claude adapter for the team MVP, more adapters for public.

### 0.3 "Automated" ≠ "measure everything" — and default-exclude is itself watched
Some work has no valid code-quality measurement (§2.5). The system **auto-classifies and
default-excludes** rather than manufacturing garbage (*measuring wrong > not measuring*). But
**default-exclude is a gaming surface** (agent-b): agents can route hard/risky work into
excluded buckets. So exclusion itself is watchdog'd (§0.1 + §2.5).

### 0.4 Every target has an anti-gaming companion (NEW — agent-b)
*"A target without a guardrail becomes a policy."* Every metric promoted to a **target** must
ship with (a) an explicit **anti-gaming companion metric** and (b) a periodic proxy-validity
re-check (§2.3). Diagnostics need no companion; targets always do.

---

## 1. Token capture — a valid efficiency sensor

**Status today: tokens are NOT captured anywhere** (verified). The token-optimization goal
has no sensor. #1 gap.

### 1.1 Source + the hidden prerequisite
`claude_code.token.usage` (OTEL, broken down by type/model) is the right source — **but OTEL
is *pushed* to an exporter, not sitting in a file** (server-a). So **build item 1.5 (a
sleeper): configure OTEL → a readable local sink** (OTLP/file exporter) *before* the
collector. The collector then reads it and attributes usage.

### 1.2 Capture the cache-aware **cost**, not raw tokens
Per unit: `{input, output, cache_creation, cache_read, model}` → **price-weighted cost (\$)**.
Cache-read ≈ 10% of fresh input; output is dearest — so **raw token count is not a valid cost
measure.** Raw tokens/cost are **diagnostics only, never targets** (Goodhart).

### 1.3 Unit honesty: per-session first, per-task/phase where derivable (server-a)
The Stop hook captures **per-session**, not per-logical-task — and **task attribution is THE
hard problem, not a footnote.** A logical task spans **main + child (subagent) sessions** →
sum across them. **Per-phase attribution only exists for orchestrated work** (phases are
subagent sessions joined via OTEL session-id); freeform has no phases. v1-real: **per-session
cost cleanly now; per-task/phase as an orchestrated-work refinement** (derive task from
orchestrate-state/branch/issue when present, else the unit *is* the session).

### 1.4 Waste, not verbosity, is the target
Most token waste is **rework** (a PROVE bounce, a re-PATCH, re-fed context) — which burns
tokens **and** signals a quality miss; same event. The legitimate target is **"eliminate
*wasted* tokens,"** which lowers cost and raises quality together.

### 1.5 Metrics + anti-gaming companions (agent-b)
| Metric | Role | Anti-gaming companion(s) |
|---|---|---|
| raw tokens / cost per phase | diagnostic | — |
| **waste-token share** | target | defect rate, PROVE coverage, repeated-reads/failed-commands, excluded-token share. *"No PROVE on implementation" = coverage failure, not a low-waste win.* |
| **cost per first-pass-correct, by complexity band** | **headline** | exclusion-rate, unclassified-rate, **task-splitting-rate**, complexity distribution; **freeze task boundaries at intake** — or at the **first implementation-like artifact** (code edit/test/commit/PR link) when no task id exists; never after outcome; **include delayed-defect penalties** in the denominator |

### 1.6 Tool / MCP / skill utilization + environment-setup overhead (Jason)

A distinct, high-value dimension: **agent-configuration efficiency** — the engine for the
Private Review's config-optimization and the public "optimize your setup for performance &
cost" feature. Fully automatable (tool/skill calls are in the session log; package installs
are observable from Bash) → fits §0.1. Behavioral/observable → hard to game (§0.5).

**Capture (per session, attributed to the active config):**
- **Utilization:** MCP servers *enabled* vs *invoked*; per-tool call counts (by source:
  built-in / MCP / which server); per-skill invocations; **last-used** per tool/skill/server.
- **Environment-setup overhead:** `pip`/`npm`/`apt` installs triggered by a task (which
  packages, time, tokens), and crucially **whether they repeat across sessions.**

**Token-cost honesty:** Claude Code **lazy-loads tool schemas** (deferred tools / ToolSearch),
so enabled-but-unused tools are *not* "100 full schemas per prompt." Real cost = the
deferred-tool **name list**, **active (non-deferred) schemas**, MCP **connection overhead**,
and **search noise** of sifting many tools. Measure it honestly; don't overclaim the tax.

**Recommendations it enables (the differentiated payoff):**
- *Disable MCP servers X, Y (0 uses / 30d) → recover ~N context tokens + connection overhead.*
- *Pre-install `reportlab`/`python-docx` in your base env — installed every doc task (~M
  tokens + T s, repeated).* (The cleaner cost win — pure repeated overhead.)
- *Skill Z unused / 60d → remove from config.*

**Validity nuance — frequency × *criticality*, not frequency alone:** a once-used tool may be
a rarely-but-critically-needed scanner. Recommend pruning only **"unused AND non-critical,"**
never "unused" (same Goodhart caution — don't strip something load-bearing). Normalize install
*time* (network confounds); the signal that matters is **repetition**, not raw seconds.

---

## 2. The adjudication anchor (renamed — *not* "ground-truth")

agent-b's central correction: **don't call automated adjudication "ground truth."** It's an
**`adjudication_anchor`** with its own validity debt — *more independent than the proxies, but
imperfect.* A fixed judge becomes the target.

### 2.1 A diverse rotating panel, never a single model (agent-b)
The anchor is a **multi-signal panel**, not one reviewer:
- **Behavioral defect tracer** (primary, §2.2) — real-world consequence.
- **GPT-5 / agent-b adversarial review** on a random **stratified** sample (successes *and*
  failures — otherwise it only audits known badness).
- **A Claude reviewer *outside* the producing path** (cross-model overlap sample).
- **Static analyzers / tests / security scanners** always collected.
Rules: reviewers **blind to the proxy labels / headline score**; **track inter-rater
agreement + calibration** against behavioral defects; **preserve dissent** (a model "pass"
never overwrites a defect signal or another reviewer's concern); **rotate prompts/rubrics +
seed adversarial cases** to detect judge drift/gaming. *This is the multi-agent requirement —
and why the hub/telemetry must support diverse agents (§0.2).*

**Minimum viable v1 panel (keep the build small — agent-b):** behavioral tracer + GPT-5
stratified review + static analyzers, *always*; the outside-path Claude overlap can be
**lower-frequency calibration** if capacity is tight.

### 2.2 Defect tracer — precision-tiered (server-a + agent-b)
Because a **contaminated anchor invalidates the entire proxy-validation loop**, **precision ≫
recall**:
- **Reverts → HIGH-precision defect/correction signal** (explicit "this reverts X") — use
  confidently, but note a revert can also undo a *clean* change for changed requirements
  (high precision, not always a "defect" — label it correction/defect, not defect-only).
- explicit "fixes regression from #PR" referencing the original → MEDIUM.
- **same-file-edit-within-window → NOISE** (files churn for non-defect reasons) — **never
  auto-mark defective**; weak hint needing corroboration only.
- **PR granularity, not commit lineage** (your **squash-merge collapses lineage** so "reverts
  commit X" won't map) — operate via the `gh` API.
- **Multiple windows (7d / 14d / 30d)** — a fixed 2-week window catches fast crashes, misses
  slow logic bugs (state the bias).
- **Human IN for tracer *calibration* (audit its first defect-marks), OUT of steady-state** —
  the one precise exception to "drop humans."

### 2.3 Proxy-validation loop — ship the *statistical mechanism*, not a disclaimer (laptop-wsl)
The cold-start is the singleton-sparse problem at the validation layer. Mechanize it:
- **Minimum-N power gate:** below adequately-powered n, **all** proxies stay **provisional** —
  neither pruned nor promoted to targeting (the `/learn` ≥5-gate medicine).
- **Downweight, never discard** at cold-start: discarding = stop collecting = can never
  re-validate (the same destructive mistake as advancing the epoch watermark). A proxy bad at
  n=10 can redeem at n=100.
- **Decide on the CI bound, not the point estimate:** if a proxy's r-CI includes 0 →
  provisional, not actioned.
- **Multiple-comparison correction (FDR/Bonferroni):** ~12 candidate proxies at p<.05 → ~0.6
  spurious "keepers" with zero real signal. Correct, or you keep a bad proxy by chance.
- **Asymmetric bars:** cheap bar to **keep collecting as a diagnostic**; strict, powered,
  corrected bar to **promote to a target** (a false-positive target is a Goodhart liability,
  far worse than a retained diagnostic).

### 2.4 Cold-start honesty
The anchor is **lagging + sparse** → v1 ships **provisional** proxies + the validation
pipeline that progressively validates/prunes them. Validity is **earned over time**, weak at
first. Stated out loud.

---

## 2.5 Work-type classification — artifact-derived, with exclusion watchdogs

| Work-type | Examples | Valid metrics |
|---|---|---|
| **Implementation** | code change (local edits/tests *or* PR/merge/PROVE) | full set |
| **Deliberative** | spec/design/research/review/discussion | no code-quality metric; cost-track; value judged downstream (§ below) |
| **Ops / admin** | git, config, running things | none |

**Classification is artifact-derived, not command-derived** (agent-b): command is *weak
evidence* (relying on the human choosing the right command re-introduces a manual dependency).
**Strongest evidence = artifact behavior: diffs, commits, PRs, tests run, CI, issue links,
files touched.** PR/merge/PROVE is the strongest implementation signal, **but local unmerged
code edits + test runs already create an implementation-like unit** that must be captured or
*explicitly* excluded (or pre-PR coding falls through the cracks).

**Deliberative value is downstream + loose** (laptop-wsl): linkage requires an **explicit
machine-readable link** (impl PR cites the spec id — the `Closes #N` discipline), *never*
proximity/temporal guessing. And it's **joint spec+impl, many-to-many, long-latency** — a
great spec + weak implementer is indistinguishable from the reverse by outcome alone. So it's
**directional, aggregate, experimental — not a per-artifact score, not a v1 deliverable.**
Cost-tracking deliberative work is the safe v1 floor. *(This spec session = cost-tracked
deliberative.)*

**Default-exclude watchdogs (agent-b — exclusion is a gaming surface):** exclusion-rate +
unclassified-rate alarms (by agent/host/workflow/repo); an **"implementation-like activity but
excluded" detector** (edits/commits/PRs/tests inside a deliberative/ops session); a
**PROVE-coverage alarm** (code change, no PROVE/CI/test evidence); **token-coverage
reconciliation** (per-task tokens must reconcile against global OTEL within tolerance, else
attribution gaps hide waste); merge/CI **ingestion-freshness** alarm (if GitHub/CI data stops,
behavioral truth silently degrades).

---

## 3. Validity bar + per-metric verdicts

Four tests: **construct validity · Goodhart/gameability · confounds · reliability.**

| Metric | Verdict |
|---|---|
| `status` PASS/BLOCKED | **WEAK** — "passed gate" ≠ "good"; gameable |
| `first_pass_correct` | **Split the definition** (agent-b): `first_prove_passed` = WEAK/gameable; `first_pass_correct_observed` (no corrective patch / reopened review / failed CI / revert in window) = much stronger. **Validity is *derived from the defect tracer*, not normalization** — standalone it conflates *correct* with *unchecked* (laptop-wsl) |
| `root_cause` / failure class | **VALID failure-diagnostic; STRUCTURALLY cannot measure quality of *successful* work** — failure telemetry by definition can't see good practice. **Needs a separate positive-signal sensor** (not a normalization fix) |
| `guards_fired` (self-reported) | **INVALID** unless artifact-derived (constant-field trap, #223) |
| `codex_overturned` | **STRONG *only when* independently derived + coverage-monitored** (agent-b) — else dormant or avoided by not invoking Codex on risky tasks |
| `duration_seconds` | **WEAK** — confounded by size; normalize; under-captured |
| `complexity`/`tier_corrected_to` | PROCESS indicator, self-reported — not quality |
| prove-log `ac_audit`/`eval_results` | **automated-review *proxy*, not closest-to-ground-truth** (agent-b) — agent-self-assessed (same ceiling as `guards_fired`; #1612 PROVE-side enforcement is the mitigation) |
| **tokens (cost, cache-aware, per phase)** | **MISSING + CRITICAL**; raw = perverse target; use cost-per-good-outcome (§1) |
| **rework / bounce rate** | **VALID but gameable** (batch fixes into first patch, skip PROVE, relabel rework as new task) — needs **boundary rules** + churn/review-comment companions |
| code-quality (lint/type/coverage/complexity) | lint/type/finding **density** = strong diagnostics; **coverage% & raw complexity gameable** (not targets); changed-line-coverage / mutation-score better but still gameable |
| `pattern_applied` / transfer-with-effect | **strong only if declared *before/during* adoption, evaluated later** (agent-b) — else over-tagged after success / untagged for risky adoptions |
| **tool/MCP/skill utilization + env-setup overhead** (§1.6) | **VALID** — behavioral, hard to game, fully automatable; strong cost/config signal. *Recommendations* need **frequency × criticality** (don't prune rare-but-critical); token tax is real but partially mitigated by lazy-loading |

**Cross-spec flag (both reviewers):** the `root_cause` structural blind spot is **one missing
sensor — *positive-signal capture* (capture what went *right*) — gating two specs** (this one
and team-knowledge auto-observe). Elevate it as a foundational build item.

---

## 4. Principles (the spine; also the public BKM)

1. **Automate or it has gaps** — + a dead-man's-switch watchdog.
2. **Agent-agnostic by design** — universal schema/anchor/methodology; pluggable capture.
3. **Normalize everything** — per complexity / per good-outcome.
4. **Separate diagnostics from targets; every target gets an anti-gaming companion.**
5. **Prefer hard-to-game, *external/behavioral* signals** over agent-internal self-reports.
6. **The anchor is a diverse panel, not a single judge** — preserve dissent, rotate rubrics.
7. **Validate proxies against the anchor — statistically** (power gate, downweight-never-discard, CI, FDR, asymmetric bars).
8. **Add a positive-signal sensor** — failure data structurally can't measure success.
9. **Fix coverage & bias first; measure exclusion itself.**

---

## 5. Build order

1. **Universal session-level capture hook** (Stop-hook slot; every work-type; artifact-derived classification).
1.5 **OTEL→readable-sink export setup** (hidden prereq, sleeper).
2. **Token collector** — read OTEL, per-session cost first, cache-aware.
3. **Dead-man's-switch watchdog** — heartbeat + #221 poller + hub coverage escalation + the §2.5 exclusion watchdogs.
4. **Precision-tiered defect tracer** — reverts-first, PR-granularity, multi-window, human-calibrated. ⭐ **long pole / critical path** (contaminating it breaks everything; interacts with squash-merge + the §7 git-inconsistency).
5. **Diverse adjudication panel** — agent-b + outside-path Claude + static analyzers; stratified sampling; dissent preserved.
6. **Proxy-validation job** — the §2.3 statistical mechanism. **Months-lagging by nature** (ongoing, not this-week).
7. **Positive-signal sensor** — capture what went *right* (gates two specs). **v1 signal
   (agent-b, concrete):** successful implementation units with **no correction within 30d +
   passed CI/PROVE + low review-comment density + no same-area rework** — imperfect, but
   breaks the failure-only dependency.
8. Populate/first-class the under-captured valid metrics.

## 6. Non-goals / deferred
Human steady-state dependency · single-model ground-truth · perfect deliberative-quality
scoring (downstream, experimental) · gameable metrics as targets · measuring ambiguous units ·
building all per-agent adapters now (Claude adapter first).

## 7. Relationships
- **Prerequisite to** the Team Knowledge MVP — the sensor its pillars aim with.
- **Agent-agnostic design enables the public cross-agent learning/benchmarking network** (§0.2).
- **The positive-signal-sensor gap gates *two* specs** (this + team-knowledge auto-observe).
- **Methodology = candidate public BKM** ("validate your agent telemetry against a diverse anchor").
- **Adjacent open spec (Jason):** git-process consistency (task #21) — interacts with the
  defect tracer (squash-merge lineage).
