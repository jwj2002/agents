#!/bin/bash
# Install Claude Code configuration by symlinking from this repo to ~/.claude/
#
# Usage: ./install.sh
#
# This script:
# 1. Backs up existing config files
# 2. Creates symlinks from ~/.claude/ → this repo
# 3. Preserves non-tracked directories (projects/, cache/, etc.)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
BACKUP_DIR="$CLAUDE_DIR/config-backup-$(date +%Y%m%d-%H%M%S)"

echo "Installing Claude configuration from: $SCRIPT_DIR"
echo "Target: $CLAUDE_DIR"
echo ""

# Create .claude directory if it doesn't exist
mkdir -p "$CLAUDE_DIR"

# Backup and symlink settings.local.json
if [ -f "$CLAUDE_DIR/settings.local.json" ] && [ ! -L "$CLAUDE_DIR/settings.local.json" ]; then
    mkdir -p "$BACKUP_DIR"
    mv "$CLAUDE_DIR/settings.local.json" "$BACKUP_DIR/"
    echo "  Backed up settings.local.json"
fi
ln -sf "$SCRIPT_DIR/settings.local.json" "$CLAUDE_DIR/settings.local.json"
echo "  ✓ Linked settings.local.json"

# Backup and symlink hooks directory
if [ -d "$CLAUDE_DIR/hooks" ] && [ ! -L "$CLAUDE_DIR/hooks" ]; then
    mkdir -p "$BACKUP_DIR"
    mv "$CLAUDE_DIR/hooks" "$BACKUP_DIR/"
    echo "  Backed up hooks/"
fi
ln -sf "$SCRIPT_DIR/hooks" "$CLAUDE_DIR/hooks"
echo "  ✓ Linked hooks/"

# Backup and symlink commands directory
if [ -d "$CLAUDE_DIR/commands" ] && [ ! -L "$CLAUDE_DIR/commands" ]; then
    mkdir -p "$BACKUP_DIR"
    mv "$CLAUDE_DIR/commands" "$BACKUP_DIR/"
    echo "  Backed up commands/"
fi
ln -sf "$SCRIPT_DIR/commands" "$CLAUDE_DIR/commands"
echo "  ✓ Linked commands/"

# Backup and symlink agents directory
if [ -d "$CLAUDE_DIR/agents" ] && [ ! -L "$CLAUDE_DIR/agents" ]; then
    mkdir -p "$BACKUP_DIR"
    mv "$CLAUDE_DIR/agents" "$BACKUP_DIR/"
    echo "  Backed up agents/"
fi
ln -sf "$SCRIPT_DIR/agents" "$CLAUDE_DIR/agents"
echo "  ✓ Linked agents/"

echo ""
if [ -d "$BACKUP_DIR" ]; then
    echo "Backups saved to: $BACKUP_DIR"
fi
echo ""
echo "Installation complete!"
echo ""
echo "Installed:"
echo "  - settings.local.json (hooks config)"
echo "  - hooks/ (PreCompact, SessionStart scripts)"
echo "  - commands/ (slash commands)"
echo "  - agents/ (agent instructions)"
