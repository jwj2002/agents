#!/bin/bash
# Install Codex configuration: shared guidance, rules, and user skills symlinks.
#
# Usage: ./install.sh
#
# Safe to run repeatedly (idempotent).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_DIR="$HOME/.codex"
AGENTS_SKILLS_DIR="$HOME/.agents/skills"
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

    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        echo "  ✓ $label (already linked)"
    else
        if [ -e "$target" ] || [ -L "$target" ]; then
            backup_item "$target"
            echo "  Backed up $label"
        fi
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
mkdir -p "$CODEX_DIR" "$CODEX_DIR/rules" "$CODEX_DIR/skills" "$AGENTS_SKILLS_DIR"

link_item "$SCRIPT_DIR/AGENTS.md" "$CODEX_DIR/AGENTS.md" "AGENTS.md"
link_item "$SCRIPT_DIR/rules/shared.rules" "$CODEX_DIR/rules/shared.rules" "rules/shared.rules"
link_item "$SCRIPT_DIR/skills" "$CODEX_DIR/skills/user" "skills/user"

for skill_dir in "$SCRIPT_DIR/skills"/*/; do
    [ -d "$skill_dir" ] || continue
    name="$(basename "$skill_dir")"
    [ -f "$skill_dir/SKILL.md" ] || continue

    link_item "${skill_dir%/}" "$CODEX_DIR/skills/$name" "skills/$name (from codex-config)"
    link_item "${skill_dir%/}" "$AGENTS_SKILLS_DIR/$name" ".agents/skills/$name (from codex-config)"
done

echo ""

# ─── Phase 1.5: Share Claude skills into Codex ──────────────────────────────
# Claude Code and Codex read an identical SKILL.md format, so a portable Claude
# skill needs no conversion — we symlink the SAME canonical file into Codex,
# giving zero drift (edit once, both runtimes see it). Per-skill links (not a
# whole-dir link) are required so Codex's own ~/.codex/skills/.system and
# /user trees stay intact. A deterministic portability lint gates each skill:
# anything referencing a Claude-only harness construct (Task/Agent tools, plan
# mode, MCP tool IDs, restrictive frontmatter) is skipped for Codex, loudly.
# Canonicalize (strip the `..`) so generated symlinks store clean absolute
# paths; empty if claude-config isn't present on this machine.
CLAUDE_CONFIG="$(cd "$SCRIPT_DIR/../claude-config" 2>/dev/null && pwd || true)"
CLAUDE_SKILLS="${CLAUDE_CONFIG:+$CLAUDE_CONFIG/skills}"
PORTABILITY_LINT="${CLAUDE_CONFIG:+$CLAUDE_CONFIG/scripts/check-skill-portability.sh}"
SKILLS_PORTED=0
SKILLS_SKIPPED=0

echo "Phase 1.5: Claude skills shared into Codex"
if [ -d "$CLAUDE_SKILLS" ] && [ -x "$PORTABILITY_LINT" ]; then
    for skill_dir in "$CLAUDE_SKILLS"/*/; do
        [ -d "$skill_dir" ] || continue
        name="$(basename "$skill_dir")"
        skill_md="$skill_dir/SKILL.md"
        [ -f "$skill_md" ] || continue

        # Never shadow Codex's reserved skill namespaces.
        if [ "$name" = "user" ] || [ "$name" = ".system" ]; then
            echo "  ⚠ skipping '$name' — reserved Codex skills namespace"
            SKILLS_SKIPPED=$((SKILLS_SKIPPED + 1))
            continue
        fi

        if "$PORTABILITY_LINT" "$skill_md" >/dev/null 2>&1; then
            link_item "${skill_dir%/}" "$CODEX_DIR/skills/$name" "skills/$name (from claude-config)"
            link_item "${skill_dir%/}" "$AGENTS_SKILLS_DIR/$name" ".agents/skills/$name (from claude-config)"
            SKILLS_PORTED=$((SKILLS_PORTED + 1))
        else
            echo "  ⚠ skipping '$name' for Codex — Claude-only constructs:"
            "$PORTABILITY_LINT" "$skill_md" 2>/dev/null | sed 's/^/      /'
            SKILLS_SKIPPED=$((SKILLS_SKIPPED + 1))
        fi
    done
    echo "  → $SKILLS_PORTED ported, $SKILLS_SKIPPED skipped (Claude-only)"
else
    echo "  ⚠ claude-config skills or portability lint not found — skipping"
    echo "    (expected $CLAUDE_SKILLS and $PORTABILITY_LINT)"
fi

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

for target in "$CODEX_DIR/AGENTS.md" "$CODEX_DIR/rules/shared.rules" "$CODEX_DIR/skills/user"; do
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
echo "  Claude→Codex: $SKILLS_PORTED skill(s) shared, $SKILLS_SKIPPED skipped (Claude-only)"
echo "  Notes:       ~/.codex/skills/.system remains local and untouched"
echo "               ~/.codex/rules/default.rules remains local (machine approvals)"
echo "               ~/.codex/AGENTS.md is shared Codex guidance"
echo "               ~/.agents/skills contains documented Codex user skill links"

if [ "$BACKUP_CREATED" = true ]; then
    echo "  Backups:     $BACKUP_DIR"
fi

echo ""
if [ $ERRORS -gt 0 ]; then
    echo "  ⚠ $ERRORS error(s) detected — check output above."
    exit 1
fi

echo "  Run: codex"
