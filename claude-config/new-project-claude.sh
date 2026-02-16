#!/bin/bash
# Bootstrap project-local Claude config from template.
# Usage:
#   ./new-project-claude.sh                # current directory
#   ./new-project-claude.sh /path/to/repo  # explicit path

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/project-template"
TARGET_DIR="${1:-$PWD}"

if [ ! -d "$TARGET_DIR" ]; then
    echo "Target directory does not exist: $TARGET_DIR"
    exit 1
fi

if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "Template directory not found: $TEMPLATE_DIR"
    exit 1
fi

COPIED=0
SKIPPED=0

# Create directory scaffold first.
while IFS= read -r -d '' dir; do
    rel="${dir#$TEMPLATE_DIR/}"
    [ "$rel" = "$dir" ] && rel=""
    mkdir -p "$TARGET_DIR/$rel"
done < <(find "$TEMPLATE_DIR" -type d -print0)

# Copy files without overwriting existing project files.
while IFS= read -r -d '' file; do
    rel="${file#$TEMPLATE_DIR/}"
    dest="$TARGET_DIR/$rel"
    if [ -e "$dest" ]; then
        echo "  skip: $rel (already exists)"
        SKIPPED=$((SKIPPED + 1))
    else
        cp "$file" "$dest"
        echo "  add:  $rel"
        COPIED=$((COPIED + 1))
    fi
done < <(find "$TEMPLATE_DIR" -type f -print0)

echo ""
echo "Project Claude bootstrap complete for: $TARGET_DIR"
echo "  Added:   $COPIED"
echo "  Skipped: $SKIPPED"
echo "Next: edit $TARGET_DIR/CLAUDE.md and $TARGET_DIR/.claude/rules/project-rules.md"
