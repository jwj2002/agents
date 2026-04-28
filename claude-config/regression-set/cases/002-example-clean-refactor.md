---
case_id: 002
title: Pure-rename refactor — reviewer should report nothing
source: SYNTHETIC — illustrative example, replace with a real PR
project: mymoney-dev
date_added: 2026-04-28
labels: [refactor, clean, no-findings]
files_changed: 4
---

# Pure-rename refactor — reviewer should report nothing

> **Synthetic case** — represents the "clean PR" baseline. Critical for
> measuring noise rate: a good reviewer reports nothing here. A reviewer
> that flags style nits or speculative concerns is being noisy.

## Source

- PR: (synthetic)
- Project: mymoney-dev

## Issue / Context

> Rename `UserAccount` → `Account` across the codebase for consistency
> with everything else (which already says `Account`). Pure rename, no
> behavior change, no schema change.

## Diff

Mechanical rename across:
- `backend/backend/accounts/models.py` — class rename
- `backend/backend/accounts/schemas.py` — schema name updates
- `backend/backend/accounts/services.py` — type hints
- `frontend/src/api/accounts.js` — type/JSDoc updates

No tests changed; existing tests still pass.

## Expected Findings

### CRITICAL

(none)

### WARNING

(none)

### SUGGESTION

(none — this is a clean refactor)

## Known False-Positives

A noisy reviewer might flag any of these — none are real:

- "Add tests for the rename" — no behavior changed; existing tests cover correctness
- "Update CHANGELOG" — not the project's convention
- "Should also rename the variable `user_account_id` to `account_id`" — that is a *separate*, larger change with foreign-key implications and is intentionally out of scope for this PR
- "Use `Account` consistently in comments" — comments may still say "user account" colloquially; that's fine

## Notes

- Cases like this measure **noise rate**. If reviewer A reports 0 findings and reviewer B reports 3 SUGGESTIONs on the same PR, A is doing the right thing.
- Don't reward "thoroughness" — clean PRs are clean.
