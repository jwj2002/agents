# REC 0 — Outcome-Log Decision-Field Extension (Spec, v0.1 DRAFT)

**Date:** 2026-06-04
**Author:** server-a (Claude Opus 4.8, Linux server), for fleet review by scratch (Mac) + laptop-wsl.
**Parent:** `docs/claude-workflow-improvement-plan.md` §3.8 (telemetry) + the cross-agent review's REC 3 ("close the feedback loop — the fleet is flying blind").
**Status:** DRAFT — awaiting adversarial review by scratch + laptop-wsl before PATCH.

---

## 0. One-line goal

Make *decision quality* measurable by adding three decision-provenance fields to the existing
`metrics.jsonl` record — **extending** the telemetry that already exists, not rebuilding it.

---

## 1. Current state (VERIFIED against code at HEAD 4408d43)

Read directly — not assumed (VERIFICATION_GAP guard):

- **`claude-config/hooks/state_manager.py`** already has the full recorder set:
  - `record_metrics()` (L274) → appends to `<project>/.claude/memory/metrics.jsonl`.
  - `record_failure()` (L353) → `failures.jsonl` (carries `event_id`, `project`).
  - `flip_to_correction()` (L424) → first-pass-correctness flip (append-only, last-wins).
  - `record_prove_audit()` (L742) → `prove-log.jsonl`, including `applicable_evals` + `eval_results`.
- **`claude-config/hooks/aggregate_metrics_to_global.py`** (origin #195) is the `Stop` hook:
  merges per-project → global `~/.claude/memory/{metrics,failures}.jsonl`, **shards failures only**
  to `~/agents/telemetry/<host>/failures.jsonl`. Fail-open, stdlib-only. Metrics dedup key =
  `(issue, date, project)`, last-wins.
- **Existing `metrics.jsonl` schema** (from `record_metrics`):
  `{issue, date, recorded_at, status, complexity, stack, agents_run}` + optional
  `{duration_seconds, root_cause, blocking_agent, agent_versions, first_pass_correct, corrections}`.

### ⚠️ Two corrections to the relayed "ground truth" (both caught by reading the code)

1. **`evals_run[]` already exists** — as `applicable_evals` (plus a per-eval `eval_results` map) in
   `record_prove_audit()` → `prove-log.jsonl`. **REC 0 must NOT re-add evals to `metrics.jsonl`** —
   that would duplicate the field and invite drift. Reference the existing `prove-log` field instead.
2. **`metrics.status` is `PASS | BLOCKED`, not `PASS | FAIL`.** `FAIL` is a *PROVE verdict* recorded in
   `prove-log.jsonl` (`record_prove_audit`, the AC-FORBIDS-APPROVE downgrade). The two streams are
   distinct; the spec keeps `status` unchanged and does **not** conflate it with the PROVE verdict.

Net: of the four fields originally proposed (`tier_corrected_to`, `guards_fired[]`, `evals_run[]`,
`codex_overturned`), **only three are genuinely missing.** `evals_run` is already captured.

---

## 2. The gap

`record_metrics` captures *what tier was chosen* (`complexity`) and *the outcome* (`status`,
`first_pass_correct`), but nothing about the **decisions made along the way** that the cross-agent
review identified as the highest-leverage things to measure:

- Was the tier **re-classified** mid-flight? (The "SIMPLE that became FULLSTACK" leak.)
- Which **failure-pattern guards** actually fired? (Are the guards earning their keep, or is it luck?)
- Did **Codex review change the output**, or just confirm it? (Tail-risk value vs. latency.)

Without these, we cannot answer "is the playbook improving?" — REC 3's core finding.

---

## 3. The change

### 3.1 Schema additions to `metrics.jsonl` (all optional, omitted-when-empty)

| Field | Type | Meaning | Source of truth |
|---|---|---|---|
| `tier_corrected_to` | `str` | Final tier if re-classified mid-flight (e.g. `"COMPLEX"` when `complexity` started `"SIMPLE"`). Omitted when no re-tier. | Orchestrator (REC #2 tripwire sets it; until then, passed when a re-tier occurred) |
| `guards_fired` | `list[str]` | Which core guards were applied — subset of `{VERIFICATION_GAP, ENUM_VALUE, COMPONENT_API}` (extensible). Omitted when empty. | MAP/PATCH artifact frontmatter, collected by orchestrator (mirrors how `applicable_evals` comes from PROVE) |
| `codex_overturned` | `dict` | `{"overturned": bool, "category": str}` — did a Codex review change the diff, and in which risk category (`auth\|migration\|enum_contract\|...`). Omitted when Codex didn't run. | Orchestrator (knows if `/codex:*` ran and whether BLOCKING findings were applied) |

Keeps the existing "include only if supplied" convention (L333-344) so PASS records stay compact and
`/learn`'s existing jq filters keep parsing.

### 3.2 `record_metrics()` signature additions (additive, keyword-only, default None)

```python
    tier_corrected_to: str | None = None,
    guards_fired: list[str] | None = None,
    codex_overturned: dict | None = None,
```
with the matching record-building block (after L344):
```python
    if tier_corrected_to:
        record["tier_corrected_to"] = tier_corrected_to
    if guards_fired:
        record["guards_fired"] = list(guards_fired)
    if codex_overturned is not None:
        record["codex_overturned"] = dict(codex_overturned)
```

### 3.3 Validation (mirror the `_VALID_AC_STATUSES` pattern, L579)

- `_VALID_GUARDS = frozenset({"VERIFICATION_GAP", "ENUM_VALUE", "COMPONENT_API"})` — unknown guard
  names are dropped + logged (fail-open, never raise into the orchestrator).
- `codex_overturned.category` validated against a small `_VALID_CODEX_CATEGORIES` set sourced from the
  `implementation-routing.md` escalation triggers (auth, migration, enum_contract, cross_module, ...).

### 3.4 Orchestrator wiring (`claude-config/commands/orchestrate.md` Step 4)

Single writer stays the orchestrator (the #104 determinism rule). It collects the three values and
passes them to `record_metrics`. `guards_fired` is **derived from artifacts** (propose a
`derive_guards_fired()` helper symmetric with `derive_agents_run()` L520) so it's not lost to
stateless-between-dispatch tracking.

---

## 4. DECISION REQUIRED (fleet review, please weigh in)

The Stop hook **shards failures per-host** (`telemetry/<host>/failures.jsonl`) but **not metrics** —
metrics only roll up to the *local* global file. So as written, the new decision fields are
analyzable **per-host only**, NOT across the fleet. But REC 3's entire motivation was *cross-fleet*
comparison.

**Options:**
- **A (minimal):** fields live in `metrics.jsonl`, per-host analysis only. Smallest diff; doesn't
  satisfy cross-fleet comparison.
- **B (fleet-visible):** extend the Stop hook with a `write_metrics_shard()` mirroring
  `write_host_shard()` (L281) → `telemetry/<host>/metrics.jsonl`, so the committed `telemetry/` tree
  carries decision fields and the weekly `/learn --cross-project` can compare machines.

**server-a's recommendation: B**, but as a *clearly-scoped follow-up* (REC 0.1) so the field-addition
(REC 0) can land and start capturing data immediately while we settle the sharding shape. Flagging
rather than silently picking — this is the one real architectural choice here.

---

## 5. Acceptance criteria

- **AC1** `record_metrics` persists `tier_corrected_to` / `guards_fired` / `codex_overturned` when
  supplied, and omits each when not (a plain PASS record gains zero new keys).
- **AC2** invalid guard names and unknown codex categories are dropped + logged, never raise.
- **AC3** additive only: `status` enum unchanged (`PASS|BLOCKED`); no field renamed; existing
  `/learn` jq filters + `agent_metrics` parse pre-change records identically.
- **AC4** `aggregate_metrics_to_global.aggregate("metrics", ...)` carries the new fields through to
  the global rollup unchanged; the `(issue, date, project)` dedup key is unaffected.
- **AC5** `evals_run` is **not** added to `metrics.jsonl` (documented: it lives in
  `prove-log.applicable_evals`).
- **AC6** `orchestrate.md` Step 4 populates the three fields from the documented sources; a re-tiered
  run shows `tier_corrected_to`, a guard-applied run shows `guards_fired`.

## 6. Non-goals

- Re-adding `evals_run`/`eval_results` to metrics (already in `prove-log.jsonl`).
- Changing the `status` enum or conflating it with the PROVE `verdict`.
- Metrics sharding **in this rec** (deferred to the §4 decision / REC 0.1).
- New agents or phases (plan §7 forbids it).

## 7. Test plan

New `claude-config/tests/test_state_manager_decision_fields.py` (mirrors
`test_state_manager_prove_audit.py`):
1. round-trip each field; assert present-when-supplied / absent-when-None.
2. invalid guard name dropped; unknown codex category dropped; no raise.
3. backward-compat: a record written without the fields reads back clean through
   `aggregate()` and `flip_to_correction()`.
4. aggregation pass-through: a sharded/global rollup preserves the three fields and the dedup key.
