#!/bin/bash
# Bootstrap project-local shared agent config from template.
#
# Usage:
#   ./new-project-agents.sh                         # current directory
#   ./new-project-agents.sh /path/to/repo           # explicit path
#   ./new-project-agents.sh --with-codex-config .   # include .codex/config.toml

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/project-template"
TARGET_DIR=""
WITH_CODEX_CONFIG=false

while [ $# -gt 0 ]; do
    case "$1" in
        --with-codex-config)
            WITH_CODEX_CONFIG=true
            shift
            ;;
        --help|-h)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            if [ -n "$TARGET_DIR" ]; then
                echo "Unexpected argument: $1" >&2
                exit 1
            fi
            TARGET_DIR="$1"
            shift
            ;;
    esac
done

TARGET_DIR="${TARGET_DIR:-$PWD}"

if [ ! -d "$TARGET_DIR" ]; then
    echo "Target directory does not exist: $TARGET_DIR" >&2
    exit 1
fi

if [ ! -d "$TEMPLATE_DIR/common" ]; then
    echo "Template directory not found: $TEMPLATE_DIR/common" >&2
    exit 1
fi

COPIED=0
SKIPPED=0

copy_tree() {
    # copy_tree <source-dir> <target-dir>
    local source_dir="$1"
    local target_root="$2"
    local rel dest

    while IFS= read -r -d '' dir; do
        rel="${dir#$source_dir/}"
        [ "$rel" = "$dir" ] && rel=""
        mkdir -p "$target_root/$rel"
    done < <(find "$source_dir" -type d -print0)

    while IFS= read -r -d '' file; do
        rel="${file#$source_dir/}"
        dest="$target_root/$rel"
        if [ -e "$dest" ]; then
            echo "  skip: $rel (already exists)"
            SKIPPED=$((SKIPPED + 1))
        else
            cp "$file" "$dest"
            echo "  add:  $rel"
            COPIED=$((COPIED + 1))
        fi
    done < <(find "$source_dir" -type f -print0)
}

copy_tree "$TEMPLATE_DIR/common" "$TARGET_DIR"

if [ "$WITH_CODEX_CONFIG" = true ]; then
    if [ ! -d "$TEMPLATE_DIR/optional/codex-config" ]; then
        echo "Optional Codex config template not found: $TEMPLATE_DIR/optional/codex-config" >&2
        exit 1
    fi
    copy_tree "$TEMPLATE_DIR/optional/codex-config" "$TARGET_DIR"
fi

echo ""
echo "Project agent bootstrap complete for: $TARGET_DIR"
echo "  Added:   $COPIED"
echo "  Skipped: $SKIPPED"
echo ""
echo "Next: edit $TARGET_DIR/AGENTS.md, $TARGET_DIR/CLAUDE.md, and project-specific files under .claude/."
if [ "$WITH_CODEX_CONFIG" = false ]; then
    echo "Optional: rerun with --with-codex-config if this repo needs trusted project-level Codex config."
fi
