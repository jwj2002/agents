#!/bin/bash
# Install frontend-design skill globally to ~/.claude/
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing frontend-design skill to ~/.claude/"

mkdir -p ~/.claude/commands

cp "$SCRIPT_DIR/frontend-design.md" ~/.claude/commands/
echo "  ✓ Installed frontend-design.md to ~/.claude/commands/"

echo ""
echo "Installation complete!"
echo ""
echo "Usage: /frontend-design <design brief>"
