#!/usr/bin/env bash
# Daily coding-memory maintenance, spawned detached by the SessionStart hook
# (coding_memory_maint.py). Cross-platform (macOS/WSL/Linux). Personal store only
# (residency enforced by the CLI). Safe path: ingest (prunes deleted files on a
# clean scan) + doctor --prune-expired (TTL only) — never --prune-missing unattended.
set -uo pipefail
REPO="$HOME/agents"
LOG="$HOME/.claude/logs/coding-memory-maint.log"
LOCK="$HOME/.claude/.coding-memory-maint.lock"   # mkdir lock: portable single-flight
mkdir -p "$(dirname "$LOG")"
ts() { date "+%Y-%m-%dT%H:%M:%S%z"; }

# single-flight via atomic mkdir; steal a stale lock (>60m) so a hung run can't wedge
# future runs forever. flock/timeout are unavailable on stock macOS, so avoid them.
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -prune -mmin +60 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null || rm -rf "$LOCK" 2>/dev/null
    mkdir "$LOCK" 2>/dev/null || { echo "[$(ts)] lock contended; skip" >>"$LOG"; exit 0; }
  else
    echo "[$(ts)] another maint run holds the lock; skip" >>"$LOG"; exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null || rm -rf "$LOCK" 2>/dev/null' EXIT

echo "[$(ts)] maint start" >>"$LOG"
"$REPO/bin/coding-memory" ingest >>"$LOG" 2>&1; ing=$?
"$REPO/bin/coding-memory" doctor --prune-expired >>"$LOG" 2>&1; doc=$?
echo "[$(ts)] maint done (ingest rc=$ing, doctor rc=$doc)" >>"$LOG"
