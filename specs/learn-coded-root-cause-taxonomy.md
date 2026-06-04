# Spec — Coded Root-Cause Taxonomy for `/learn` (DRAFT)

**Date:** 2026-06-04
**Origin:** Fleet `/learn --dry-run` across jns-mac + jns-server + jj-dellpro14 (3-agent run).
**Status:** DRAFT — design proposal, no implementation yet.

---

## 1. Problem (verified against real fleet data)

`/learn` clusters failures by **exact `root_cause` string** and only promotes a
prevention rule at **≥5 occurrences**. Two `root_cause` styles coexist in the
telemetry today:

- **Coded** (e.g. `ASYNCPG_POOL_VS_CONNECTION`, `OPENAI_STRICT_SCHEMA`,
  `VERIFICATION_GAP`, `MISSING_TEST`) — stable identifiers that **cluster across
  recurrences**.
- **Free-text** (e.g. *"Agent stated dependency resolved but didn't verify exact
  implementation"*, *"assumed projectionMode is always numeric"*) — a unique
  string per occurrence that can **never cluster**.

**Measured impact (2026-06-04 fleet run, deduped base ~45):** the `mymoney-dev`
corpus has **~25 free-text failures**; of these **~11 are semantically
`VERIFICATION_GAP`** (the long-documented #1 failure *class*), and the rest split
across **`SCOPE_CREEP`, `AMBIGUITY_UNRESOLVED`, `DOCUMENTATION`**. Because each is
a distinct string, the frequency gate saw **~25 singletons, 0 patterns ≥5**, and
the entire fleet `/learn` promoted **nothing** — even the ~11-instance
`VERIFICATION_GAP` signal was invisible.

> The taxonomy — not the transport — is the binding constraint. Even with perfect
> cross-fleet sync (REC 0.1), free-text root_causes will not aggregate. **But the
> fix must avoid the inverse failure** (over-bucketing distinct classes into one
> coarse code) — see §5/§7.

## 2. Goal

Make reasoning/discipline failures **learnable** by giving every failure a
**coded root_cause** drawn from a controlled vocabulary, while preserving the
human-readable detail as a separate field.

## 3. Proposed change

### 3.1 Controlled `root_cause` vocabulary
Introduce `_VALID_ROOT_CAUSES` (frozenset) covering the recurring classes,
seeded from the existing core patterns + observed codes:
`VERIFICATION_GAP, ENUM_VALUE, COMPONENT_API, MISSING_TEST, LINT_ERROR,
SCOPE_CREEP, STRUCTURE_VIOLATION, SCHEMA_DRIFT, CONCURRENCY, SILENT_FAILURE,
SQL_CORRECTNESS, LLM_OUTPUT_SCHEMA, SERVICE_WIRING, …` (extensible).

`record_failure()` keeps free-text in a **new `detail` field** and requires
`root_cause` to be a coded value; an unknown code is accepted but logged
(fail-open) so recording never breaks.

### 3.2 Retro-map existing free-text → coded (server-a's one-move fix)
A one-shot `map_freetext_root_causes.py` pass classifies historical free-text
`root_cause` strings onto coded values (keyword/rule-based first; the
"assumed/stated … without verify/validate/check" family → `VERIFICATION_GAP`).
Run over the committed shards once. Empirically (verified on the 2026-06-04 data)
this collapses the **~11 verify-family `mymoney-dev` rows into one
`VERIFICATION_GAP` cluster** that trips the ≥5 gate — while the **non-verify rows
map to their OWN codes** (`SCOPE_CREEP`, `AMBIGUITY_UNRESOLVED`, `DOCUMENTATION`),
becoming their own clusters as they recur. **Critical:** the mapper must NOT
greedily sweep all 25 into `VERIFICATION_GAP` — that re-creates the coarse
blindness in the opposite direction. Rows that match no rule **stay free-text**
(never force-mapped to `OTHER`), since forcing is its own signal loss.

### 3.3 Capture point
PROVE/PATCH outcome recording emits the coded `root_cause` (the agent already
reasons about which guard/phase failed); the free-text becomes `detail`.

## 4. Acceptance criteria

- **AC1** `record_failure()` writes a coded `root_cause` + free-text `detail`;
  legacy records without `detail` still parse.
- **AC2** validation is fail-open at the RECORD layer (a bad code never breaks
  recording), BUT an unknown code is **rejected/normalized against
  `_VALID_ROOT_CAUSES`, not merely logged** — else a typo (`VERIFICATON_GAP`)
  silently becomes a new singleton, reintroducing the exact bug this fixes.
- **AC3** the retro-map maps the **verify-family SUBSET (~11, ≥5)** onto
  `VERIFICATION_GAP`; a post-map `/learn --dry-run` shows it apply-eligible
  (currently 0). **Precision check (required):** non-verify rows
  (`SCOPE_CREEP`/`AMBIGUITY_UNRESOLVED`/`DOCUMENTATION`) are NOT swept into
  `VERIFICATION_GAP` (false-positive mapping rate ≈ 0).
- **AC4** `/learn` clustering (Step 2) and the ≥5 gate operate on coded
  `root_cause`; `detail` is surfaced as evidence, not used as a cluster key.
- **AC5 (detail-mining — prevents rule-flattening).** Prevention-checklist
  generation (Step 5/6) MUST mine the `detail` texts WITHIN a coded cluster, so a
  cluster yields **specific** preventions ("validate projectionMode is numeric"),
  not one generic "verify things" rule. Cluster by code for FREQUENCY; generate
  preventions from `detail`.
- **AC6 (granularity governance).** Split a code when its sub-clusters have
  DISTINCT preventions; unmappable rows **stay free-text** (never force-swept to
  `OTHER`). Prevents the mega-bucket (inverse) failure.

## 5. Non-goals

- Semantic/LLM clustering of `detail` text (rule-based mapping first; ML later).
- Changing the ≥5 threshold itself (tracked separately — single-high-signal
  events like `codex_overturned` are a distinct lever).
- Cross-fleet transport (REC 0.1) — orthogonal; this fixes learnability even
  per-host.

## 6. Relationships

- **Unblocks** the auto-promotion of **[[LR-007]]** (VERIFICATION_GAP discipline),
  which had to be promoted manually because the free-text rows never clustered.
- **Companion to** the `learn.md` event_id dedup fix (correct *counting*); this
  fixes *what is counted* (coded vs free-text).
- **Independent of** REC 0.1 (transport) — but together they close the loop:
  taxonomy makes lessons learnable, REC 0.1 makes the whole fleet's lessons visible.
