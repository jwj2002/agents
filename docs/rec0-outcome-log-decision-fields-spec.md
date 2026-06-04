# REC 0 — Outcome-Log Decision Fields (Spec, v0.3 DRAFT)

**Date:** 2026-06-04
**Author:** server-a (Claude Opus 4.8, Linux server). Reviewed adversarially by scratch (Mac) + laptop-wsl.
**Parent:** `docs/claude-workflow-improvement-plan.md` §3.8 + the cross-agent review's REC 3 ("close the feedback loop").
**Status:** DRAFT v0.3 — Blocker 3 (shard-commit gap) downscoped per re-verify; dedup hardened to field-level. Awaiting diff re-verify.

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

## CHANGELOG v0.2 → v0.3 (re-verify responses)

Re-verify approved 6/7 v0.2 items; two findings remained. Both pushed REC 0 to a **honestly per-host**
slice — cross-fleet sync is its own infrastructure rec, not a field-add.

| Finding | Resolution in v0.3 |
|---|---|
| 🔴 **Blocker 3 — shard never committed.** Verified: `telemetry/<host>/` dirs are untracked; no hook git-adds/commits/pushes them. So write→**commit**→push→pull→read is broken at commit; "cross-host compare" reads only the local host. | **Downscoped (option b).** REC 0 DoD = **per-host re-tier rate**, read from the **local global rollup** (`~/.claude/memory/metrics.jsonl`, which already carries the field via field-agnostic aggregation — verified). `write_metrics_shard()` **and** the commit/push/pull sync move to **REC 0.1 (telemetry sync)**. Net: REC 0 shrinks to 2 files (no `aggregate` change, no shard). |
| 🟠 **Dedup — record-level newest-wins drops a provenance fact** if a later record for the key omits the field. `tier_corrected_to` is "what happened," not mutable state. | **Field-level carry-forward** for the decision-provenance fields: newest-`recorded_at` wins for mutable/outcome fields (status, first_pass_correct, …), then **carry forward** `tier_corrected_to`/`guards_fired`/`codex_overturned` from ANY record for the key if the newest lacks them. Collision test must **FAIL on the current last-wins code** (tautology guard). |

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
- **Blocker 3 CONFIRMED:** `telemetry/<host>/` shard dirs are **untracked, never git-added/committed/
  pushed** by any hook (only `worktree_manager` shells git). `jns-mac/failures.jsonl` is the sole
  tracked shard, and it's uncommitted churn. So a write→**commit**→push→pull→read chain does not exist
  — "cross-host comparison" would read only the local host. ⇒ cross-fleet sync is descoped to REC 0.1.
- **Dedup:** field-blind last-wins — fragile across source files (see §3.5); the specific
  `flip_to_correction` case is *safe* because it copies fields forward and wins by append-order.

---

## 2. The gap

`record_metrics` captures the chosen tier (`complexity`) and outcome (`status`,
`first_pass_correct`) but nothing about the **decisions** the cross-agent review flagged as
highest-leverage: was the tier **re-classified** mid-flight, which **guards** were relevant, and did
**Codex** change the output. Without a write→read path (and a consumer that surfaces it) these are
unmeasurable — even on a single host.

---

## 3. The change

### 3.1 Definition of done (the per-host vertical slice)

REC 0 is **done** when `tier_corrected_to` flows write→read **on a single host** and is reportable:

```
record_metrics(tier_corrected_to=...)        # WRITE  (state_manager.py)
  → aggregate() local rollup (field-agnostic)  # ROLLUP (~/.claude/memory/metrics.jsonl — already preserves it)
    → agent_metrics reports per-host re-tier rate   # READ  (agent_metrics.py)
```

Cross-**fleet** comparison (committing/syncing each host's shard) is **out of scope** — it's a real
sync-infrastructure rec (**REC 0.1**, §8), not a field-add (Blocker 3). `guards_fired` and
`codex_overturned` are written on the **same frozen schema** but are **dormant** (§3.4) — defined now
so producers/consumers added later require **zero reshape**.

### 3.2 Write — `record_metrics()` additions (additive, keyword-only, default None)

```python
    tier_corrected_to: str | None = None,      # ACTIVE this rec
    guards_fired: list[str] | None = None,     # dormant (schema frozen)
    codex_overturned: dict | None = None,      # dormant (schema frozen)
```
Record-building keeps the "include only if supplied" convention so PASS records stay compact.

### 3.3 Read (in DoD); Shard + Sync (descoped to REC 0.1)

- **Read (REC 0):** extend `agent_metrics.py` with a **per-host re-tier rate** — fraction of records
  where `tier_corrected_to` is present and ≠ `complexity`, grouped by initial `complexity` — reading
  the **local global rollup** `~/.claude/memory/metrics.jsonl` (which already carries `tier_corrected_to`
  via field-agnostic aggregation — verified). No shard read, no cross-host dependency.
- **Shard + Sync (REC 0.1, NOT this rec):** `write_metrics_shard()` (field-agnostic, decision-bearing
  **projection** with **retention** — metrics are every-task vs. sparse failures, so no blind mirror of
  `write_host_shard`) **plus** the mechanism that actually makes shards cross-fleet: who git-adds each
  host's shard, commit cadence, push/pull, and — the real concern — **high-frequency telemetry commits
  churning the `agents` repo history + merge handling.** That is sync infrastructure, sized separately.

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

### 3.5 Dedup correctness fix (field-level, for provenance facts)

The decision fields are **provenance facts** ("this issue *was* re-tiered"), not mutable state — so a
later record for the same key that legitimately omits the field must NOT erase the fact. Record-level
newest-wins would drop it. Therefore, on `(issue,date,project)` collision:

1. take the **newest-`recorded_at`** record as the base (for mutable/outcome fields: `status`,
   `first_pass_correct`, `corrections`, …) — `recorded_at` is microsecond-precision (L327), so this is
   deterministic; and
2. **carry forward** the decision-provenance fields (`tier_corrected_to`, `guards_fired`,
   `codex_overturned`) from ANY record for the key when the base lacks them.

**Collision test (required, with tautology guard):** two records, same `(issue,date,project)`, one with
`tier_corrected_to` and one without, in adverse source order → assert the merged global RETAINS the
field. The test MUST be authored so it **FAILS against the current last-wins implementation** (proving
it catches the real bug, not a tautology that only passes on new code). AC4 round-trip is necessary but
not sufficient.

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
- **AC4b** dedup collision (field-level): same-key records (one with / one without `tier_corrected_to`)
  in adverse order → merged global RETAINS the field (§3.5). Test MUST fail on the current last-wins
  code (tautology guard).
- **AC5** `evals_run` is NOT added to metrics (lives in `prove-log.applicable_evals`).
- **AC6a** `tier_corrected_to` flows **write→read on one host**: written → preserved in the local
  global rollup → `agent_metrics` reports a **per-host re-tier rate**. *(This is the DoD; testable
  today. Cross-fleet rate = REC 0.1.)*
- **AC6b** `guards_fired` populated via explicit task-triggered self-report is testable today;
  **variance test:** an enum-touching task → non-empty incl `ENUM_VALUE`; a backend-no-enum task →
  `ENUM_VALUE` ABSENT. The artifact-**derived** path is deferred to REC 1/3 (not asserted here).
- **AC7** a representative record (populated `tier_corrected_to` + dormant fields) stays within the §6
  PIPE_BUF size budget.

## 6. Cross-env / durability notes

- **PIPE_BUF atomicity is size-bounded (4096 B).** `record_metrics` appends one JSON line to
  `metrics.jsonl`; single-line appends are atomic only ≤ PIPE_BUF. A record bloated by nested
  `codex_overturned` + a long `guards_fired` list could exceed it and, under `--parallel` concurrent
  appends, interleave/corrupt. **Keep records compact** (and when REC 0.1 adds the shard, it writes a
  projection, not the full record).
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
| **REC 0** (this) | `tier_corrected_to` write→read **per-host** (state_manager + agent_metrics) + frozen dormant fields | — |
| **REC 0.1** | **Telemetry sync:** `write_metrics_shard()` (projection + retention) + commit/push/pull mechanism (cadence, repo-churn, merge handling, auth) that makes shards **cross-fleet** | REC 0 frozen schema |
| **REC 0.2** | Low-tier write-sites: record `/quick` + plan-mode SIMPLE outcomes | REC 0 frozen schema |
| **REC 1 / REC 3** | Artifact producers (PLAN evidence, MAP contract-sheet, PropTypes citation) that make `guards_fired` **derived/falsifiable** | REC 0 field defn |

REC 0.1 + 0.2 reuse REC 0's frozen schema (zero reshape). Schedule them right after REC 0 — both
high-value — without bloating REC 0's clean per-host landing.

## 9. Test plan

New `claude-config/tests/test_state_manager_decision_fields.py`:
1. round-trip each field; present-when-supplied / absent-when-None.
2. validation: invalid guard + unknown codex category dropped; no raise.
3. backward-compat: field-less record survives `aggregate()` + `flip_to_correction()`.
4. **dedup collision** (AC4b): same key, with/without field, adverse order → field retained; **assert
   the test fails on the pre-change last-wins code** (tautology guard).
5. **write → read per-host** (AC6a): `record_metrics(tier_corrected_to=…)` → local rollup →
   `agent_metrics` per-host re-tier rate non-zero. (No shard — that's REC 0.1.)
6. **guards_fired variance** (AC6b): enum-task non-empty incl ENUM_VALUE; backend-no-enum omits it.
7. **size budget** (AC7): representative record ≤ PIPE_BUF.
