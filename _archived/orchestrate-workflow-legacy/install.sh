#!/bin/bash
# Install orchestrate workflow globally to ~/.claude/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing orchestrate workflow to ~/.claude/"

# Create directories
mkdir -p ~/.claude/commands
mkdir -p ~/.claude/agents

# Copy command
cp "$SCRIPT_DIR/orchestrate.md" ~/.claude/commands/
echo "  ✓ Installed orchestrate.md to ~/.claude/commands/"

# Copy agents (don't overwrite existing project-specific ones)
for agent in "$SCRIPT_DIR/agents/"*.md; do
    filename=$(basename "$agent")
    if [ ! -f ~/.claude/agents/"$filename" ]; then
        cp "$agent" ~/.claude/agents/
        echo "  ✓ Installed $filename to ~/.claude/agents/"
    else
        echo "  - Skipped $filename (already exists)"
    fi
done

echo ""
echo "Installation complete!"
echo ""
echo "Usage: /orchestrate <issue-number>"
echo ""
echo "Agent files installed:"
ls -1 ~/.claude/agents/*.md 2>/dev/null | xargs -n1 basename || echo "  (none)"
