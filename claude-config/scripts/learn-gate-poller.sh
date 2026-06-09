#!/bin/bash
# learn-gate-poller.sh — periodic maintenance for the ~/agents telemetry + learn loop.
#
# Invoked by launchd: com.claude-learn-gate-poller.plist (StartInterval 43200s = 12h).
# Extracted from the plist's former inline command so the logic is readable,
# testable (`bash -n`), and editable without re-deploying the plist.
#
# Responsibilities (each best-effort, none aborts the others):
#   1. Sync the agents repo — ff-only pull of code/config updates.
#   2. Run the learn gate; if it trips, apply cross-project patterns via /learn.
#   3. Dead-man's switch (#359): every outcome arms or clears
#      learn_deadman.py, which emails an alert if the gate stays tripped
#      >7 days without a successful /learn run. The loop must never fail
#      silently again.
#
# Win C (the perpetually-dirty tree caused by telemetry/<host>/*.jsonl shards)
# is RESOLVED: shards are gitignored and local-only (REC 0.1's OTEL hub, the
# intended cross-machine transport, is deferred indefinitely, so telemetry stays
# off the code repo). Nothing here commits or pushes shards — they never enter
# git. See rules/git-workflow.md, "Working tree hygiene in ~/agents".

set -uo pipefail   # deliberately NOT `-e`: every step is independently fault-tolerant

REPO="$HOME/agents"
LOG="$HOME/Library/Logs/claude-learn/poller.log"
mkdir -p "$(dirname "$LOG")"
ts()  { date -Iseconds; }
log() { echo "[$(ts)] $*" >>"$LOG"; }

deadman() {  # trip|clear — best-effort, never blocks the poller
    python3 "$REPO/claude-config/scripts/learn_deadman.py" "$1" >>"$LOG" 2>&1 \
        || log "deadman $1 failed (non-fatal)"
}

# Resolve the claude CLI explicitly: launchd's PATH (even via `bash -lc`) does
# not reliably include user install dirs — the loop was dead for months on
# `claude: command not found` (#359). Never invoke bare `claude` here.
resolve_claude() {
    local candidate
    if candidate="$(command -v claude 2>/dev/null)"; then
        echo "$candidate"; return 0
    fi
    for candidate in \
        "$HOME/.local/bin/claude" \
        "$HOME/.claude/local/claude" \
        /opt/homebrew/bin/claude \
        /usr/local/bin/claude; do
        if [ -x "$candidate" ]; then
            echo "$candidate"; return 0
        fi
    done
    return 1
}

cd "$REPO" || { log "FATAL: $REPO missing — aborting poller run"; exit 0; }

# 1. Sync. ff-only preserves the existing safe semantics and tolerates a dirty
#    own-shard (incoming changes touch other hosts' paths, not ours).
git pull --ff-only --quiet 2>>"$LOG" || log "pull --ff-only failed (non-fatal)"

# 2. Gate, then learn only if the gate trips (matches the former inline behaviour).
if python3 claude-config/scripts/telemetry_gate.py --verbose >>"$LOG" 2>&1; then
    if CLAUDE_BIN="$(resolve_claude)"; then
        if "$CLAUDE_BIN" --print "/learn --apply --cross-project --validate" >>"$LOG" 2>&1; then
            log "/learn run succeeded"
            deadman clear
        else
            log "/learn invocation FAILED (exit $?) — gate remains tripped"
            deadman trip
        fi
    else
        log "FATAL: claude CLI not found (checked PATH, ~/.local/bin, ~/.claude/local, /opt/homebrew/bin, /usr/local/bin)"
        deadman trip
    fi
else
    log "learn gate not tripped — skip /learn"
    deadman clear
fi

log "poller run complete"
