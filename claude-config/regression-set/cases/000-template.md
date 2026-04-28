---
case_id: 000
title: <short descriptive title>
source: <PR URL or commit SHA>
project: <repo name>
date_added: YYYY-MM-DD
labels: [enum, migration, auth, refactor, secrets, concurrency, ...]
files_changed: N
---

# <Title>

## Source

- PR: <url>
- Commit: <sha>
- Project: <repo>
- Author: <username>

## Issue / Context

> Paste the linked issue body or 2–3 sentences of context.

## Diff

Either inline the diff (small cases) or reference it:

```diff
<diff content here, or link to commit>
```

## Expected Findings

### CRITICAL (reviewer MUST flag)

- [ ] **<eval ID or category>**: <one-line description of the bug>
  - Why CRITICAL: <e.g., "data loss", "auth bypass", "deploy break">
  - Where: `path/to/file.py:LINE`

### WARNING (reviewer SHOULD flag)

- [ ] **<category>**: <one-line description>
  - Why WARNING: <correctness/quality issue, not blocking>
  - Where: `path/to/file.py:LINE`

### SUGGESTION (nice to have)

- [ ] <description>

## Known False-Positives

Things a noisy reviewer might flag that are **not** real bugs in this case:

- "<thing>" — actually fine because <reason>

## Notes

- Any context a reviewer might miss
- Why this case was added to the regression set
- Related cases or follow-up PRs
