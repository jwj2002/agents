---
run_name: 384-context-budgets
date: 2026-06-10
config_version: 7646e1f6c4da4ad759bd3badf3fd76a911800653
notes: First LIVE run (3 fresh-context sonnet reviewers, answer keys withheld). Triggered by #384 touching agents/_base.md + prove.md (Step 7.6). Case-001 diff comment "// BUG: uses Python NAME" stripped before review (answer leak — case needs fixing). 003's three unexpected findings (None-check on repo.get, E09 commit-in-service, E12 audit-missing) counted as false positives per strict scoring but are plausibly valid — expected-lists may be under-specified.
---

# 001 enum-mismatch

- critical_expected: 1
- critical_caught: 1
- warning_expected: 1
- warning_caught: 0
- false_positives: 0
- false_positives_known: 0
- reviewer_output_lines: 1

# 002 clean-refactor

- critical_expected: 0
- critical_caught: 0
- warning_expected: 0
- warning_caught: 0
- false_positives: 0
- false_positives_known: 0
- reviewer_output_lines: 1

# 003 missing-migration

- critical_expected: 1
- critical_caught: 1
- warning_expected: 2
- warning_caught: 0
- false_positives: 3
- false_positives_known: 0
- reviewer_output_lines: 4
