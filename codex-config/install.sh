#!/bin/bash
# Install Codex configuration: shared rules and user skills symlinks.
#
# Usage: ./install.sh
#
# Safe to run repeatedly (idempotent).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_DIR="$HOME/.codex"
BACKUP_DIR="$CODEX_DIR/config-backup-$(date +%Y%m%d-%H%M%S)"
BACKUP_CREATED=false

LINKS_TOTAL=0
LINKS_CREATED=0

backup_item() {
    local target="$1"
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        BACKUP_CREATED=true
    fi
    mv "$target" "$BACKUP_DIR/"
}

link_item() {
    # link_item <source> <target> <label>
    local source="$1"
    local target="$2"
    local label="$3"
    LINKS_TOTAL=$((LINKS_TOTAL + 1))

    if [ -e "$target" ] && [ ! -L "$target" ]; then
        backup_item "$target"
        echo "  Backed up $label"
    fi

    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        echo "  ✓ $label (already linked)"
    else
        ln -sfn "$source" "$target"
        echo "  ✓ $label → linked"
        LINKS_CREATED=$((LINKS_CREATED + 1))
    fi
}

echo "=== Codex Config Installer ==="
echo "  Source: $SCRIPT_DIR"
echo "  Target: $CODEX_DIR"
echo ""

echo "Phase 1: Symlinks"
mkdir -p "$CODEX_DIR" "$CODEX_DIR/rules" "$CODEX_DIR/skills"

link_item "$SCRIPT_DIR/rules/shared.rules" "$CODEX_DIR/rules/shared.rules" "rules/shared.rules"
link_item "$SCRIPT_DIR/skills" "$CODEX_DIR/skills/user" "skills/user"

echo ""

echo "Phase 2: First-time setup"
if [ ! -f "$CODEX_DIR/config.toml" ]; then
    cp "$SCRIPT_DIR/config.toml.example" "$CODEX_DIR/config.toml"
    chmod 600 "$CODEX_DIR/config.toml"
    echo "  ✓ config.toml created from template"
else
    echo "  ✓ config.toml already exists (left unchanged)"
fi

echo ""

echo "Phase 3: Verify"
ERRORS=0

for target in "$CODEX_DIR/rules/shared.rules" "$CODEX_DIR/skills/user"; do
    if [ -L "$target" ] && [ -e "$target" ]; then
        :
    else
        echo "  ✗ Broken symlink: $target"
        ERRORS=$((ERRORS + 1))
    fi
done

if [ $ERRORS -eq 0 ]; then
    echo "  ✓ All symlinks resolve"
fi

echo ""
echo "=== Installation Summary ==="
echo "  Symlinks:    ✓ $LINKS_TOTAL/$LINKS_TOTAL linked"
echo "  Notes:       ~/.codex/skills/.system remains local and untouched"
echo "               ~/.codex/rules/default.rules remains local (machine approvals)"

if [ "$BACKUP_CREATED" = true ]; then
    echo "  Backups:     $BACKUP_DIR"
fi

echo ""
if [ $ERRORS -gt 0 ]; then
    echo "  ⚠ $ERRORS error(s) detected — check output above."
    exit 1
fi

echo "  Run: codex"
