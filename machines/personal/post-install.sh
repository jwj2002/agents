#!/bin/bash
# Post-install for Personal machine (macOS)
# Sets up launchd agents for obsidian-agent automation

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="$(command -v python3)"

echo "=== Personal Machine Post-Install ==="
echo "  Platform: macOS"
echo ""

# ─── Obsidian Agent: launchd (real-time updates + scheduled rollups) ──────
echo "Setting up launchd agents..."
cd "$REPO_DIR/obsidian-agent"
"$PYTHON_BIN" -m obsidian_agent --install-launchd
echo ""

# ─── Email helper dependencies ────────────────────────────────────────────
echo "Checking email helper dependencies..."
if "$PYTHON_BIN" -c "import azure.identity; import httpx" 2>/dev/null; then
    echo "  ✓ azure-identity + httpx already installed"
else
    echo "  Installing azure-identity httpx..."
    "$PYTHON_BIN" -m pip install azure-identity httpx 2>/dev/null || \
    echo "  ⚠ Failed to install email deps — install manually: pip3 install azure-identity httpx"
fi
echo ""

echo "=== Personal machine setup complete ==="
echo ""
echo "  launchd watcher: active (60s polling)"
echo "  launchd rollups: daily 11 PM (includes weekly/monthly)"
echo "  Email: deps installed (configure credentials in ~/.claude/.env)"
echo ""
echo "  Check status:  launchctl list | grep obsidian-agent"
echo "  View logs:     ~/Library/Logs/obsidian-agent/"
echo ""
