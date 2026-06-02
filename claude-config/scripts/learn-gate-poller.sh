#!/bin/bash
# learn-gate-poller.sh — periodic maintenance for the ~/agents telemetry + learn loop.
#
# Invoked by launchd: com.claude-learn-gate-poller.plist (StartInterval 43200s = 12h).
# Extracted from the plist's former inline command so the logic is readable,
# testable (`bash -n`), and editable without re-deploying the plist.
#
# Responsibilities (each best-effort, none aborts the others):
#   1. Sync the agents repo — ff-only pull of other machines' telemetry shards.
#   2. Run the learn gate; if it trips, apply cross-project patterns via /learn.
#   3. Commit + push THIS machine's telemetry shard so the working tree returns
#      to CLEAN.
#
# Why step 3 exists — the structural fix:
#   Telemetry shards (telemetry/<host>/*.jsonl) are tracked by design for
#   cross-machine aggregation (feat(learn): cross-machine git-sharded telemetry),
#   but every session appends to them, so the tree is almost always dirty. A
#   perpetually-dirty tree is what tempted autonomous runs to `git stash` to get
#   a clean ff-only pull — and then never restore, silently burying real WIP
#   (four orphaned stashes, cleaned up 2026-06-02). Committing the shard here
#   keeps the tree clean AND shares the data, removing the temptation to stash.
#   The companion behavioural rule is rules/git-workflow.md, "Working tree
#   hygiene in ~/agents".
#
# NOTE on "never commit directly to main": telemetry shard auto-commits are the
# one sanctioned exception — machine-generated data, never code, scoped to
# telemetry/ paths only, on main only.

set -uo pipefail   # deliberately NOT `-e`: every step is independently fault-tolerant

REPO="$HOME/agents"
LOG="$HOME/Library/Logs/claude-learn/poller.log"
mkdir -p "$(dirname "$LOG")"
ts()  { date -Iseconds; }
log() { echo "[$(ts)] $*" >>"$LOG"; }

cd "$REPO" || { log "FATAL: $REPO missing — aborting poller run"; exit 0; }

# Commit + push only the telemetry/ paths, only on main, with a rebase-retry so a
# concurrent push from another machine/PR doesn't strand the commit. All failures
# are logged and non-fatal; the next run retries.
commit_and_push_telemetry() {
    local branch
    branch="$(git symbolic-ref --short -q HEAD || echo '')"
    if [ "$branch" != "main" ]; then
        log "telemetry: on '$branch' not main — skip commit (avoids cross-branch push)"
        return
    fi
    if git diff --quiet -- telemetry/ && git diff --cached --quiet -- telemetry/; then
        return  # nothing to commit
    fi

    git add telemetry/ 2>>"$LOG"            || { log "telemetry: git add failed";    return; }
    git commit -q -m "chore(telemetry): shard update $(ts)" 2>>"$LOG" \
                                            || { log "telemetry: git commit failed"; return; }

    if git push --quiet origin main 2>>"$LOG"; then
        log "telemetry shard committed + pushed"
    elif git pull --rebase --quiet 2>>"$LOG" && git push --quiet origin main 2>>"$LOG"; then
        log "telemetry shard committed + pushed (after rebase)"
    else
        log "telemetry push failed (non-fatal) — commit kept locally, next run retries"
    fi
}

# 1. Sync. ff-only preserves the existing safe semantics and tolerates a dirty
#    own-shard (incoming changes touch other hosts' paths, not ours).
git pull --ff-only --quiet 2>>"$LOG" || log "pull --ff-only failed (non-fatal)"

# 2. Gate, then learn only if the gate trips (matches the former inline behaviour).
if python3 claude-config/scripts/telemetry_gate.py --verbose >>"$LOG" 2>&1; then
    claude --print "/learn --apply --cross-project --validate" >>"$LOG" 2>&1 \
        || log "/learn run failed (non-fatal)"
else
    log "learn gate not tripped — skip /learn"
fi

# 3. Return the tree to clean and share this machine's shard.
commit_and_push_telemetry

log "poller run complete"
