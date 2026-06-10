---
run_name: 384-context-budgets-rescored
date: 2026-06-10
config_version: 7646e1f6c4da4ad759bd3badf3fd76a911800653
notes: "Rescored against corrected keys (issue #400): case-001 leak comment removed,
  case-003 expected lists updated (+1 CRITICAL None-check, +2 WARNING E09/E12).
  Reviewer outputs identical to 2026-06-10-384-context-budgets.md — reviews not re-run.
  Original file preserved as historical record."
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

- critical_expected: 2
- critical_caught: 2
- warning_expected: 4
- warning_caught: 2
- false_positives: 0
- false_positives_known: 0
- reviewer_output_lines: 4
