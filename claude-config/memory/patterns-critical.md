# Critical Patterns

**Provenance**: regenerated 2026-06-09 (#366) from the FULL deduped 2026
failure corpus — N=40 records, 2026-01-06 → 2026-06-07, union of
`~/agents/telemetry/*/failures.jsonl` + `~/.claude/memory/failures.jsonl`,
classified by `map_freetext_root_causes.py`. Percentages are real counts
against that N, not carried-forward claims.

**Load this file ALWAYS. patterns-full.md has per-cluster evidence.**

---

## 1. VERIFICATION_GAP — 11/40 (27.5%), the dominant cluster

**Trigger**: any assumption about code structure, spec content, data shape,
or dependency behavior.

**2026 evidence shapes** (from the corpus): "stated dependency resolved but
didn't verify implementation", "added new field without checking ALL
formulas using it", "assumed consecutive year data", "didn't verify column
dependencies and execution order", "documented expected data shapes but
didn't add validation".

**Prevention**:
- Read the spec file FIRST if referenced; read the actual code before
  asserting anything about it
- "Resolved/exists/unchanged" claims require a fresh read, not memory
- New field/parameter → grep EVERY consumer (formulas, serializers, tests)
- Data-shape assumptions get validation code, not comments

---

## 2. AMBIGUITY_UNRESOLVED — 3/40 (7.5%)

**Trigger**: two valid interpretations of a spec/issue; a contradiction you
noticed.

**2026 evidence shapes**: "identified contradiction but failed to resolve it
definitively", "discussed both interpretations but didn't pick one".

**Prevention**: pick ONE interpretation, write it down (artifact/PR body),
and flag the alternative explicitly. Noticing ambiguity without resolving
it is the failure — resolution is cheap, rework is not.

---

## 3. Long tail — 26/40 (65%): one-off infra/SQL/integration causes

No other cluster reaches 3 (SCOPE_CREEP 2, DOCUMENTATION 2, rest
singletons: SQL reserved words, asyncpg pool misuse, blocking
fire-and-forget, stub handlers, …). The lesson is the loop, not a pattern:
record root causes precisely so /learn can cluster them.

---

## Status of the legacy headline patterns

| Pattern | Old claim | 2026 corpus | Now |
|---|---|---|---|
| VERIFICATION_GAP | 63% | **27.5%** | still #1 — apply above |
| ENUM_VALUE | 26% | **0 occurrences** | mechanically gated (E01, evals runner #361); still read enum VALUEs on fullstack work |
| COMPONENT_API | 17% | **0 occurrences** | prose eval E02 + /quick gate; still read component source before reuse |

The old percentages came from an earlier (pre-2026-telemetry) corpus and
must not be quoted as current. ENUM_VALUE/COMPONENT_API remain real
fullstack risks — their absence in 2026 partly reflects less fullstack
work — but their enforcement is now mechanical, not statistical.

---

## Decision Matrix

| Situation | Action |
|-----------|--------|
| Issue references spec | Read spec FIRST |
| Claiming "X is handled/unchanged" | Re-read X now |
| New field/param | Grep every consumer |
| Two valid interpretations | Pick ONE, document why |
| Fullstack with enums | Check VALUE vs NAME (E01 runner) |
| Reusing component | Read PropTypes/source |
