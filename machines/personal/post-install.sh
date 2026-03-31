#!/bin/bash
# Post-install for Personal machine (WSL/Linux)
# Sets up systemd timer + cron for obsidian-agent automation

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="$(command -v python3)"

echo "=== Personal Machine Post-Install ==="
echo "  Platform: Linux/WSL"
echo ""

# ─── Obsidian Agent: systemd timer (real-time updates) ────────────────────
echo "Setting up systemd timer..."
cd "$REPO_DIR/obsidian-agent"
"$PYTHON_BIN" -m obsidian_agent --install-systemd
echo ""

# ─── Obsidian Agent: cron (scheduled rollups) ─────────────────────────────
echo "Setting up cron entries..."
"$PYTHON_BIN" -m obsidian_agent --install-cron
echo ""

# ─── Email helper dependencies ────────────────────────────────────────────
echo "Checking email helper dependencies..."
if "$PYTHON_BIN" -c "import azure.identity; import httpx" 2>/dev/null; then
    echo "  ✓ azure-identity + httpx already installed"
else
    echo "  Installing azure-identity httpx..."
    "$PYTHON_BIN" -m pip install --user azure-identity httpx 2>/dev/null || \
    "$PYTHON_BIN" -m pip install --user --break-system-packages azure-identity httpx 2>/dev/null || \
    echo "  ⚠ Failed to install email deps — install manually: pip3 install azure-identity httpx"
fi
echo ""

echo "=== Personal machine setup complete ==="
echo ""
echo "  Systemd timer: active (60s polling)"
echo "  Cron: nightly daily rollup, weekly, monthly"
echo "  Email: deps installed (configure credentials in ~/.claude/.env)"
echo ""
