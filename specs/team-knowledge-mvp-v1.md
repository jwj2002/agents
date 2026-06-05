# Team Knowledge Hub — MVP v1 Spec (DRAFT v3)

**Date:** 2026-06-05
**Author:** scratch (assembling fleet input: server-a=transport, agent-b=trust/security,
laptop-wsl=pattern model). Reframed per Jason: patterns (not scaffold) as the spine.
**Status:** DRAFT — for review + fleet lane-verification before any build.

**v3 changes (applied fleet-review fixes + Jason reframes):**
- **Two deployments** named (team v1 / public vNext) with a swappable trust profile (§0.5).
- **SENSE → TARGET → INVEST** operating model makes telemetry the *sensor*, not the product
  (§1.0); ties this spec to `telemetry-validation.md` (the locked sensor spec).
- **Audit = per-dev shard** `audit/<dev>.jsonl` (was a single `audit/log.jsonl` — JSONL-in-git
  append conflict), union-on-read (§4).
- **Component intake gate** hardened: quarantine-clone + manifest + pinned SHA + dangerous-file
  flagging + no-auto-run (§ Pillar 3 / §6).
- **Verified-sanitization-before-announce**: you cannot announce until the sanitize check
  passes and is logged (§ Pillar 3 / §6).
- **Top-performer privacy mechanism** resolved: opt-in, aggregate-only, k-anon cohort ≥3,
  bucketed, never a named dev (§ Pillar 2 / §6.1).
- **`catalog.yaml` schema** specified (§ Pillar 3).
- **Confidence-gating** on patterns entering the map / consensus (§1.3, §1.6).
- **Consensus-validation step** (coherence-vs-correctness against telemetry) made an explicit
  gate before publish (§1.6).
- **Tool/MCP/skill utilization + env-setup overhead** added to Pillar 2 efficiency scores
  (mirrors `telemetry-validation.md` §1.6 — the public-version cost wedge).

---

## 0.5. Two deployments, one core (team now, public next)

The pillars and the §2 north-star boundary are identical across both; only the **trust
profile** swaps (a config, not a fork):

| | **Team v1 (this spec)** | **Public vNext (deferred)** |
|---|---|---|
| Membership | static `roster.yaml`, 4 known devs | open registration + reputation |
| Trust machinery | light (attribution, not auth — §5) | full (signed artifacts, sandboxed import, federation) |
| **Leads with** | Pillar 1 (the divergence map) | **Pillar 2 + token-cost optimization** (the cold-start wedge) |
| Pillar 3 (components) | **enabled** (same-team git host) | **disabled at launch** (public code-sharing = too large an attack surface) |

The public hub's value prop = *honest, private feedback on your agent/workflow config and
your token cost*, for the expanding population of agentic-coding engineers. We design v1 so
nothing in the core has to be rebuilt to get there — only the trust profile hardens. The
hard §2 boundary (shared artifacts are **data, never instructions**) is what makes the public
version even thinkable.

---

## 1. Goal & scope

A **team of 4 developers** (same team), each running their own coding agent on their own
machine, collaborate **agent-to-agent** across **three pillars**:

1. **Patterns** — the process **identifies recurring coding patterns *within a single
   developer*** (across that dev's own projects) **and *across the team***, surfacing where
   aligning on a robust pattern saves time for both agents and developers.
2. **Private Developer Review** — each dev can, in isolation, get a full private review of
   their own workflow/agents/commands/prompts + behavior, with constructive feedback to
   improve **code quality and efficiency**. Shared only with that developer.
3. **Shareable Components / Starting-Point Templates** — a dev can share a concrete working
   artifact (e.g. a voice pipeline) so a teammate can use it as a starting point.

**Out of scope (v1):** open/cross-org federation, crypto PKI, auto-enforcement, semantic
clustering, large/binary asset stores (deferred — §10).

## 2. North star (governing principle — all four agents converged, agent-b sharpest)

> **A knowledge EXCHANGE, not a command hub.** Share *patterns, reviews, and components* —
> never *control*. Every shared artifact is **data, not instructions**. No remote message
> or artifact may alter local control state (tools, credentials, prompts, trusted-memory,
> repo files, CI, shell) — it can only create a **local proposal / inbox item**. Same-team
> trust lets the *machinery* be light; this *boundary* stays hard even among teammates.

## 3. Vocabulary (the unit ladder)

| Unit | What it is |
|---|---|
| **Practice** | What a dev actually does (raw, per-dev, auto-observed). |
| **Pattern** | A **recurring** practice — identified **within a dev** (across their projects) or **across the team**. The core output of Pillar 1. |
| **Adopted pattern (BKM)** | A team-level pattern the team converges on as the robust/best way — advisory-until-locally-confirmed. |
| **Component / template** | A concrete shareable code artifact (Pillar 3) — a working *implementation* to start from, not a distilled lesson. |

**Comparability** (the load-bearing lesson from this session): patterns only align if keyed
to a **shared practice-area taxonomy** (controlled `area` + `pattern_key`) — without it,
dev A's "error handling" and dev B's "exception strategy" never match (#223). And the team
maps on the **invariant** (the method/prose); a code *example* travels only when the
context is genuinely shared, else it stays illustrative.

---

## PILLAR 1 — Patterns (within-developer + across-team)

### 1.0 Operating model: SENSE → TARGET → INVEST
Telemetry is the **sensor**, not the product. The loop has three deliberately separated stages:

| Stage | Who/what | What it does | Trust |
|---|---|---|---|
| **SENSE** | telemetry (auto) | Auto-observes each dev's practices + outcomes (LRs, metrics, decision fields, git). **No judgment** — just signal. | mechanical |
| **TARGET** | `map_patterns.py` (auto) | Points at where a shared pattern would *pay off*: within-dev inconsistency, team divergence, recurring failure clusters. **Prioritizes; does not decide.** | mechanical |
| **INVEST** | the team (deliberate) | Humans/agents capture the pattern, **validate it against telemetry**, and adopt it. The expensive, judgment-heavy step is reserved for targets the sensor flagged as worth it. | deliberate |

**Why the split matters:** it keeps the cheap mechanical stages (SENSE, TARGET) honest and
fully automated, while the costly human attention (INVEST) is spent only where the sensor
says there's signal. This is the same sensor that `telemetry-validation.md` (LOCKED) certifies
as a *valid measurement* — Pillar 1 is its first consumer. A target the telemetry can't yet
sense (e.g. token cost, until that sensor lands) is a known blind spot, not a silent gap.

### 1.1 The process: discover, don't assume
The analysis is **bottom-up**: scan each dev's actual projects + telemetry to **discover**
their **common stack** (frameworks/libs/db they reuse) and the **areas where a consistent
pattern would help** — first **within each developer** (where they solve the same thing
differently across their own repos = a personal-consistency win), then **across the team**
(where the team's shared stack diverges = a team-alignment win). Commonality is *found in
the data*, not assumed from any fixed baseline.

### 1.2 Capture = AUTO-OBSERVE primary (Jason)
Each dev's agent **derives** practices from their telemetry + artifacts (LRs, metrics, git
history, the `guards_fired`/`codex_overturned` decision fields) by mapping observed behavior
onto `pattern_key`s via the **#223 retro-map taxonomy** — the observed-behavior→coded-key
bridge we already built. Explicit-declare is optional/supplementary; where a dev declares,
the **declared-vs-observed delta is gold** (claims "always tests" but has `MISSING_TEST`
failures = a self-conflict). Unmapped observations stay **UNMAPPED** (surfaced as a
taxonomy-gap signal, never force-bucketed — the #223 fake-consensus guard).

### 1.3 Pattern schema (reuses LR/pattern shape — laptop-wsl)
```yaml
schema_version: 1
id: PRAC-<dev>-<area>-NNN
dev: jason
area: error-handling               # CONTROLLED (taxonomy/areas.yaml)
pattern_key: CUSTOM_EXC_PER_MODULE  # CONTROLLED cluster key; UNMAPPED if none fits
practice: "Custom exception class per module; never bare except."  # the INVARIANT (mappable)
rationale: "Traceable, module-scoped catch."
stack_scope: [python, fastapi]     # discovered stack -> applicability
instantiation: "class FooError(ModuleError): ..."   # OPTIONAL example — NOT used for matching
source: observed | declared | observed+declared
evidence: "LR-001; 12 corrections"
confidence: 0.9                    # GATED — see below
captured_at: '2026-06-05'
```

**Confidence-gating (so the map isn't polluted by weak signal):** `confidence` is derived from
evidence strength, not asserted. **For v1 it is a simple, inspectable function — NOT a learned/
opaque score** (an opaque confidence would manufacture or suppress consensus invisibly, the §7
anti-theater failure). MVP form: `confidence = min(1.0, log2(1 + observation_count) / log2(1 + N_cap))`
(a capped-log of how many times the practice was observed, `N_cap` a config knob) **+ a fixed
corroboration bonus** (e.g. +0.2, clamped to 1.0) when telemetry independently agrees, and a
**penalty** when `source` is `declared`-only with no observation behind it. Every term is
readable in the YAML; no black box. Two floors:
- **`confidence < 0.4` → `low-confidence`**: still captured + visible in a dev's own map, but
  **excluded from team CONSENSUS/CONFLICT classification** (it can't push the team to adopt or
  arbitrate). Surfaced as "needs more evidence," never silently dropped.
- A pattern only contributes to a **CONSENSUS** count when `confidence ≥ 0.4` **and** `source`
  includes `observed` (a purely-declared claim never alone trips quorum — the declared-vs-observed
  delta is the tell, §1.2).

The floor is a config knob in `taxonomy/areas.yaml`, tuned as the corpus grows (start
conservative; a too-low floor manufactures fake consensus — the §7 anti-theater concern).

### 1.4 The MAP mechanic (the within-dev + team analysis)
An assembler builds `CELL[area][dev]` and classifies each AREA ROW by grouping on
`pattern_key` — **at two scopes**:
- **Within-developer:** does this dev apply the same `pattern_key` consistently across
  *their own* projects, or diverge from themselves? (personal consistency / their own BKMs)
- **Across-team:** do devs share a `pattern_key`?

| Outcome | Condition | Meaning |
|---|---|---|
| **CONSENSUS** | quorum (3/4) share a `pattern_key` | adopted-pattern (BKM) candidate |
| **DIVERGENCE** | ≥2 different, non-contradictory keys | richest learning → discuss; may yield stack-scoped patterns |
| **CONFLICT** | ≥2 mutually-exclusive keys, same context | highest-value debate → **arbitrate (Jason) before adopting** |
| **GAP** | key missing for some/all in an area that matters | blind spot |

**First concrete output = the pattern map** (within each dev + the `{area×dev}` team
matrix): *"here's where you're inconsistent with yourself, and where the 4 of you diverge."*
Immediately valuable and the seed for the first adopted patterns. Deterministic keys for
MVP; semantic clustering deferred.

### 1.5 Practice-area taxonomy seed (discovered + extensible)
Seeded from the team's **discovered common stack** (and the existing
`~/agents/knowledge/patterns/` `fastapi-*`/`auth-*` files as a bootstrap): `auth` · `rbac` ·
`fastapi-layering` · `db-orm` · `data-migrations` · `caching` · `multi-tenancy` ·
`api-design` · `typing-schemas` · `error-handling` · `testing` · `git-workflow` ·
`code-review` · `dependency-mgmt` · `security` · `concurrency` · `observability-logging` ·
`documentation` · `naming-style` · `ai-agent-workflow` · `performance` · `refactoring`.
Extensible via governance (a new area minted when UNMAPPED patterns recur with a distinct
concern; an `ALL_CAPS` token in UNMAPPED = "add a key" signal, per #223).

### 1.6 Adopted-pattern lifecycle (reconciles server-a's PR-gate + agent-b's local-accept)
1. MAP finds **CONSENSUS** (quorum share `pattern_key` K in area A, confidence-gated per §1.3).
2. **VALIDATE (coherence-vs-correctness — a DISCONFIRMATION gate at MVP scale).** Quorum agreement
   is *coherence*, not *correctness* — 4 devs can share a bad habit. But at 4-dev scale a 3/4
   consensus is **3 practicing vs 1 not** — N=1 on the other side has **no power to *confirm*** K
   helps. So the team gate does the job it *can* at small N: **disconfirmation, not confirmation**
   (asymmetric bars, borrowed from `telemetry-validation.md`'s min-N power gate / downweight-never-
   discard). Check K against telemetry: is there a clear signal that the devs practicing K have
   **worse** outcomes in area A? 
   - **Contradicting evidence → BLOCK:** tag `coherent-unproven`, route to discussion / the §arbiter;
     never publish a telemetry-contradicted consensus.
   - **No contradiction → proceed as advisory** (it auto-enforces nothing anyway). Absence of
     contradiction is *not* proof — it just clears the cheap veto.
   The **real** outcome-validation accrues at **step 6 (advisory-until-locally-confirmed)**, where
   N accumulates per dev over time. The team gate catches obvious bad-habit consensus today; the
   local gate is the statistical validator as the corpus grows.
3. **Distill → adopted pattern** (invariant = the practice; provenance = which devs; the
   step-2 validation evidence attached).
4. **PUBLISH-to-pool** = a PR to `team-knowledge/patterns/`; the **PR review *is* the
   endorsement gate** (same team). *Published ≠ adopted by a dev.*
5. **PROPOSE** to each dev's agent as **advisory** (inbox; never auto-enforced).
6. **ENFORCED for a dev** only after **that dev's own telemetry confirms it helps**
   (advisory-until-locally-confirmed).
7. **CONFLICT** rows never auto-promote → **arbiter = Jason** (may weigh telemetry).

Status: `proposed → coherent-unproven → validated → published-to-pool → accepted-local → enforced-local → deprecated`.

---

## PILLAR 2 — Private Developer Review (PRIVATE coach)

Each dev runs, **in isolation**, a full review of their own workflow/agents/commands/prompts
**+ behavior**, returning a prioritized **top-3 improvements (with expected impact) + their
trend**. **Output is PRIVATE — only that developer sees it.**

**Privacy invariant:** runs **locally**; findings never leave the dev's machine. May *read*
shared artifacts (team patterns, opt-in anonymized aggregates) to benchmark, but a dev's
review is never exposed to anyone else. The only thing that can leave is a pattern the dev
**deliberately publishes** (the §publish gate). → The review is the **per-dev front door**
to Pillar 1's team map (private "improve me" and shared "align us" share one capture layer,
split by the publish gate).

- **Inputs:** config (CLAUDE.md, agents, commands, prompts) **+ behavior/telemetry**.
- **Benchmarks (all four):** (1) team patterns; (2) your own trend; (3) external
  best-practice (failure guards, routing discipline); (4) **top-performer (anonymized)** —
  ⚠️ *privacy-gated* by the §6.1 mechanism (opt-in, aggregate-only, k-anon cohort ≥3,
  bucketed; never a named dev or their private data — the one cross-dev touchpoint).
- **Scores — Quality:** guard presence/effectiveness; declared-vs-observed delta; gaps vs
  team patterns; first-pass-correctness by command/workflow; prompt anti-patterns.
- **Scores — Efficiency:** routing mis-tiers; token/ceremony bloat; rework/bounce rate;
  Codex over/under-trigger; cycle time by task type.
- **Scores — Tooling cost & utilization** (mirrors `telemetry-validation.md` §1.6 — the
  public-version cost wedge): **MCP server inventory vs actual use** (servers/tools connected
  but never invoked = dead config + token-context tax), **per-tool/skill invocation counts**,
  and **environment-setup overhead** (time/tokens lost to mid-task package installs, cold
  MCP starts, repeated dependency fetches). Output = "what to prune, pin, or pre-provision."
  This is the dimension a public agentic-coding engineer most wants honest feedback on.
- On-demand for MVP (continuous coaching deferred).

---

## PILLAR 3 — Shareable Components / Starting-Point Templates

A dev shares a **concrete working artifact** (e.g. a voice pipeline) so a teammate can use
it as a **starting point**. Distinct from a pattern: a pattern is the *method*; a component
is a *working implementation to fork*.

**Transport split (the key design): the hub COORDINATES; git TRANSFERS.** The hub is a
message bus, not a file mover — pushing code through it loses versioning/review and is a
malware/injection surface (agent-b). So:
- **git** carries the artifact (a repo / template / branch the teammate clones-or-forks).
- **the hub** does discovery + handshake (announce availability + the clone ref).

**Flow (voice-pipeline use case):**
1. Sharer's agent **packages** the artifact into a shareable repo/template + **sanitizes**
   it (strips secrets/creds/proprietary glue).
2. **VERIFIED-SANITIZATION-BEFORE-ANNOUNCE (blocking gate).** Sanitization is not announced on
   trust. A **secret-scan + sanitize-check runs and must pass**, and its result is **written to
   `audit/<dev>.jsonl`** (`{action: publish, component, commit_sha, sanitized: true, scanner,
   findings: 0}`), **before** any hub announce is permitted. A failed/again scan blocks the
   announce. *No clean-scan record in the audit shard ⇒ the catalog entry is invalid and importers
   must refuse it.* (Pairs with the §6 publish boundary.)
3. **Announce on the hub:** "voice-pipeline-v1 — python/pipecat, starting point for realtime
   voice" + the git ref **pinned to a commit SHA**. Register it in the **component catalog**
   (schema below).
4. **IMPORT via the ComponentReview intake gate (agent-b — the supply-chain boundary).** A shared
   artifact is **untrusted code adopted deliberately**. The importing agent MUST:
   - **Quarantine-clone** the **pinned SHA** into an isolated path **outside any agent-trusted
     directory** (never into `.claude/`, hooks, skills, or a path on the agent's exec/trust path).
   - Build/inspect a **manifest**: declared entrypoints, dependencies, and any **dangerous files**
     — install/post-install scripts, network-calling code, `eval`/dynamic-exec, credential/env
     readers, hook/CI files. Flagged files are surfaced to the human, not run.
   - **No-auto-run, no-auto-install:** nothing executes and no dependency is installed until the
     human reviews the manifest and approves. The component enters as an **inbox proposal**, never
     a live dependency.
   - Re-verify the importer's copy against the catalog's `commit_sha` (the announce can't point at
     one tree and ship another).
5. Teammate's agent then **helps adapt** the reviewed component as their starting point — but
   **no-auto-install survives into the adapt phase**: the real trigger isn't the clone, it's the
   helpful `pip/npm install` (firing postinstall) as step one of "adapting." Dependency
   installation stays a **human-gated** action through adapt, not just import.

**v1 boundary = static inspection only (resolved 2026-06-05).** The gate stops *silent* compromise
(no-auto-run + no-auto-install ⇒ nothing executes before a human reads the manifest), which is the
v1 threat for 4 trusted teammates. **Sandboxed *execution*** (run in a no-creds/no-network
container, observe behavior) is **deferred to the public tier (§0.5)** — there the sharer can't be
trusted at all. It's defense-in-depth, not a boundary: a sandbox only sees what one run with one
input does, so dormant/input-triggered code walks past it. Naming it as v-next keeps v1 buildable
and honest about the guarantee.

**Component catalog schema** (`team-knowledge/components/catalog.yaml`, one entry per component):
```yaml
schema_version: 1
components:
  - id: voice-pipeline-v1
    title: "Realtime voice pipeline (pipecat) — starting point"
    owner_dev: jason                 # attribution (roster.yaml)
    stack: [python, pipecat, openai-realtime]
    git_ref: "git@host:team/voice-pipeline.git"
    commit_sha: "a1b2c3d…"           # PINNED — importers clone THIS, re-verify against it
    sanitized: true                  # MUST be backed by a clean-scan record in audit/<owner>.jsonl
    sanitize_audit: "audit/jason.jsonl#<event_id>"   # provenance pointer to the gate-2 record
    dangerous_files: []              # manifest flags surfaced at publish time (e.g. ["postinstall.sh"])
    how_to_get: "clone @ commit_sha, then run ComponentReview intake (step 4)"
    published_at: '2026-06-05'
```

**Requires:** the team shares a git host → a component = a repo/template the teammate clones
(same-team makes this trivial). Cross-network fallback = **git bundle** over a transport
(your jbox06 pattern). **Large/binary assets** (datasets, audio) → a shared object store,
**deferred** (v1 = code artifacts, git's sweet spot).

---

## 4. Architecture (reuse, don't build)

- **Hub (existing channel)** = SIGNALING ONLY — announce/request/notify across all three
  pillars; routes knowledge *signals*, never executable approvals, credentials, files, or
  "perform this action" (plane separation).
- **`team-knowledge` git repo** (NEW) = durable store + curation gate (low-volume, curated,
  reviewed — git's strength). **Component artifacts** live in their own shareable repos/
  templates (cataloged here), not inside this repo.
- **Local planes per dev:** a data plane imports artifacts to an **advisory inbox**; only
  the local control plane (agent + human) acts. No federated message reaches a tool-capable
  agent as instructions.

```
team-knowledge/
  roster.yaml                      # 4-dev allowlist {dev_id, agent_name, machine, team_tag, benchmark_optin}
  taxonomy/areas.yaml              # controlled area + pattern_key vocab
  patterns/<area>/<dev>.yaml       # each dev's per-area patterns (Pillar 1 input)
  patterns/adopted/BKM-NNN.yaml    # adopted team patterns
  components/catalog.yaml          # index of shareable components (Pillar 3) + git refs
  scripts/map_patterns.py          # assembler -> within-dev + {area x dev} divergence map
  audit/<dev>.jsonl                # PER-DEV append-only shard; union-on-read (NOT one shared file)
```

**Audit = per-dev shard (not one `log.jsonl`).** A single shared append-only JSONL in git
guarantees merge conflicts the moment two devs publish concurrently (same last line, same EOF) —
the exact failure the telemetry shards already taught us (#220). Each dev appends only to **their
own** `audit/<dev>.jsonl`; readers take the **union** across shards. Each row carries an
`event_id` so the union dedups deterministically. **Reuse the *mechanism*, not the field set**
(resolved 2026-06-05): factor `aggregate_metrics_to_global`'s hashing into a parameterized
`event_id(fields)` builder that both call sites share, but give audit its **own key tuple**
`dev | ts | action | component | commit_sha` — the REC 0 tuple (`issue|date|project|root_cause|
details`) has no `root_cause`/`issue` on an audit row, so reusing it verbatim collapses distinct
events to one hash (the #225 data-loss dedup class). Carry the #225 hardening forward: recompute
`event_id` on read (never trust a provided one), window before dedup. *server-a verifies the
refactor leaves the REC 0 path it owns undisturbed.* Records are **data, not instructions** (§2) —
an audit row never triggers an action on read.

## 5. Identity = attribution, NOT authentication (server-a)

MVP-minimal: a static `roster.yaml` of 4 allowlisted devs `{dev_id, agent_name, machine,
team_tag, benchmark_optin}`. Agents self-declare `dev_id`; hub transport authenticated to
membership; unknown senders quarantined. **No crypto identity in v1** (4 known teammates) —
attribution is required (whose pattern/component is whose), authentication is not.
(`benchmark_optin` gates the §6.1 anonymized top-performer pool.)

## 6. Trust & security — smallest safe v1 (agent-b)

**Non-negotiable even among teammates:** no transitive authority; no cross-machine action
(remote agents *propose*, only local executes); **publish/sanitize boundary** (export path
strips secrets/creds/tokens/sensitive paths/raw logs); imported knowledge **advisory**
(never silently a prompt/policy/permission/code change); provenance survives summarization;
shared artifacts are **data, not instructions**.

**v1 controls:** allowlisted roster · object types (**Pattern**, **Component**,
**Observation**) · **local publish** (sanitized draft + human/policy approval — no
auto-publish) · **verified-sanitization-before-announce** (clean-scan record in `audit/<dev>.jsonl`
is a precondition for any announce — Pillar 3 gate 2) · **ComponentReview intake** for imports
(quarantine-clone the pinned SHA, manifest + dangerous-file flagging, no-auto-run/no-auto-install
— Pillar 3 gate 4) · **local import inbox** (advisory) · plane-separated hub (signals only) ·
**per-dev append-only audit shards** (`audit/<dev>.jsonl`, union-on-read, `event_id`-deduped) ·
hygiene (size limits, text-only messages, secret-scanning, "team-shared" labels). **The one
boundary never crossed:** no shared artifact may directly alter local control state — only create
a local proposal/inbox item.

### 6.1 Top-performer-anonymized benchmark — privacy mechanism (resolves the v2 open item)

Pillar 2 benchmark (4) lets a dev compare themselves to the team's best **without** exposing any
individual. The mechanism (opt-in, aggregate-only):

1. **Opt-in.** A dev's metrics enter the benchmark pool only if they opt in (`roster.yaml:
   benchmark_optin: true`). No opt-in ⇒ neither contributes to nor sees peer comparisons.
2. **k-anonymity cohort ≥ 3.** A benchmark statistic is computed/returned **only when ≥3 opted-in
   devs** are in the pool. Below 3, "top performer" would re-identify (with 2, the other dev *is*
   the benchmark) — so it returns **suppressed**, not a number.
3. **Aggregate + bucketed only.** What's exposed is a **bucketed distribution** (e.g. the cohort's
   p75 first-pass-correctness as a coarse band, or "top-quartile token cost is in range X–Y"),
   **never a raw per-dev value** and **never a name**. The requesting dev sees *where they fall vs
   the band*, not whose band it is.
4. **No private data crosses.** Only metrics already eligible for aggregation (the SENSE layer's
   outcome stats) feed it — never config text, prompts, code, or review findings (those stay
   §Pillar-2 private). The benchmark reads the **shared aggregate**, not anyone's machine.
5. **Auditable + revocable.** Opt-in/opt-out is logged; opting out removes a dev from future pools
   (already-computed bands don't retro-identify because they were k-anon ≥3 bucketed).

This is the **only** cross-dev touchpoint in the otherwise-private Pillar 2, and it is the
component that makes the **public** deployment (§0.5) tractable — same mechanism, larger cohort.

## 7. Measurement (REC 0 reuse — laptop-wsl)

Add a **`pattern_applied: {id, version, source_dev}`** decision field to outcome records
(like REC 0's `tier_corrected_to`/`codex_overturned`); the existing aggregate/learn pipeline
computes **transfer-with-effect** — an adopted pattern (or component) from dev A that, after
dev B adopted it, **fired and measurably improved B's outcomes** (first-pass-correctness) on
B's own work. **Anti-theater:** count patterns/components that *measurably changed a dev's
outcomes post-adoption* — never "captured" / "shared" / "agreed." Guard **fake consensus**
(the UNMAPPED rule) and **coherence-vs-correctness** (4 devs agreeing ≠ correct — could be a
shared bad habit; cross-validate against telemetry).

## 8. Onboarding & installer (adoption enabler — MVP-critical)

A packaged **Channel-MCP installer + hub-connection config**: *download → run → registered.*
Adds the Channel MCP to the dev's Claude Code config, sets the hub endpoint, registers
`dev_id` in `roster.yaml`, and **clones `team-knowledge`**. Minimal "connect" only — not a
full agent-config bootstrap (deferred). A team hub nobody can join is dead on arrival.

## 9. Buildable-this-week slice

1. `team-knowledge` repo + `roster.yaml` (4 devs). *(server-a)*
2. `taxonomy/areas.yaml` + the Pattern YAML schema, bootstrapped from existing
   `knowledge/patterns/`. *(laptop-wsl — load-bearing)*
3. Each agent **auto-observes** + writes `patterns/<area>/<dev>.yaml`. *(all)*
4. `map_patterns.py` emits the **within-dev + team divergence map** with
   CONSENSUS/DIVERGENCE/CONFLICT/GAP. *(server-a)*
5. **Pillar 3 minimal:** `components/catalog.yaml` (schema §Pillar 3) + the hub announce/clone
   handshake, **with the two gates in the loop from day one** — verified-sanitization-before-
   announce (gate 2) and the ComponentReview intake (gate 4: quarantine-clone pinned SHA,
   manifest, no-auto-run). Share the **voice pipeline** as the first component.
   *(server-a catalog + handshake; agent-b sanitize + intake gate)*
6. Private-review command (local audit → top-3) reusing the same captured patterns, **including
   the §Pillar-2 tooling-cost/utilization dimension**. *(scratch)*

**First deliverables:** (a) the pattern-divergence map across the 4 devs, (b) the voice
pipeline shared + cloned by a teammate. Measure adoption effect via `pattern_applied` (REC 0).

## 10. Non-goals / deferred (v1)

Open/cross-org federation · crypto PKI/reputation · content-addressing (one repo dedups
fine at 4-dev scale) · auto-enforcement · semantic clustering · large/binary asset store ·
full agent-config bootstrap · continuous (vs on-demand) private review · **sandboxed component
execution** (static inspection is the v1 boundary; sandbox = public-tier hardening, §Pillar 3).

## 11. Resolved decisions (Jason, 2026-06-05)

1. **Same team / same company.** ✓
2. **CONSENSUS quorum = 3 of 4.**
3. **Conflict arbiter = Jason** (may weigh telemetry).
4. **No shared codebase — separate projects.** Commonality is **discovered** (common stack
   per-dev + team), not assumed. **Scaffold dropped as an anchor/pillar**; "patterns" is the
   spine, identified within-dev + across-team.
5. **Capture = AUTO-OBSERVE primary** (#223 retro-map); declare optional.
6. **Private review:** config + behavior; all four benchmarks; private top-3.
7. **Installer:** Channel-MCP + hub-connection (minimal connect).
8. **Three pillars:** Patterns, Private Review, Shareable Components. **Transfer split:**
   hub coordinates, **git transfers** components (voice-pipeline use case).
9. **Two deployments** (team v1 now, public vNext) sharing one core + the §2 boundary; only
   the trust profile swaps (§0.5). Public leads with Pillar 2 + token-cost; components stay
   team-only at public launch.
10. **Telemetry is the SENSOR** (SENSE→TARGET→INVEST, §1.0), certified by the locked
    `telemetry-validation.md`. Pillar 1 is its first consumer.

### Resolved in v3 (was "Open item for the fleet")
- **Top-performer-anonymized benchmark privacy mechanism** — DEFINED (§6.1): opt-in,
  aggregate-only, k-anon cohort ≥3, bucketed, never a named dev / private data.
- **Audit shard conflict** — FIXED: per-dev `audit/<dev>.jsonl`, union-on-read (§4).
- **Component supply-chain risk** — FIXED: verified-sanitization-before-announce + the
  ComponentReview intake gate (quarantine-clone pinned SHA, manifest, no-auto-run) (§Pillar 3, §6).
- **`catalog.yaml` schema** — SPECIFIED (§Pillar 3).
- **Weak-signal / fake-consensus** — GATED: confidence floor (§1.3) + the explicit
  coherence-vs-correctness validation step (§1.6).

### Resolved with Jason (2026-06-05) — fleet to VERIFY, not re-litigate
The three v3 open questions were decided one-on-one; the fleet's job is lane-verification that the
resolved position is implementable, not to reopen the choice.
- **server-a (audit dedup):** RESOLVED — reuse the *mechanism* (parameterized `event_id(fields)`),
  audit-specific key tuple `dev|ts|action|component|commit_sha` (§4). *Verify the refactor leaves
  the REC 0 path you own undisturbed and the key tuple has no collision at publish/import/accept.*
- **agent-b (component intake):** RESOLVED — **static inspection is the v1 boundary**; no-auto-run/
  no-auto-install extended through the *adapt* phase; sandboxed execution deferred to the public
  tier (§Pillar 3, §10). *Verify static + no-auto-install actually closes the silent-compromise path
  for the 4-dev case.*
- **laptop-wsl (confidence + validation):** RESOLVED — transparent capped-log confidence function
  (§1.3); §1.6 step 2 is a **disconfirmation gate at small N** (block on contradiction, can't confirm
  from N=1), with step 6 (advisory-until-locally-confirmed) as the real validator. *Verify the
  confidence function is sane on the bootstrap corpus and the disconfirmation gate ties cleanly to
  `telemetry-validation.md`'s asymmetric-bars rule.*
