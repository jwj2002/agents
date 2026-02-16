#!/bin/bash
# Install both Claude and Codex shared configurations.
# Usage: ./install-all.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Agents Unified Installer ==="
echo "  Repo: $ROOT_DIR"
echo ""

if [ -x "$ROOT_DIR/claude-config/install.sh" ]; then
    echo "[1/2] Installing Claude config"
    "$ROOT_DIR/claude-config/install.sh"
else
    echo "[1/2] Skipped Claude config (install.sh missing or not executable)"
fi

echo ""

if [ -x "$ROOT_DIR/codex-config/install.sh" ]; then
    echo "[2/2] Installing Codex config"
    "$ROOT_DIR/codex-config/install.sh"
else
    echo "[2/2] Skipped Codex config (install.sh missing or not executable)"
fi

echo ""
echo "Done."
