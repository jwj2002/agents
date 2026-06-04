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

**Measured impact (2026-06-04 fleet run):** the `mymoney-dev` corpus contains
**24 free-text failures that are all semantically `VERIFICATION_GAP`** — the
documented #1 failure pattern (63%). Because each is a distinct string, the
frequency gate saw **24 singletons, 0 patterns ≥5**, and the entire fleet
`/learn` promoted **nothing**. The single highest-value, highest-frequency lesson
in the data is **structurally invisible** to the learner.

> The taxonomy — not the transport — is the binding constraint. Even with perfect
> cross-fleet sync (REC 0.1), free-text root_causes will not aggregate.

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
Run over the committed shards once. This **collapses the 24 invisible
`mymoney-dev` singletons into one 24-occurrence `VERIFICATION_GAP` cluster** that
trips the ≥5 gate immediately — turning blocker #2 into a learnable pattern in a
single backfill.

### 3.3 Capture point
PROVE/PATCH outcome recording emits the coded `root_cause` (the agent already
reasons about which guard/phase failed); the free-text becomes `detail`.

## 4. Acceptance criteria

- **AC1** `record_failure()` writes a coded `root_cause` + free-text `detail`;
  legacy records without `detail` still parse.
- **AC2** `_VALID_ROOT_CAUSES` validation is fail-open (unknown code logged, never
  raises) — mirrors `_VALID_AC_STATUSES`.
- **AC3** the retro-map pass maps the 24 `mymoney-dev` "assume-don't-verify"
  rows onto `VERIFICATION_GAP`; a post-map `/learn --dry-run` shows
  `VERIFICATION_GAP ≥ 5` as an apply-eligible cluster (currently 0).
- **AC4** `/learn` clustering (Step 2) and the ≥5 gate operate on coded
  `root_cause`; `detail` is surfaced as evidence, not used as a cluster key.

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
