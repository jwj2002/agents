---
paths: ["**/specs/**", "**/.agents/**"]
---

# Spec Self-Review Checklist — Mandatory Pre-Submission Gate

**This rule is the loud, file-pattern-triggered companion to
`spec-review-workflow.md` §3.** It exists because §3 of that workflow
is the discipline that catches the majority of spec defects, but the
2026-06-03 Workspace V1 + AggregateKanban V1 R1 review proved it can
be skipped without anyone noticing — 17 of 21 R1 blockers (81%) would
have been prevented by §3 if it had been invoked.

This rule auto-loads on any session touching `specs/**` (or
`.agents/**`). The discipline below is **not optional** before
committing any spec PR you authored in this session.

---

## When this rule fires

You are authoring or substantially modifying a spec under `specs/`.
That means BOTH of:

- You're about to commit a `feat(spec)`, `spec(...)`, or `docs(spec)`
  PR, OR
- You're about to invoke `/codex:adversarial-review` (R1+) on a draft.

If either is true: **stop and run the checks below before committing.**

---

## The four mandatory checks

Adapted from `~/.claude/rules/spec-review-workflow.md` §3.1–§3.4.
Re-stated here because the spec-review-workflow rule is workflow-stage
guidance; this rule is the per-PR gate.

### Check 1 — Spec ↔ manifest cross-check (every backtick symbol)

```bash
# From the repo root:
grep -oE '\`[A-Za-z_][A-Za-z0-9_./:-]*\`' specs/<feature>.md | sort -u > /tmp/spec-symbols.txt

# Cross-check each symbol against the manifest:
grep -oE '\`[A-Za-z_][A-Za-z0-9_./:-]*\`' specs/<feature>.code-reality.md | sort -u > /tmp/manifest-symbols.txt

# Any symbol in the spec but NOT in the manifest:
comm -23 /tmp/spec-symbols.txt /tmp/manifest-symbols.txt
```

Every result is one of:
- **A load-bearing claim that wasn't verified** → add to manifest by
  reading actual code, then proceed.
- **Prose that doesn't need to be in the spec** → remove or
  un-backtick it.

If you can't fit a symbol into one of those two buckets, the spec is
making an unverified claim.

### Check 2 — Spec ↔ upstream-spec cross-check (schema/enum collisions)

**This was a 2026-06-03 R1 finding** — the Workspace V1 + AggregateKanban
spec proposed columns and enum values that collided with already-shipped
substrates. See companion rule `spec-schema-collision-check.md`.

For every table, enum, or CHECK constraint your spec touches:

```bash
# Find the migration that owns each cited table/enum/CHECK:
grep -rn "CREATE TABLE <table>\|CREATE TYPE <enum>\|ADD CONSTRAINT.*CHECK" \
    db/migrations/ specs/ | head

# Read those migrations end-to-end. Confirm:
# 1. Every column your spec proposes adding has NO collision with shipped names.
# 2. Every enum value your spec proposes extending PRESERVES all shipped values.
# 3. Every constraint your spec proposes rewriting is rewritten ADDITIVELY.
```

If you find a collision: rename, reuse, or document the collision
explicitly in the spec's migration section.

### Check 3 — Internal-consistency pass (pick 4-6 pairs)

The §3.3 owner_onboarding lesson: spec sections drift apart silently.
Pick the 4-6 pairs most likely to contradict each other and read them
in sequence.

Typical drift pairs (every spec has them):

| Pair | Why they drift |
|---|---|
| §Goals / §Principles ↔ §Schema / §Implementation | Marketing statement contradicted by what the spec actually proposes |
| §Schema migration ↔ §Rollback / §Versioning | "No data loss" claims contradicted by `DROP COLUMN` in down-migrations |
| §State machine ↔ §AC | AC names a behavior the state machine doesn't produce |
| §AC ↔ §Body | AC count or name mismatches §Body's enumeration (e.g., "5 panels" vs body lists 7) |
| §Tool/endpoint signature ↔ §Frontend consumer | Frontend dispatch needs fields the tool/endpoint doesn't expose |
| §Phase ordering ↔ §Rollback procedure | Phase N's rollback depends on Phase M still being in place |

**Read each pair in sequence (top-to-bottom of one section, then
top-to-bottom of the next). Do NOT just spot-check.** Drift is
detected by reading, not by grep.

### Check 4 — Frontend component-API verification (UI/Fullstack specs only)

Skip for backend-only specs. For specs that touch frontend code:

- Every component cited has a verified prop contract in the manifest §1.
- Every hook cited has a verified return shape in the manifest §2.
- Every design token matches the project's design-tokens (or manifest §3).
- Manifest §5 maps spec requirements to real components.
- Manifest §6 lists components considered-but-absent.

If any box is unchecked and the spec is UI/Fullstack, **V1.0 is not
ready.**

---

## Output gate

If any of Checks 1–4 surfaces a discrepancy:

1. **STOP committing.**
2. Fix the spec OR fix the manifest (whichever is wrong).
3. Re-run the check that surfaced the discrepancy.
4. Only proceed to commit after a clean pass.

**Cost:** 15-30 minutes for a moderate-sized spec.
**Savings:** documented from 2026-06-03 R1 — 17 blocker fix-ups, each
~10-20 min in adversarial-review cycles. Catches one of those: 5×
ROI minimum.

---

## When to bypass (rare)

You may skip this checklist ONLY when:

- The change is a typo / wording polish on a section without claims.
- The change is purely additive to a section already locked (e.g.,
  adding an Open-Items entry).
- You are working under an explicit operator directive that names this
  rule by file path and says "skip for this PR" with a reason.

A general "I'm in a hurry" is NOT a valid bypass. The 2026-06-03 R1
incident was specifically a "hurry to ship" case — 6 PRs in one
session, no §3 invocation, 17 preventable blockers.

---

## How this rule was born

**2026-06-03 Mavis Workspace V1 + AggregateKanban V1 R1 review.**
Codex (R1 single-reviewer) returned BLOCK on both specs with 12 + 9
blocking findings, risk 9/10 on both. Investigation
(`~/projects/buddy/.agents/outputs/r1-root-cause-analysis.md` +
`r1-corrective-proposals.md`) classified:

- 12 of 21 blockers were "process-not-applied" — `spec-review-workflow.md`
  §3 would have caught them but was skipped.
- 4 were "process-too-weak" — covered by `spec-state-machine-truth-table.md`
  (new rule, same PR).
- 4 were "process-absent" — covered by
  `spec-new-substrate-domain-sweep.md` (new rule, same PR).

The fix wasn't to add a new discipline. The fix was to make the
existing §3 discipline **impossible to skip silently** by:

1. Promoting §3 to a standalone rule (this file).
2. Frontmatter-loading on every spec touch (`paths: ["**/specs/**"]`).
3. Stating bluntly at the top: "not optional."

This is the **enforcement layer** for `spec-review-workflow.md` §3.

## Related

- `~/.claude/rules/spec-review-workflow.md` — the authoritative §3
  definition + R1-R3 convergence rules + stop conditions.
- `~/.claude/rules/spec-schema-collision-check.md` — Check 2's deep
  procedure for schema-touching specs.
- `~/.claude/rules/spec-state-machine-truth-table.md` — when Check 3
  finds a multi-section state contract.
- `~/.claude/rules/spec-new-substrate-domain-sweep.md` — when the spec
  proposes a NEW persistence substrate.
- `~/.claude/templates/code-reality-manifest.md` — template for the
  Step 4 manifest these checks cross-reference.
