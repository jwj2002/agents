# REC 0 — Outcome-Log Decision Fields (Spec, v0.2 DRAFT)

**Date:** 2026-06-04
**Author:** server-a (Claude Opus 4.8, Linux server). Reviewed adversarially by scratch (Mac) + laptop-wsl.
**Parent:** `docs/claude-workflow-improvement-plan.md` §3.8 + the cross-agent review's REC 3 ("close the feedback loop").
**Status:** DRAFT v0.2 — re-scoped per the consolidated CHANGES-REQUESTED verdict. Awaiting diff re-verify.

---

## CHANGELOG v0.1 → v0.2 (review responses)

The fleet review returned **CHANGES REQUESTED** (write-layer approved; not measurable end-to-end as
scoped). v0.2 addresses all seven gate items. Key reframe: **v0.1 would have shipped three write-only,
fleet-invisible fields — telemetry theater.** v0.2 delivers ONE field end-to-end as definition-of-done.

| # | Gate item | Resolution in v0.2 |
|---|---|---|
| 1 | Re-scope to a measurable vertical slice | §3 — `tier_corrected_to` delivered **write→shard→read→fleet-compare**; other two fields ride the frozen schema but are explicitly **DORMANT** (§3.4). |
| 2 | Promote sharding + consumer into definition-of-done | §3.2/§3.3 — metrics shard + reader are now **in REC 0**, not deferred. (Former "REC 0.1 sharding" is absorbed.) |
| 3 | Dedup merge + collision test [correctness] | §3.5 — deterministic **newest-`recorded_at`-wins** merge + collision test. Incl. accuracy note: the `flip_to_correction` trigger is actually safe (verified L476); the real risk is cross-source-file same-key. |
| 4 | `guards_fired` task-triggered + AC6a/b + variance test | §3.4 + AC6a/AC6b — defined as **task-triggered relevance** (varies by surface), labeled CLAIMED not VERIFIED, with the variance test that kills constant-theater. |
| 5 | `codex_overturned` 3-state + controlled vocab | §3.4 — `{state: not_run\|confirmed\|overturned, category}` + `_VALID_CODEX_CATEGORIES`. |
| 6 | Named `/quick` limitation + sibling map | §4 + §8 — "orchestrated work only" stated as a NAMED limitation; sibling **REC 0.2** = low-tier write-sites. |
| 7 | PIPE_BUF budget + ext4 assumption | §6 — documented; records kept compact. |

**Three theater modes named across the three reviewers — all now defended against:** *empty* (always
`[]`), *dormant* (no producer), *constant* (always all three). The unified fix is task-triggered
relevance + honest CLAIMED/VERIFIED labeling + a variance test.

---

## 1. Current state (VERIFIED against code at HEAD 4408d43)

- **`claude-config/hooks/state_manager.py`**: `record_metrics()` (L274), `record_failure()` (L353),
  `flip_to_correction()` (L424, builds the corrected record via `dict(last_record)` — copies all
  fields forward), `record_prove_audit()` (L742, holds `applicable_evals` + `eval_results`).
- **`claude-config/hooks/aggregate_metrics_to_global.py`** (Stop hook): merges per-project → **local**
  `~/.claude/memory/{metrics,failures}.jsonl`; shards **failures only** (`write_host_shard`, L281) to
  `~/agents/telemetry/<host>/failures.jsonl`. Metrics dedup = `(issue,date,project)`, last-wins
  (L228-229), **field-blind**. Whole-dict pass-through, **no allowlist** (verified) — so new fields
  survive the *local* rollup.
- **Reader = `mcp-server/tools/agent_metrics.py`** (98 lines): consumes **only** `date`, `status`,
  `complexity`, `stack`, `root_cause` (verified L42-76). Unknown fields are silently ignored.

### Verified review premises
- `metrics.status` ∈ `{PASS, BLOCKED}` (NOT `PASS|FAIL`; `FAIL` is a `prove-log` verdict). ✔
- `evals_run` already exists as `applicable_evals` in `prove-log.jsonl`. ✔
- **Blocker 2 CONFIRMED:** the reader ignores the three proposed fields → write-only without a consumer.
- **Dedup:** field-blind last-wins — fragile across source files (see §3.5); the specific
  `flip_to_correction` case is *safe* because it copies fields forward and wins by append-order.

---

## 2. The gap

`record_metrics` captures the chosen tier (`complexity`) and outcome (`status`,
`first_pass_correct`) but nothing about the **decisions** the cross-agent review flagged as
highest-leverage: was the tier **re-classified** mid-flight, which **guards** were relevant, and did
**Codex** change the output. Without a write→shard→read→compare path these are unmeasurable.

---

## 3. The change

### 3.1 Definition of done (the vertical slice)

REC 0 is **done** when `tier_corrected_to` flows end-to-end and is fleet-comparable:

```
record_metrics(tier_corrected_to=...)        # WRITE   (state_manager.py)
  → aggregate + write_metrics_shard()          # SHARD   (aggregate_metrics_to_global.py)
    → telemetry/<host>/metrics.jsonl (git)      # FLEET   (committed, cross-host visible)
      → agent_metrics reports re-tier rate      # READ    (agent_metrics.py)
```

`guards_fired` and `codex_overturned` are written on the **same frozen schema** but are **dormant**
(§3.4) — defined now so producers/consumers added later require **zero reshape**.

### 3.2 Write — `record_metrics()` additions (additive, keyword-only, default None)

```python
    tier_corrected_to: str | None = None,      # ACTIVE this rec
    guards_fired: list[str] | None = None,     # dormant (schema frozen)
    codex_overturned: dict | None = None,      # dormant (schema frozen)
```
Record-building keeps the "include only if supplied" convention so PASS records stay compact.

### 3.3 Shard + Read (promoted into DoD)

- **Shard:** new `write_metrics_shard()` in the Stop hook, mirroring `write_host_shard()` but
  **field-agnostic** (carries the whole record, so dormant fields ride for free when they light up) →
  `telemetry/<host>/metrics.jsonl`. **Volume guard:** metrics are every-task (failures are sparse), so
  the shard writes a **decision-bearing projection** (`issue, date, recorded_at, complexity,
  tier_corrected_to, status` + the two dormant fields) and defines **retention** (rotate per host, cap
  rows / age) — NOT a blind mirror of the failure shard.
- **Read:** extend `agent_metrics.py` with a **re-tier rate** (count records where
  `tier_corrected_to` present and ≠ `complexity`, grouped by initial `complexity`), reading the
  committed `telemetry/<host>/metrics.jsonl` shards for cross-host comparison.

### 3.4 Field semantics

- **`tier_corrected_to`** (ACTIVE): final tier when re-classified mid-flight; omitted when no re-tier.
  Source today: orchestrator passes it when a re-tier occurs (no REC 1/3 dependency).
- **`guards_fired`** (DORMANT until producer exists; schema frozen now): **TASK-TRIGGERED RELEVANCE**,
  not intent. `ENUM_VALUE` only when the diff touches a role/status/type/enum surface; `COMPONENT_API`
  only when a component/hook is reused; `VERIFICATION_GAP` when a structural assumption was made +
  checked. So the field **varies with task surface** (kills constant-theater). Labeled
  **CLAIMED/RELEVANT, self-reported — NOT VERIFIED-EFFECTIVE.** Two-phase: explicit-pass (orchestrator,
  task-triggered, today) → `derive_guards_fired()` from artifact evidence (PLAN file:line, MAP
  contract-sheet/VALUE, COMPONENT_API PropTypes citation) once **REC 1/3** produce those artifacts.
  Until the producer lands, the orchestrator MAY pass it explicitly; analysis MUST NOT read it as
  guard-effectiveness.
- **`codex_overturned`** (DORMANT; schema frozen): `{"state": "not_run"|"confirmed"|"overturned",
  "category": str}`. **3-state** because overturn-*rate* needs the denominator (how often Codex ran) —
  a bool conflates "ran+confirmed" with "never ran". `category` ∈ `_VALID_CODEX_CATEGORIES`
  (`auth, migration, enum_contract, cross_module, secrets, ...`, sourced from
  `implementation-routing.md` triggers). Validation fail-open: unknown category/guard dropped + logged,
  never raises into the orchestrator (mirrors `_VALID_AC_STATUSES`, L579).

### 3.5 Dedup correctness fix

Replace field-blind last-wins for metrics with **newest-`recorded_at`-wins** (every new record carries
microsecond-precision `recorded_at`, L327): on key collision keep the record with the greatest
`recorded_at`; tie-break to the field-richer record. This removes the order-dependent clobber class
(narrow today — cross-source-file same-key — but latent). **Collision test (required):** two records,
same `(issue,date,project)`, one with `tier_corrected_to` and one without, in adverse source order →
assert the merged global RETAINS the field. (AC4 round-trip is necessary but not sufficient.)

---

## 4. Named limitation (no silent cap)

REC 0 records **orchestrated work only.** `/quick` and plan-mode SIMPLE have separate write-sites and
emit no metric today — a known blind spot for the high-volume low tier where mis-tiering originates.
This is stated, not hidden. Closing it = sibling **REC 0.2** (§8). REC 0 adds **no dormant unwired
`/quick` writer** (that is the same theater trap); it only **freezes the record shape** so a future
`/quick` row is byte-identical and 0.2 is pure wiring.

---

## 5. Acceptance criteria

- **AC1** `record_metrics` persists each field when supplied, omits each when None (plain PASS record
  gains zero keys).
- **AC2** invalid guard names / unknown codex categories dropped + logged, never raise.
- **AC3** additive only: `status` enum unchanged; no field renamed; existing `agent_metrics` + `/learn`
  jq parse pre-change records identically.
- **AC4** `aggregate("metrics", …)` carries new fields through to the **local** global rollup unchanged.
- **AC4b (NEW)** dedup collision: same-key records (one with / one without `tier_corrected_to`) in
  adverse order → merged global retains the field (§3.5 merge rule).
- **AC5** `evals_run` is NOT added to metrics (lives in `prove-log.applicable_evals`).
- **AC6a** `tier_corrected_to` flows **end-to-end**: written → sharded to `telemetry/<host>/metrics.jsonl`
  → `agent_metrics` reports a cross-host **re-tier rate**. *(This is the DoD; testable today.)*
- **AC6b** `guards_fired` populated via explicit task-triggered self-report is testable today;
  **variance test:** an enum-touching task → non-empty incl `ENUM_VALUE`; a backend-no-enum task →
  `ENUM_VALUE` ABSENT. The artifact-**derived** path is deferred to REC 1/3 (not asserted here).
- **AC7 (NEW)** sharded record stays within the §6 size budget under representative field population.

## 6. Cross-env / durability notes

- **PIPE_BUF atomicity is size-bounded (4096 B).** Single-line appends are atomic only ≤ PIPE_BUF; a
  record bloated by nested `codex_overturned` + a long `guards_fired` list could exceed it and, under
  `--parallel` concurrent appends, interleave/corrupt. **Keep records compact**; the shard writes a
  projection (§3.3), not the full record.
- **Atomicity/fsync/perms assume native ext4** (not `/mnt/c`). Stated for the WSL machine.
- Backward-compat is SAFE (unknown-field tolerance) — but that tolerance is precisely why a **reader**
  (§3.3) is mandatory, else the fields are silently inert.

## 7. Non-goals

- Re-adding `evals_run`/`eval_results` to metrics (in `prove-log.jsonl`).
- Changing the `status` enum or conflating it with the PROVE `verdict`.
- A `/quick`/freeform writer (sibling REC 0.2).
- Artifact-derived `guards_fired` (REC 1/3) or new agents/phases (plan §7 forbids).

## 8. Sibling RECs (reuse REC 0's FROZEN schema — no reshape)

| REC | Scope | Depends on |
|---|---|---|
| **REC 0** (this) | `tier_corrected_to` end-to-end (write+shard+read) + frozen dormant fields | — |
| **REC 0.2** | Low-tier write-sites: record `/quick` + plan-mode SIMPLE outcomes | REC 0 frozen schema |
| **REC 1 / REC 3** | Artifact producers (PLAN evidence, MAP contract-sheet, PropTypes citation) that make `guards_fired` **derived/falsifiable** | REC 0 field defn |

Schedule REC 0.2 immediately after REC 0 — high-volume tier, high value — without bloating REC 0's
clean landing.

## 9. Test plan

New `claude-config/tests/test_state_manager_decision_fields.py`:
1. round-trip each field; present-when-supplied / absent-when-None.
2. validation: invalid guard + unknown codex category dropped; no raise.
3. backward-compat: field-less record survives `aggregate()` + `flip_to_correction()`.
4. **dedup collision** (AC4b): same key, with/without field, adverse order → field retained.
5. **shard + read** (AC6a): write → `write_metrics_shard` → `agent_metrics` re-tier rate non-zero.
6. **guards_fired variance** (AC6b): enum-task non-empty incl ENUM_VALUE; backend-no-enum omits it.
7. **size budget** (AC7): representative record ≤ PIPE_BUF.
