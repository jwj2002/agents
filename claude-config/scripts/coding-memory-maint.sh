#!/usr/bin/env bash
# Daily coding-memory maintenance, spawned detached by the SessionStart hook
# (coding_memory_maint.py). Cross-platform (macOS/WSL/Linux). Personal store only
# (residency enforced by the CLI). Runs the SAFE path: ingest (which prunes
# deleted files on a clean scan) + doctor --prune-expired (TTL only). Never runs
# the risky --prune-missing unattended.
set -uo pipefail
REPO="$HOME/agents"
LOG="$HOME/.claude/logs/coding-memory-maint.log"
mkdir -p "$(dirname "$LOG")"
ts() { date "+%Y-%m-%dT%H:%M:%S%z"; }
echo "[$(ts)] maint start" >>"$LOG"
"$REPO/bin/coding-memory" ingest >>"$LOG" 2>&1
ing=$?
"$REPO/bin/coding-memory" doctor --prune-expired >>"$LOG" 2>&1
doc=$?
echo "[$(ts)] maint done (ingest rc=$ing, doctor rc=$doc)" >>"$LOG"
