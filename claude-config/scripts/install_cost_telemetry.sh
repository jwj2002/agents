#!/bin/bash
# Activate / deactivate the cost-telemetry collector launchd job (cost-telemetry-v0 §D2).
# NOT run automatically — this is the DEFERRED activation step (joint review + smoke test).
# After `load`, also wire the Stop hook (hooks/cost_collect_request.py) and SessionStart freshness
# (scripts/cost_telemetry_freshness.py) into ~/.claude/settings.json — also deferred.
set -euo pipefail

PLIST_SRC="$(cd "$(dirname "$0")/../launchd" && pwd)/com.cost-telemetry-collect.plist"
DEST="$HOME/Library/LaunchAgents/com.cost-telemetry-collect.plist"
LOG="$HOME/.claude/logs/cost-telemetry.log"

case "${1:-help}" in
  load)
    mkdir -p "$HOME/.claude/logs" "$(dirname "$DEST")"
    cp "$PLIST_SRC" "$DEST"
    launchctl unload "$DEST" 2>/dev/null || true   # idempotent: unload before load
    launchctl load "$DEST"
    echo "✓ loaded com.cost-telemetry-collect (every 6h). Logs: $LOG"
    echo "  Next (also deferred): add cost_collect_request.py to Stop hooks +"
    echo "  cost_telemetry_freshness.py to SessionStart in ~/.claude/settings.json."
    ;;
  unload|--uninstall)
    launchctl unload "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    echo "✓ unloaded + removed com.cost-telemetry-collect."
    ;;
  status)
    launchctl list | grep cost-telemetry || echo "(not loaded)"
    ;;
  *)
    echo "usage: $0 [load|unload|status]"
    echo "  load    — copy plist to LaunchAgents + launchctl load (idempotent)"
    echo "  unload  — launchctl unload + remove plist"
    echo "  status  — show whether the job is loaded"
    ;;
esac
