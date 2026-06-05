# Team Knowledge Hub — MVP v1 Spec (DRAFT v2)

**Date:** 2026-06-05
**Author:** scratch (assembling fleet input: server-a=transport, agent-b=trust/security,
laptop-wsl=pattern model). Reframed per Jason: patterns (not scaffold) as the spine.
**Status:** DRAFT — for review + fleet lane-verification before any build.

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
clustering, large/binary asset stores (deferred — §12).

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
confidence: 0.9
captured_at: '2026-06-05'
```

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
1. MAP finds **CONSENSUS** (quorum share `pattern_key` K in area A).
2. **Distill → adopted pattern** (invariant = the practice; provenance = which devs).
3. **PUBLISH-to-pool** = a PR to `team-knowledge/patterns/`; the **PR review *is* the
   endorsement gate** (same team). *Published ≠ adopted by a dev.*
4. **PROPOSE** to each dev's agent as **advisory** (inbox; never auto-enforced).
5. **ENFORCED for a dev** only after **that dev's own telemetry confirms it helps**
   (advisory-until-locally-confirmed).
6. **CONFLICT** rows never auto-promote → **arbiter = Jason** (may weigh telemetry).

Status: `proposed → published-to-pool → accepted-local → enforced-local → deprecated`.

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
  ⚠️ *privacy-gated*: opt-in **anonymized aggregates / published patterns only**, never a
  named dev or their private data (**agent-b hardens this — the one cross-dev touchpoint**).
- **Scores — Quality:** guard presence/effectiveness; declared-vs-observed delta; gaps vs
  team patterns; first-pass-correctness by command/workflow; prompt anti-patterns.
- **Scores — Efficiency:** routing mis-tiers; token/ceremony bloat; rework/bounce rate;
  Codex over/under-trigger; cycle time by task type.
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
   it (strips secrets/creds/proprietary glue) — the publish gate.
2. **Announce on the hub:** "voice-pipeline-v1 — python/pipecat, starting point for realtime
   voice" + the git ref. Register it in the **component catalog** (`team-knowledge/components/`:
   what/stack/owner/sanitized?/how-to-get).
3. Teammate's agent **clones/forks** it as their starting point and **helps adapt** it.
4. **Reviewed before building on it** — a shared artifact is *untrusted code adopted
   deliberately*, **never auto-run** (agent-b's boundary).

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
  roster.yaml                      # 4-dev allowlist {dev_id, agent_name, machine, team_tag}
  taxonomy/areas.yaml              # controlled area + pattern_key vocab
  patterns/<area>/<dev>.yaml       # each dev's per-area patterns (Pillar 1 input)
  patterns/adopted/BKM-NNN.yaml    # adopted team patterns
  components/catalog.yaml          # index of shareable components (Pillar 3) + git refs
  scripts/map_patterns.py          # assembler -> within-dev + {area x dev} divergence map
  audit/log.jsonl                  # append-only: publish/import/accept, who/when/sanitization
```

## 5. Identity = attribution, NOT authentication (server-a)

MVP-minimal: a static `roster.yaml` of 4 allowlisted devs `{dev_id, agent_name, machine,
team_tag}`. Agents self-declare `dev_id`; hub transport authenticated to membership; unknown
senders quarantined. **No crypto identity in v1** (4 known teammates) — attribution is
required (whose pattern/component is whose), authentication is not.

## 6. Trust & security — smallest safe v1 (agent-b)

**Non-negotiable even among teammates:** no transitive authority; no cross-machine action
(remote agents *propose*, only local executes); **publish/sanitize boundary** (export path
strips secrets/creds/tokens/sensitive paths/raw logs); imported knowledge **advisory**
(never silently a prompt/policy/permission/code change); provenance survives summarization;
shared artifacts are **data, not instructions**.

**v1 controls:** allowlisted roster · object types (**Pattern**, **Component**,
**Observation**) · **local publish** (sanitized draft + human/policy approval — no
auto-publish) · **local import inbox** (advisory) · plane-separated hub (signals only) ·
append-only **audit log** · hygiene (size limits, text-only messages, secret-scanning,
"team-shared" labels). **The one boundary never crossed:** no shared artifact may directly
alter local control state — only create a local proposal/inbox item.

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
5. **Pillar 3 minimal:** a `components/catalog.yaml` + the hub announce/clone handshake — so
   you can share the **voice pipeline** as the first component. *(server-a + agent-b sanitize)*
6. Private-review command (local audit → top-3) reusing the same captured patterns. *(scratch)*

**First deliverables:** (a) the pattern-divergence map across the 4 devs, (b) the voice
pipeline shared + cloned by a teammate. Measure adoption effect via `pattern_applied` (REC 0).

## 10. Non-goals / deferred (v1)

Open/cross-org federation · crypto PKI/reputation · content-addressing (one repo dedups
fine at 4-dev scale) · auto-enforcement · semantic clustering · large/binary asset store ·
full agent-config bootstrap · continuous (vs on-demand) private review.

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

### Open item for the fleet
- **Top-performer-anonymized benchmark (Pillar 2.4)** — agent-b to define the privacy
  mechanism (opt-in anonymized aggregates only; never a named dev / private data).
