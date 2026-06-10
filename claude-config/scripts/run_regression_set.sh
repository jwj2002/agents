#!/usr/bin/env bash
# run_regression_set.sh — detect agent/command prompt changes and guide a
# regression-set run.
#
# Usage:
#   bash run_regression_set.sh [--diff-range <range>]
#
# Exit 0 = no prompt files changed (regression set not required).
# Exit 1 = prompt files changed (action required — complete a regression run).

set -euo pipefail

DIFF_RANGE="origin/main...HEAD"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --diff-range)
            DIFF_RANGE="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

CHANGED=$(git diff --name-only "$DIFF_RANGE" 2>/dev/null || true)

PROMPT_FILES=$(echo "$CHANGED" | grep -E '^claude-config/(agents|commands)/.*\.md$' || true)

if [[ -z "$PROMPT_FILES" ]]; then
    echo "No agent/command prompt files changed — regression set not required."
    exit 0
fi

echo "Prompt files changed in $DIFF_RANGE:"
echo "$PROMPT_FILES" | sed 's/^/  /'
echo ""
echo "ACTION REQUIRED — complete a regression run before merging:"
echo ""
echo "  1. For each case in claude-config/regression-set/cases/, run the"
echo "     case diff through the reviewer agent (or live /codex:review)."
echo "     Record findings in a dated result file:"
echo ""
echo "       claude-config/regression-set/results/$(date +%Y-%m-%d)-<run-name>.md"
echo ""
echo "     Use claude-config/regression-set/results/template.md as your template."
echo ""
echo "  2. Score the new run against the baseline:"
echo ""
echo "       python3 claude-config/regression-set/score.py \\"
echo "         claude-config/regression-set/results/2026-06-09-baseline.md \\"
echo "         claude-config/regression-set/results/$(date +%Y-%m-%d)-<run-name>.md"
echo ""
echo "  3. A 'REGRESSED' verdict blocks the merge — fix the prompt change until"
echo "     CRITICAL recall is at least as good as the baseline."
exit 1
