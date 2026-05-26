---
paths: ["**/specs/**", "**/.agents/**"]
---

# Spec Review Workflow & Best Practices

This document defines the **specification review and issue creation workflow** based on lessons learned from the flow-of-funds specification process (December 2025) and the owner_onboarding_v1 8-round review loop (May 2026).

## Overview

The spec review workflow ensures specifications are **finalized and validated** before creating GitHub issues, preventing wasted effort and maintaining consistency between specs and implementation work.

**Target:** converge in ≤ 3 adversarial review rounds. If you find yourself heading toward round 4+, something upstream (drafting discipline, manifest completeness, reviewer scope) is wrong — fix that instead of doing another surgical round. See §4.

---

## 1. Why these rules exist

The owner_onboarding_v1 spec required **8 rounds** of adversarial review (Codex + Claude in parallel) before reaching a clean state. Risk trajectory was non-monotonic (8 → 8 → 7 → 6 → 5 → 7 → 8 → 7) — risk **rose** in three rounds because each "surgical fix" introduced new code-reality errors.

Of ~14 distinct findings across 8 rounds, **6 were latent bugs from V1.0–V1.2 era** — pre-existing claims that no reviewer caught for 5+ rounds. The remaining ~8 findings were errors introduced by surgical-fix drafts that I never verified against the codebase before re-submitting.

The single highest-leverage fix is: **do code-reality verification at drafting time, not as a side-effect of review.** The next three sections operationalize this.

---

## 2. Pre-V1.0 Code-Reality Manifest (mandatory before drafting)

Before writing any spec that touches existing code, produce a companion file:

```
specs/<feature>.md                  ← the spec
specs/<feature>.code-reality.md     ← the manifest (this section)
```

Use the template at `~/.claude/templates/code-reality-manifest.md`. Fill it in by reading the actual codebase — `Read`, `Grep`, `Bash` to query the DB if needed. Do NOT skip this step on the assumption that "I roughly know the code."

The manifest captures, verbatim from the source files:

- **§1 Functions cited** — every function the spec calls/extends, with signature AND surrounding pre-write guards/branches/early returns (the round-7 lesson: locating a symbol ≠ tracing what reaches it; read 50+ lines around each cited line)
- **§2 Tables / columns** — every table the spec writes to or queries, with exact column list and unique/partial indexes
- **§3 Enums** — every enum value the spec uses, copied verbatim
- **§4 CHECK constraints** — current values for any constraint the spec extends
- **§5 Cross-module helpers** — every contract that spans modules
- **§6 Migration provenance** — for every "already in production" claim, the actual owning migration file:line
- **§7 Negative manifest** — things that look like they should exist but DON'T (prevents re-invention)

**Cost:** 30–60 minutes one-shot. **Savings:** 3–6 review rounds (the owner_onboarding spec's rounds 1, 6, 7, 8 were all manifest failures — together that's 4 rounds × 2 reviewers × ~15 min ≈ 2 hours of compute, plus drafting time).

The manifest is NOT itself an implementation deliverable. It's a drafting precondition. After spec lock, the manifest stays as a companion file so future implementation work can verify the spec against it.

---

## 3. Self-Review Checklist (before submitting V1.0 for review)

Before invoking any reviewer, the spec author runs this checklist. It takes ~15 minutes and catches the majority of grade-A errors that adversarial review would otherwise spend a full round on.

### 3.1 Spec ↔ manifest cross-check

```bash
# For every symbol the spec cites, confirm it's in the manifest with verified shape
grep -E "`[A-Za-z_][A-Za-z0-9_]*`" specs/<feature>.md | sort -u
# → cross-check each hit against specs/<feature>.code-reality.md
```

Any symbol in the spec but NOT in the manifest is either (a) a load-bearing claim that wasn't verified, or (b) prose that doesn't need to be in the spec. Either way: address before submission.

### 3.2 Execution-order trace

For every claim in the spec of the form "operation X happens via path Y":

- [ ] I read 50+ lines around Y in the actual source.
- [ ] I confirmed that no pre-write guard / early return / conditional branch can prevent X from reaching the cited line.
- [ ] If guards exist, the spec either (a) explicitly notes they apply, or (b) explains why the spec's call path bypasses them.

This is the discipline that would have caught the V1.6 `add_edge() SUPERSESSION` claim: the function exists, the SUPERSESSION code at `:1211` exists, but `find_relationship_conflict()` at `:1090` returns None first for the romantic conflict group.

### 3.3 Internal consistency

Pick the 4–6 sections of the spec most likely to drift apart (typical pairs: architecture vs. acceptance criteria, schema vs. rollback semantics, helper signatures vs. their usage sites). Read them in sequence. They should tell one story.

The V1.7→V1.8 round-8 finding was a fact-correction-model contradiction across §7.2, §7.5, §11.4, §12.3 — present since V1.0, undetected for 7 rounds because each round focused on deltas, not whole-spec coherence.

### 3.4 Output

If anything in §3.1–§3.3 fails, V1.0 is not ready. Fix and re-check before involving reviewers. Reviewers are an expensive resource (each round ≈ 20 min of agent compute + your synthesis time); don't burn them on errors you could have caught in 15 minutes.

---

## 4. Adversarial Review — Convergence Rules

### 4.1 Round cadence and reviewer count

| Round | Reviewers | Why |
|---|---|---|
| R1 | **1 reviewer** (default: Codex via `/codex:adversarial-review`) | First-pass errors are gross; one reviewer catches >90%. Two in parallel at R1 is wasteful. |
| R2 | 2 reviewers in parallel (Codex + spec-reviewer agent) | Convergence check. Two reviewers catching the same issue independently is your lock signal (§4.3). |
| R3 | 2 reviewers | Final pass. If R3 is not clean, go to §4.4 — do NOT do R4. |

### 4.2 Risk trajectory as a signal

Track Codex's `RISK: N/10` across rounds. The trajectory tells you what's happening:

- **Monotonic descent (8 → 6 → 4 → PROCEED):** healthy convergence. Continue.
- **Plateau (6 → 6 → 6):** reviewers are sampling, not exhausting. Either the spec is large enough that one pass isn't covering it, or the same class of issue keeps surfacing. Re-scope reviewer prompt.
- **Rising (e.g., 5 → 7):** a "fix" introduced new errors, or surfaced latent ones. **STOP.** Do NOT continue surgical fixes. Go to §4.4.

### 4.3 Convergence (lock) signal

Lock the spec when **both** of these hold:

1. Both reviewers return PROCEED (or PROCEED-WITH-EDITS with only nits/m findings).
2. Their findings are **convergent** — if any are non-trivial, both reviewers found them independently.

Reviewer **divergence** (one says clean, the other says BLOCK) is NOT a tiebreaker question. Resolve it by reading the underlying code/docs yourself, 5 minutes max. The owner_onboarding round-8 divergence on `ON CONFLICT DO NOTHING` semantics was settled by reading PG docs — Claude was wrong, Codex was right. Without that manual resolution, picking either reviewer would have been wrong.

### 4.4 Stop conditions (use BEFORE round 4)

If round 3 doesn't lock, choose ONE of:

- **(a) Full hygiene pass.** One exhaustive read of the entire spec against the manifest + codebase, finding all remaining latent bugs in one pass. Then submit ONE final review round. Use when most remaining findings are pre-existing-but-undetected (the owner_onboarding pattern).
- **(b) Architectural rethink.** If risk is rising or the same kind of issue keeps surfacing, the underlying design may be wrong. Step back from text edits and reconsider whether the spec's premise is reachable in the current codebase. Use when round-over-round findings include "this path is unreachable / this feature doesn't compose with X."
- **(c) Lock with known-issues addendum.** Accept the spec at current state, add §N "Known V1 implementation gaps" listing remaining findings as work-to-do in implementation tickets. Use when the architecture is right but details are noisy and implementation work would naturally close them.

R4+ of pure surgical fixes is almost never the right answer. It's what we did with owner_onboarding (8 rounds) and it cost ~7 hours.

---

## 5. Drafting → Review → Lock — the end-to-end happy path

```
┌────────────────────────────────────────────┐
│ 1. Code-Reality Manifest (§2)              │
│    30-60 min, read actual code             │
│    → specs/<feature>.code-reality.md       │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────┴─────────────────────────┐
│ 2. Draft V1.0 from manifest                │
│    Every claim sourced from §1-§7          │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────┴─────────────────────────┐
│ 3. Self-Review Checklist (§3)              │
│    15 min, spec ↔ manifest grep            │
│    Execution-order trace + internal        │
│    consistency check                        │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────┴─────────────────────────┐
│ 4. R1: Single reviewer (§4.1)              │
│    /codex:adversarial-review               │
└──────────────────┬─────────────────────────┘
                   │
              ┌────┴────┐
              │ Clean?  │
              └────┬────┘
            yes ◄──┴──► no → fix → R2: 2 reviewers
              │
              ▼
       ┌─────────────┐
       │ Convergence?│
       │  (§4.3)     │
       └─────┬───────┘
       yes  ◄┴► no → resolve divergence (5 min) → re-check
              │
              ▼
       ┌─────────────┐
       │ R3 final    │
       │ confirmation│
       └─────┬───────┘
             │
             ▼
       LOCK + tag + create issues (§6+)
```

If you're at R4 or risk has risen between rounds, route to §4.4 instead of continuing this happy path.

---

## Workflow Pattern

### ✅ CORRECT: Spec Finalization Gate

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Initial Spec Review                                      │
│    - Analyze spec against codebase                          │
│    - Identify gaps, inconsistencies, missing prerequisites  │
│    - Document findings in review artifact                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Senior Engineer / Stakeholder Feedback                   │
│    - Code review findings                                   │
│    - Identify architectural gaps                            │
│    - Clarify business requirements                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Make Decisions & Update Spec                             │
│    - Document all stakeholder decisions                     │
│    - Fix inconsistencies                                    │
│    - Add prerequisites and dependencies                     │
│    - Update effort estimates                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    ┌───────────────┐
                    │ Spec Final?   │
                    └───────┬───────┘
                            │
                ┌───────────┴────────────┐
                │                        │
              NO                        YES
                │                        │
                └──► Repeat 1-3          │
                                         ↓
                        ┌────────────────────────────────┐
                        │ 4. Commit Final Spec to Git    │
                        │    - Single version (vX)       │
                        │    - Mark as FINAL             │
                        │    - Tag commit                │
                        └────────────────────────────────┘
                                         ↓
                        ┌────────────────────────────────┐
                        │ 5. Create GitHub Issues        │
                        │    - Reference spec + commit   │
                        │    - All issues consistent     │
                        └────────────────────────────────┘
```

### ❌ INCORRECT: Create Issues Before Finalizing Spec

```
Spec Review → Decisions → Create Issues → Fix Spec
                              ↓
                    ⚠️ Issues now inconsistent with spec
                    ⚠️ Must update all issues manually
                    ⚠️ Wasted effort
```

---

## Single Source of Truth Pattern

### Specification Versioning

**DO:**
- ✅ Use **one spec file** with clear version in filename (e.g., `feature-name-v3.md`)
- ✅ Use **git commits** to track version history
- ✅ Use **git tags** for major versions (e.g., `spec-flow-of-funds-v3.0`)
- ✅ Mark final version as **FINAL** in title and status

**DON'T:**
- ❌ Keep multiple version files (v1.md, v2.md, v3.md)
- ❌ Use timestamps in filenames (spec-123125.md)
- ❌ Maintain outdated versions in main branch

### Review Document Management

**DO:**
- ✅ Keep **only the final review document** in `.agents/outputs/`
- ✅ Name clearly: `spec-review-FINAL-{feature-name}-{mmddyy}.md`
- ✅ Archive intermediate reviews if needed

**DON'T:**
- ❌ Keep multiple review iterations (creates confusion)
- ❌ Reference outdated reviews in issues

---

## Spec Finalization Checklist

Before creating GitHub issues, ensure:

### Content Completeness
- [ ] All prerequisites documented with evidence
- [ ] Current behavior accurately reflects codebase state
- [ ] All stakeholder decisions documented
- [ ] Implementation phases defined with dependencies
- [ ] Effort estimates realistic and approved
- [ ] Risk assessment complete
- [ ] Open questions resolved

### Internal Consistency
- [ ] No contradictions between sections
- [ ] Terminology used consistently
- [ ] Dependencies correctly sequenced
- [ ] Acceptance criteria align with goals

### Stakeholder Approval
- [ ] Engineering lead approval
- [ ] Product team approval (timeline, scope)
- [ ] Architecture team approval (if applicable)
- [ ] Security team approval (if applicable)

### Documentation Quality
- [ ] Status marked as "FINAL - Ready for Implementation"
- [ ] Version number in frontmatter and title
- [ ] Document history table updated
- [ ] References to other docs accurate

---

## Issue Creation Best Practices

### Issue Template Requirements

Every issue created from a spec MUST include:

```markdown
## Reference
Spec: `specs/{spec-name}-v{X}.md` (lines Y-Z)
**Spec Version**: v{X}.0 (commit {hash})

## Overview
[Clear description of what this issue implements]

## Problem
**Current State**: [What exists now]
**Required**: [What spec requires]

## Implementation
[Detailed implementation steps from spec]

## Acceptance Criteria
[Checklist from spec - do not duplicate, reference spec lines]

## Dependencies
**Depends on**: Issue #X, Issue #Y
**Blocks**: Issue #Z

## Effort Estimate
**X-Y days** (COMPLEXITY_LEVEL)
```

### Spec Version Reference Format

**Required fields:**
1. **Spec file path** with version: `specs/flow-of-funds-v3.md`
2. **Line numbers** for relevant sections: `(lines 76-88, 243-258)`
3. **Spec version**: `v3.0`
4. **Git commit hash**: `(commit abc1234)`

**Example:**
```markdown
## Reference
Spec: `specs/flow-of-funds-v3.md` (lines 434-448)
**Spec Version**: v3.0 (commit 97bc25e)
```

**Why this matters:**
- Ensures implementers reference correct version
- Git commit provides immutable reference
- Line numbers help locate exact requirements
- Version number prevents confusion with outdated specs

---

## Git Workflow for Specs

### 1. Create Initial Spec

```bash
# Create spec in specs/ directory
# Naming: feature-name-v1.md (start with v1)

# Commit initial version
git add specs/feature-name-v1.md
git commit -m "feat: Add feature-name specification v1"
git push
```

### 2. Iterate Based on Feedback

```bash
# Update spec file IN PLACE
# DO NOT create v2, v3 files yet

# Commit each iteration
git commit -am "docs: Update feature-name spec with senior feedback"
git push
```

### 3. Finalize Spec

```bash
# Update status to FINAL
# Update version number in frontmatter
# Rename file if moving to final version number

git mv specs/feature-name-v1.md specs/feature-name-v3.md  # If jumped versions
# OR just update content if keeping v1

# Commit final version
git add specs/feature-name-v3.md
git commit -m "docs: Finalize feature-name specification v3 (FINAL)"

# Tag the commit
git tag -a spec-feature-name-v3.0 -m "Feature Name Specification v3.0 FINAL"
git push && git push --tags
```

### 4. Create Issues

```bash
# Now that spec is finalized, create issues
# Each issue references: specs/feature-name-v3.md (commit abc1234)

# If spec needs updates after issues created
# Update the SAME file (v3.md)
# Increment version in frontmatter (v3.1, v3.2)
# Update affected issues
```

---

## Version Control Strategy

### Semantic Versioning for Specs

- **v1.0**: Initial draft
- **v2.0**: Major revision (after senior review)
- **v3.0**: Final approved version (ready for implementation)
- **v3.1**: Minor updates after finalization (bug fixes, clarifications)
- **v3.2**: Additional minor updates

### Git Tags

**Format**: `spec-{feature-name}-v{X}.{Y}`

**Examples**:
- `spec-flow-of-funds-v3.0` - Final approved version
- `spec-rbac-v2.0` - Second major revision
- `spec-invitation-v1.0` - Initial version

**When to tag**:
- ✅ When spec status changes to FINAL
- ✅ Before creating GitHub issues
- ✅ Before starting implementation
- ❌ Not for every minor update

---

## Lessons Learned: Flow-of-Funds Case Study

### What Went Wrong

**Problem**: Created GitHub issues from v2 spec, then found Phase 3 inconsistencies, created v3 spec.

**Impact**:
- Had to manually update issues #125 and #126
- Had 3 spec files (v1, v2, v3) causing confusion
- Had 3 review documents with overlapping content
- Wasted time cleaning up afterward

### What Would Have Been Better

**Improved Flow**:
1. ✅ Spec review → senior feedback → UPDATE spec v1 → iterate
2. ✅ Make all decisions → UPDATE spec v1 → mark as FINAL → rename to v3
3. ✅ Commit final spec
4. ✅ Create all issues referencing v3 + commit hash
5. ✅ No cleanup needed

**Time Saved**: 2-3 hours of manual issue updates and cleanup

---

## Quick Reference

### Before Creating Issues

1. Is spec marked FINAL? → If NO, keep iterating
2. Are all decisions documented? → If NO, get decisions
3. Is spec committed to git? → If NO, commit it
4. Is commit tagged? → If NO, tag it
5. Ready to create issues? → YES

### Issue Creation Checklist

- [ ] Spec is FINAL and committed
- [ ] Have git commit hash
- [ ] Issue template includes spec reference with commit
- [ ] Issue references specific line numbers
- [ ] Issue dependencies align with spec phases
- [ ] Issue effort estimates match spec

### Cleanup After Finalization

1. Delete old spec versions (if any)
2. Delete intermediate review documents
3. Keep only: final spec + final review
4. Commit cleanup
5. Push to remote

---

## Related Documentation

- **Orchestrate Workflow**: `.claude/rules/orchestrate-workflow.md`
- **Spec-Reviewer Agent**: `.claude/agents/spec-reviewer.md`
- **Feature Command**: `.claude/commands/feature-from-spec.md`
- **Backend Patterns**: `.claude/rules/backend-patterns.md`

---

## Summary

**Golden Rules**:

1. **Finalize spec BEFORE creating issues** (not after)
2. **One spec file** (use git for history, not filenames)
3. **Tag the commit** when finalizing spec
4. **Reference commit hash** in every issue
5. **Delete old versions** after finalization

Following this workflow prevents:
- ❌ Inconsistent issues
- ❌ Manual issue updates
- ❌ Confusion about canonical version
- ❌ Wasted cleanup effort

And ensures:
- ✅ Single source of truth
- ✅ Immutable references (git commits)
- ✅ Clear version history
- ✅ Efficient workflow
