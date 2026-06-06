# Telemetry Validation — Spec (DRAFT v3)

**Date:** 2026-06-05
**Author:** scratch, with Jason. Fleet-reviewed (agent-b = validity/adjudication, server-a =
capture/transport, laptop-wsl = proxy-validation) + an independent **Codex (gpt-5.5) adversarial
review** (10 findings, all folded into v3). Grounded in the 2026-06-04 `/learn` findings + a
verified audit of the current telemetry.
**Status:** DRAFT v3 — **Prerequisite** to the Team Knowledge MVP (the sensor everything else aims
with). The validation *methodology* is a candidate **public BKM**.

**v3 changes (Codex adversarial review — measurement-validity hardening):**
- **The success label is honest about its blind spot** (F1/F2/F3 — the core): the defect tracer's
  precision≫recall means *"no correction seen" ≠ "correct."* So the positive metric is renamed
  **`no_observed_defect_30d`** and requires **exposure evidence** before it counts as a good outcome;
  the LLM members of the anchor are treated as **correlated raters** (calibrated on seeded cases),
  not independent votes (§0.6, §2.1, §2.2, §3, §5).
- **Target-promotion gate** (§0.5, NEW) — no metric becomes a *target* until its source is captured,
  attribution coverage clears a threshold, proxy-validation has passed, and its anti-gaming companions
  are enforced as **disqualifiers**, not dashboards (F5/F6/F10).
- **Hub-side dead-man's-switch machinery** specified (§0.1) — expected-host registry, poller-health
  heartbeat (who watches the poller), content-completeness counters, alert semantics (F8).
- **Pre-registered proxy-validation design** (§2.3) — effect sizes, base rates, min-N, pooling, decision
  rule, and an explicit fallback when power is never reached (F4).
- **Watchdog de-circularized** (§2.5) — exclusion watchdogs use evidence *independent* of the classifier
  (F7); calibration is a defined **preflight control**, reconciling "zero-manual" with "human-in-for-
  calibration" (F9).

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

**"Absence is the signal" only works if the hub OWNS the expectation (F8 — Codex).** A silent host
is only an alarm if something on the hub *knows that host was supposed to report* and *that the
poller itself is alive.* So the hub side is specified, not assumed:
- **Expected-host/session registry** (the roster, §5-equivalent) — the hub knows the set that *should*
  report; a missing member is detectable, not invisible.
- **`last_seen` SLA per host** — exceed the deadline ⇒ alarm.
- **A poller-health heartbeat DISTINCT from the capture heartbeat** — *who watches the poller?* The
  poller emits its own liveness beat; the hub alarms if the poller goes quiet (else the watchdog dies
  silently and every host looks "fine" because nothing is checking).
- **Content-completeness + monotonic-sequence counters** — catch the **heartbeat-present-but-payload-
  empty/corrupt** failure (a beating-but-brain-dead capture hook): expected event/field counts and a
  per-shard monotonic sequence, not just "a file was touched."
- **Exporter-freshness check** (OTEL sink, §1.1) — stale token sink ⇒ alarm.
- **Explicit alert semantics** for each distinct state: *hub-unreachable*, *poller-down*,
  *heartbeat-only (empty payload)*, *corrupt payload*, *stale exporter* — each is a different failure,
  not one generic "silent."

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

### 0.4 Every target has an anti-gaming companion (agent-b)
*"A target without a guardrail becomes a policy."* Every metric promoted to a **target** must
ship with (a) an explicit **anti-gaming companion metric** and (b) a periodic proxy-validity
re-check (§2.3). Diagnostics need no companion; targets always do.

### 0.5 Target-promotion gate — a metric earns "target" status, never asserts it (NEW v3 — Codex F5/F6/F10)
The v2 failure: metrics the validity table (§3) marks WEAK/MISSING/gameable were still named as
*targets* (waste-token share, cost-per-first-pass-correct) elsewhere in the same spec. A metric may be
collected as a **diagnostic** freely, but it cannot become a **target** until **all four** hold:
1. **Source captured** — the underlying signal actually exists (tokens aren't captured today, §1).
2. **Attribution coverage ≥ threshold** — per-task/complexity attribution reconciles against global
   totals within tolerance (else the target hides unattributed work; F5).
3. **Proxy-validation passed** — it cleared the §2.3 statistical bar against the anchor (not provisional).
4. **Companions enforced as DISQUALIFIERS, not dashboards** — its anti-gaming companions (§0.4) can
   *block* the target from being read as "good," not merely sit beside it (F10).
Anything failing the gate stays a **diagnostic** and is labeled as such. **No self-reported variable
may parameterize a target** — e.g. complexity bands must be **artifact-derived** (changed lines,
files/modules, dependency depth, test surface, migration risk, review scope) and themselves validated
against the anchor before they normalize any target (F6).

### 0.6 "No defect observed" is not "correct" — the success label's honest ceiling (NEW v3 — Codex F1/F2/F3)
The deepest v2 hazard: the defect tracer is (correctly) precision≫recall, so it *misses* defects — yet
v2 reused *absence of a correction signal* as the **positive success label** in three places at once
(the anchor, `first_pass_correct`, the positive-signal sensor). Low recall then biases **all of them the
same way** — rewarding work that merely *escaped detection*. The standing rule: **a "good outcome" is
`no_observed_defect` under a stated coverage, never `correct`**, and it counts toward a denominator only
with **exposure evidence** (the work was actually tested / used / reviewed — §3, §5). LLM reviewers in
the anchor are **correlated raters** (shared model priors), calibrated on seeded cases — not independent
votes (§2.1). This principle governs §2.1, §2.2, §3, and §5.

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
| **waste-token share** | target — **TARGET-GATED (§0.5)** | defect rate, PROVE coverage, repeated-reads/failed-commands, excluded-token share (as **disqualifiers**, §0.5). *"No PROVE on implementation" = coverage failure, not a low-waste win.* |
| **cost per `no_observed_defect`, by complexity band** | **headline — TARGET-GATED (§0.5); ships as a DIAGNOSTIC until the gate clears** | exclusion-rate, unclassified-rate, **task-splitting-rate**, complexity distribution; **freeze task boundaries at intake** — or at the **first implementation-like artifact** (code edit/test/commit/PR link) when no task id exists; never after outcome; **include delayed-defect penalties** in the denominator |

**Why the headline is gated, not live (Codex F5/F6):** it depends on two things v1 has *not* solved —
**per-task cost attribution** (§1.3: per-session now; per-task only for orchestrated work) and a **valid
correctness label** (there is none — only `no_observed_defect`, §0.6). It also normalizes by **complexity
band**, which §3 marks self-reported/gameable. So until immutable task IDs + parent-child session joins +
cross-session cache allocation + attribution-coverage threshold exist (§0.5 condition 2) **and** complexity
is **artifact-derived + anchor-validated** (§0.5), this metric is published **only as a per-session cost
diagnostic alongside the excluded/unattributed-cost rate** — never as a target anyone optimizes against.

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

**Independence is OPERATIONAL, not asserted (NEW v3 — Codex F1).** Blinding + dissent do not defeat
**correlated model error** — two LLMs with shared priors miss the same things. So:
- **A producer model family/version may NOT judge its own family's work** (agent-b can't adjudicate
  agent-b-produced work; a Claude reviewer can't be the anchor for Claude-produced work it shares priors
  with). agent-b is assigned the adjudication lane *for review of OTHER producers*, never its own output.
- **LLM reviewers are weighted as CORRELATED raters, not independent votes** — N agreeing LLMs ≠ N
  independent confirmations; their agreement is discounted toward their measured correlation.
- **The two evidence classes are kept SEPARATE in the anchor:** (a) **non-LLM** — behavioral defect
  tracer + static analyzers/tests/scanners (the independent backbone); (b) **LLM review** (correlated,
  supplementary). An LLM "pass" can never outvote the non-LLM evidence.
- **Calibrate before trusting:** seed **known-defect AND known-clean** cases and track **per-rater
  sensitivity/specificity** *before* any rater's labels feed proxy-validation (§2.3) — an uncalibrated
  rater is a diagnostic, not an anchor input.

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

**Low recall must not masquerade as quality (NEW v3 — Codex F2, the strongest objection).** Precision≫
recall is right for *not false-accusing*, but it means many real defects go **unseen** — and v2 then reused
"no correction seen" as a *positive* label, so misses silently inflate quality everywhere downstream. Fixes:
- **Never treat "no detected correction" as "correct"** — a non-detection is `no_observed_defect` under the
  tracer's coverage, full stop (§0.6).
- **Add a recall-estimation layer** so coverage is *known*, not assumed: stratified **audit samples** (human
  re-checks a random slice → estimated recall), plus broader low-precision *recall* signals used only to
  estimate coverage (not to mark individual defects): review-thread outcomes, **forward-fix** detection,
  issue references, CI failures, reopened PRs, semantic same-area rework.
- **Publish positive labels with their coverage** — "no observed defect under coverage X%" — and **withhold
  any metric that depends on correctness-implied-by-absence until estimated recall exceeds a stated threshold.**

**Calibration is a defined PREFLIGHT control, reconciling §0.1's "zero manual" (NEW v3 — Codex F9).**
"Zero-manual" governs **capture**; **calibration** is a deliberate validation control, not a steady-state
dependency. Specify it: an **owner**, a **sample size**, a **cadence** (preflight before first anchor use +
periodic re-calibration), and **pass/fail criteria** — and **the tracer may NOT emit anchor labels until
calibration passes.** (So §0.1 and this exception are consistent, not contradictory.)

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

**Pre-register the design, or the mechanism is theater at 4-dev sparsity (NEW v3 — Codex F4).** The
v2 bullets name the *tools* but not the *numbers* — without them the loop can run forever proving
nothing. Before collection, fix and write down: **target effect sizes** (the smallest r worth acting
on), **defect base-rate assumptions** (so power is computable), **minimum sample size per proxy**, the
**pooling rules** (across repos/agents/time — the only way 4 devs reach power is aggregation, with its
own confounds stated), the **decision rule** (sequential or Bayesian, since data trickles in), and —
critically — the **explicit fallback when power is NOT reached by a stated sample/date horizon**
(the proxy stays a permanent diagnostic; the loop does not silently treat "underpowered" as "validated"
or block forever). Pooling caveat: cross-dev pooling assumes comparable work; stratify or it manufactures
significance from heterogeneity.

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

**The watchdog must NOT share the classifier's eyes (NEW v3 — Codex F7).** If the same artifact
visibility (the session's own diffs/commits/PR links) both *classifies* work and *watches* the
classification, a gap that hides work from the classifier hides it from the watchdog too — they go
blind together. So the watchdog draws on **evidence independent of the per-session capture**:
**ground-truth git/filesystem reconciliation** (repo/worktree snapshots, branch refs, and a
filesystem diff of what *actually* changed on disk vs what the session *reported*), **global OTEL
session totals** (independent of per-task attribution), the **expected host/session roster**
(§0.1 — sessions that should exist but produced nothing), and **ingestion completeness** against the
`gh`/CI API. A high **excluded-/unattributed-token share**, or an artifact gap the independent
reconciliation can see but the session didn't report, is **target-disqualifying (§0.5)** until resolved.

---

## 3. Validity bar + per-metric verdicts

Four tests: **construct validity · Goodhart/gameability · confounds · reliability.**

| Metric | Verdict |
|---|---|
| `status` PASS/BLOCKED | **WEAK** — "passed gate" ≠ "good"; gameable |
| `first_pass_correct` → **`no_observed_defect_30d`** | **Renamed (Codex F3): the honest name is "no defect observed," not "correct."** `first_prove_passed` = WEAK/gameable. The stronger metric (no corrective patch / reopened review / failed CI / revert in window) is **derived from the defect tracer** and therefore **bounded by the tracer's recall** (§2.2) — standalone it conflates *correct* with *unchecked* (laptop-wsl). **Counts as a good outcome ONLY with exposure evidence** (the work was actually tested/used/reviewed; §5) and **only above the §2.2 recall threshold.** Stays out of *targets* until then (§0.5/§0.6) |
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
4. **Separate diagnostics from targets; a metric EARNS target status through the §0.5 gate** —
   source captured, attribution covered, proxy-validated, companions as disqualifiers. No self-reported
   variable parameterizes a target.
5. **Prefer hard-to-game, *external/behavioral* signals** over agent-internal self-reports.
6. **The anchor is a diverse panel, not a single judge — and LLM raters are CORRELATED, not independent**
   (calibrated on seeded cases; a producer family never judges its own work). Preserve dissent, rotate rubrics.
7. **Validate proxies against the anchor — statistically AND pre-registered** (effect sizes, min-N, pooling,
   decision rule, power-never-reached fallback; power gate, downweight-never-discard, CI, FDR, asymmetric bars).
8. **"No defect observed" ≠ "correct"** — failure data structurally can't measure success; the positive sensor
   (`no_observed_defect_30d`) needs **exposure evidence** + known recall, or it just measures "unchecked."
9. **Fix coverage & bias first; measure exclusion itself — with evidence INDEPENDENT of the classifier.**

---

## 5. Build order

1. **Universal session-level capture hook** (Stop-hook slot; every work-type; artifact-derived classification).
1.5 **OTEL→readable-sink export setup** (hidden prereq, sleeper).
2. **Token collector** — read OTEL, per-session cost first, cache-aware.
3. **Dead-man's-switch watchdog** — heartbeat + #221 poller + hub coverage escalation + the §2.5 exclusion watchdogs.
4. **Precision-tiered defect tracer** — reverts-first, PR-granularity, multi-window, human-calibrated. ⭐ **long pole / critical path** (contaminating it breaks everything; interacts with squash-merge + the §7 git-inconsistency).
5. **Diverse adjudication panel** — agent-b + outside-path Claude + static analyzers; stratified sampling; dissent preserved.
6. **Proxy-validation job** — the §2.3 statistical mechanism. **Months-lagging by nature** (ongoing, not this-week).
7. **Positive-signal sensor = `no_observed_defect_30d`** — capture what went *right* (gates two
   specs), **honestly named** (Codex F3): the v1 signal (no correction within 30d + passed CI/PROVE +
   low review-comment density + no same-area rework) is **still all absence-of-failure**, so it measures
   *"unchecked for 30 days"* unless paired with **exposure evidence**. **Required before a unit counts
   as a good outcome:** a deployed/used code path, **meaningful test execution** (not just "tests
   exist"), **reviewer coverage**, **CI scope**, and **tracer coverage** above the §2.2 recall threshold.
   Without exposure, it's recorded as `unverified`, not `good`. Breaks the failure-only dependency
   **without** manufacturing a false positive label.
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
