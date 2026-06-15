#!/usr/bin/env bash
# Scheduled personal coding-memory ingest (launchd: com.coding-memory-ingest).
# Thin wrapper so logic is editable without redeploying the plist. Runs the
# default (personal-only) ingest — no --source override, so residency holds.
# Fails soft: logs and exits non-zero on error; never retries in a tight loop
# (launchd re-runs on the next StartInterval).
set -uo pipefail
REPO="$HOME/agents"
LOG="$HOME/.claude/logs/coding-memory-ingest.log"
mkdir -p "$(dirname "$LOG")"
ts() { date "+%Y-%m-%dT%H:%M:%S%z"; }
echo "[$(ts)] coding-memory ingest start" >>"$LOG"
if "$REPO/bin/coding-memory" ingest >>"$LOG" 2>&1; then
  echo "[$(ts)] ingest ok" >>"$LOG"
else
  rc=$?
  echo "[$(ts)] ingest FAILED rc=$rc (jns unreachable? see output above)" >>"$LOG"
  exit "$rc"
fi
