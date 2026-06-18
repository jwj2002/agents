---
name: spec-coherence-pass
description: When a spec plateaus across adversarial-review rounds — RISK stays flat and per-finding surgical fixes keep introducing cross-section drift — stop the surgical loop and do ONE whole-spec coherence pass (read end-to-end, build truth tables for contested contracts, reconcile every section + AC to one story), then run one final review.
---

# spec-coherence-pass

This is the spec equivalent of "stop debugging line-by-line and re-read the
whole function." Use it when round-by-round surgical fixes are no longer
converging a spec. It complements — does not replace — `/spec-review`
(which is about turning a *locked* spec into GitHub issues). This skill is
about *getting the spec to lock* when the review loop has stalled.

## When to use (trigger conditions)

Invoke a coherence pass when ANY of these hold during spec adversarial review:

- **RISK plateau** — Codex `RISK: N/10` is flat across rounds (e.g. 6 → 6 → 6).
  Reviewers are sampling, not exhausting.
- **RISK rising** — a "fix" introduced new errors or surfaced latent ones
  (e.g. 5 → 7). STOP surgical fixes immediately.
- **Drift symptom** — each per-finding edit fixes one section but contradicts
  another (an enum, a state value, a column, a timeout, a default flips between
  §A and §C).
- **At R4** — you are about to do a fourth round of pure surgical fixes. Don't.
  The owner_onboarding spec took 8 surgical rounds (~7 hours). The coherence
  pass exists to never repeat that.

Authority for the convergence/stop rules: `~/.claude/rules/spec-review-workflow.md`
§4.2 (risk trajectory), §4.3 (lock signal), §4.4 (stop conditions). This skill
operationalizes §4.4 option (a) "full hygiene pass."

## The procedure

1. **Stop the surgical loop.** Do not open the review tool. Do not make another
   one-line edit. Announce: "Spec plateaued at RISK N — switching to a
   whole-spec coherence pass."

2. **Read the spec end-to-end, once, in order.** No jumping to the contested
   section. You are reconstructing the single intended story, not patching.

3. **Build explicit truth tables for every contested contract.** A contested
   contract is anything that appears in 2+ sections and has drifted: enums,
   status/role values, state machines, column names + types, default values,
   timeouts, flag names, who-writes-what. One table per contract. Columns:
   `value/state | section(s) that define it | every section + AC that consumes it | conflict?`.
   The table is the single source of truth; the prose sections must conform to
   it, not the reverse.

4. **Reconcile every section AND every AC to the tables.** Walk the whole spec
   and the acceptance criteria. Any sentence or AC that disagrees with a truth
   table is edited to match. Resolve genuine ambiguities by reading the actual
   code/migrations/docs (5 min max per call) — do not let the spec assert a
   contract the codebase can't honor. Document the decision inline.

5. **One final review round.** Submit ONE adversarial review of the
   now-coherent spec (`/codex:adversarial-review`, or the gated wrapper). If it
   does not lock, route to §4.4 (b) architectural rethink or (c) lock with a
   "Known V1 implementation gaps" addendum — NOT another surgical round.

## Reusable prompt skeleton

Paste-ready prompt for the coherence pass itself (run it on yourself or hand to
a fresh-context agent):

```
WHOLE-SPEC COHERENCE PASS — spec has plateaued in adversarial review.

Spec: <path> (current commit <sha>)
Manifest / code-reality doc: <path or "none">
Review history: RISK trajectory <e.g. 7 → 6 → 6>; recurring finding class: <e.g.
  "status enum value disagrees between §4 and the AC table">.

Do NOT make per-finding surgical edits. Instead:

1. Read the ENTIRE spec end-to-end in order. Reconstruct the single intended
   story.
2. Build an explicit truth table for EACH contested contract (any value that
   appears in 2+ sections and has drifted: enums, states, columns+types,
   defaults, timeouts, flag names, write-ownership). Table columns:
     value/state | defined-in section(s) | consumed-by section(s) + AC(s) | conflict?
3. For every conflict, pick ONE truth. If the truth depends on actual code,
   read the code/migrations/docs (cite file:line) before choosing. Document
   each decision.
4. Reconcile EVERY section and EVERY acceptance criterion to the truth tables.
   Edit any prose/AC that disagrees.
5. Output: (a) the truth tables, (b) a list of every section/AC you changed and
   why, (c) the reconciled spec, (d) a readiness call: LOCK / NEEDS-FINAL-REVIEW
   / ARCHITECTURAL-RETHINK with reasoning.

Convergence/stop rules: ~/.claude/rules/spec-review-workflow.md §4.2–§4.4.
```

## After the pass

- If LOCK or final review passes → proceed to `/spec-review` for issue creation.
- If still not converging → §4.4 (b) rethink the premise, or (c) lock with a
  known-gaps addendum. R4+ of surgical fixes is almost never right.
