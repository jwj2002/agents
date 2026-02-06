#!/bin/bash
# Install Claude Code configuration: symlinks, dependencies, first-time setup.
#
# Usage: ./install.sh
#
# Safe to run repeatedly (idempotent). Handles both fresh installs and updates.
#   - Fresh:  git clone && ./install.sh
#   - Update: git pull && ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"  # ~/agents
CLAUDE_DIR="$HOME/.claude"
BACKUP_DIR="$CLAUDE_DIR/config-backup-$(date +%Y%m%d-%H%M%S)"
BACKUP_CREATED=false

# Counters
LINKS_CREATED=0
LINKS_TOTAL=0

# ─── Platform Detection ─────────────────────────────────────────────────────

if [[ "$(uname)" == "Darwin" ]]; then
    PLATFORM="macos"
    PLATFORM_LABEL="macOS"
elif grep -qi microsoft /proc/version 2>/dev/null; then
    PLATFORM="wsl"
    WIN_USER=$(cmd.exe /C "echo %USERNAME%" 2>/dev/null | tr -d '\r' || true)
    PLATFORM_LABEL="WSL (Windows: ${WIN_USER:-unknown})"
else
    PLATFORM="linux"
    PLATFORM_LABEL="Linux"
fi

echo "=== Claude Config Installer ==="
echo "  Platform: $PLATFORM_LABEL"
echo "  Source:   $SCRIPT_DIR"
echo "  Target:   $CLAUDE_DIR"
echo ""

# ─── Helpers ─────────────────────────────────────────────────────────────────

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
    # Backs up existing non-symlink targets, then creates symlink.
    local source="$1"
    local target="$2"
    local label="$3"
    LINKS_TOTAL=$((LINKS_TOTAL + 1))

    # If target exists and is NOT a symlink, back it up
    if [ -e "$target" ] && [ ! -L "$target" ]; then
        backup_item "$target"
        echo "  Backed up $label"
    fi

    # Create/update symlink
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        echo "  ✓ $label (already linked)"
    else
        ln -sf "$source" "$target"
        echo "  ✓ $label → linked"
        LINKS_CREATED=$((LINKS_CREATED + 1))
    fi
}

# ─── Phase 1: Symlinks ──────────────────────────────────────────────────────

echo "Phase 1: Symlinks"
mkdir -p "$CLAUDE_DIR"

link_item "$SCRIPT_DIR/settings.local.json" "$CLAUDE_DIR/settings.local.json" "settings.local.json"
link_item "$SCRIPT_DIR/hooks"               "$CLAUDE_DIR/hooks"               "hooks/"
link_item "$SCRIPT_DIR/commands"            "$CLAUDE_DIR/commands"            "commands/"
link_item "$SCRIPT_DIR/agents"              "$CLAUDE_DIR/agents"              "agents/"
link_item "$SCRIPT_DIR/rules"               "$CLAUDE_DIR/rules"              "rules/"
link_item "$SCRIPT_DIR/skills"              "$CLAUDE_DIR/skills"              "skills/"
link_item "$SCRIPT_DIR/statusline.py"       "$CLAUDE_DIR/statusline.py"       "statusline.py"

echo ""

# ─── Phase 2: Dependencies ──────────────────────────────────────────────────

echo "Phase 2: Dependencies"

MCP_STATUS="skipped"
PYYAML_STATUS="skipped"

# Determine pip invocation that works on this system.
# Priority: active venv > uv pip > pipx > pip --user > pip --break-system-packages
find_pip() {
    # Inside a virtualenv — pip works directly
    if [ -n "$VIRTUAL_ENV" ]; then
        echo "pip"
        return
    fi
    # uv is fast and respects PEP 668
    if command -v uv &>/dev/null; then
        echo "uv pip"
        return
    fi
    # System pip with --user (works on most externally-managed envs)
    if command -v pip3 &>/dev/null; then
        echo "pip3"
        return
    fi
    if command -v pip &>/dev/null; then
        echo "pip"
        return
    fi
    echo ""
}

PIP_CMD=$(find_pip)

# Extra flags needed for externally-managed Python (PEP 668, Ubuntu 24.04+)
PIP_FLAGS=""
if [ -n "$PIP_CMD" ] && [ -z "$VIRTUAL_ENV" ] && [ "$PIP_CMD" != "uv pip" ]; then
    # Test if pip is blocked by PEP 668
    if ! $PIP_CMD install --quiet --dry-run pip 2>/dev/null; then
        PIP_FLAGS="--user --break-system-packages"
    fi
fi

pip_install() {
    # pip_install <args...>
    $PIP_CMD install $PIP_FLAGS "$@"
}

if [ -n "$PIP_CMD" ]; then
    # MCP server (editable install — --user incompatible with -e, use venv)
    MCP_DIR="$REPO_DIR/mcp-server"
    MCP_VENV="$REPO_DIR/mcp-server/.venv"
    if [ -f "$MCP_DIR/pyproject.toml" ]; then
        # Editable installs need a proper venv (can't use --user with -e)
        if [ -n "$VIRTUAL_ENV" ]; then
            # Already in a venv — install directly
            if pip install -e "$MCP_DIR" --quiet 2>/dev/null; then
                MCP_STATUS="installed"
                echo "  ✓ MCP server (pip install -e, in active venv)"
            else
                MCP_STATUS="failed"
                echo "  ✗ MCP server install failed"
            fi
        else
            # Create/reuse a dedicated venv for the MCP server
            if [ ! -d "$MCP_VENV" ]; then
                python3 -m venv "$MCP_VENV" 2>/dev/null || true
            fi
            if [ -f "$MCP_VENV/bin/pip" ]; then
                if "$MCP_VENV/bin/pip" install -e "$MCP_DIR" --quiet 2>/dev/null; then
                    MCP_STATUS="installed (venv)"
                    echo "  ✓ MCP server (dedicated venv: $MCP_VENV)"
                else
                    MCP_STATUS="failed"
                    echo "  ✗ MCP server install failed"
                fi
            else
                MCP_STATUS="failed"
                echo "  ✗ Could not create venv for MCP server (install python3-venv)"
            fi
        fi
    else
        MCP_STATUS="not found"
        echo "  - MCP server: $MCP_DIR/pyproject.toml not found"
    fi

    # PyYAML (for hooks) — check if already importable first
    if python3 -c "import yaml" 2>/dev/null; then
        PYYAML_STATUS="installed"
        echo "  ✓ PyYAML (already available)"
    elif pip_install PyYAML --quiet 2>/dev/null; then
        PYYAML_STATUS="installed"
        echo "  ✓ PyYAML"
    else
        PYYAML_STATUS="failed"
        echo "  ✗ PyYAML install failed (try: apt install python3-yaml)"
    fi
else
    echo "  ⚠ pip not found — skipping dependency install"
    echo "    Install Python 3 and pip, then re-run this script."
fi

echo ""

# ─── Phase 3: First-time Setup ──────────────────────────────────────────────

echo "Phase 3: First-time setup"

CONFIG_DIR="$HOME/.config/obsidian-agent"
CONFIG_FILE="$CONFIG_DIR/config.toml"
VAULT_STATUS=""
CONFIG_STATUS=""

# Determine vault path by platform
case "$PLATFORM" in
    macos)
        VAULT_PATH="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault"
        ;;
    wsl)
        if [ -n "$WIN_USER" ]; then
            WIN_VAULT="/mnt/c/Users/$WIN_USER/obsidian/MyVault"
            VAULT_PATH="$HOME/obsidian/MyVault"
        else
            VAULT_PATH="$HOME/obsidian/MyVault"
            WIN_VAULT=""
        fi
        ;;
    *)
        VAULT_PATH="$HOME/obsidian/MyVault"
        ;;
esac

# Create vault directory if needed
if [ "$PLATFORM" = "wsl" ] && [ -n "$WIN_VAULT" ]; then
    # WSL: create Windows-side directory + symlink
    if [ -d "$VAULT_PATH" ] || [ -L "$VAULT_PATH" ]; then
        VAULT_STATUS="exists"
        echo "  ✓ Vault: $VAULT_PATH (already exists)"
    else
        mkdir -p "$WIN_VAULT"
        mkdir -p "$(dirname "$VAULT_PATH")"
        ln -s "$WIN_VAULT" "$VAULT_PATH"
        VAULT_STATUS="created"
        echo "  ✓ Vault: $VAULT_PATH → $WIN_VAULT (created)"
    fi
else
    if [ -d "$VAULT_PATH" ]; then
        VAULT_STATUS="exists"
        echo "  ✓ Vault: $VAULT_PATH (already exists)"
    else
        mkdir -p "$VAULT_PATH"
        VAULT_STATUS="created"
        echo "  ✓ Vault: $VAULT_PATH (created)"
    fi
fi

# Create config.toml if needed
if [ -f "$CONFIG_FILE" ]; then
    CONFIG_STATUS="exists"
    echo "  ✓ Config: $CONFIG_FILE (already configured)"
else
    mkdir -p "$CONFIG_DIR"

    # Resolve absolute vault path for config
    ABS_VAULT="$VAULT_PATH"

    cat > "$CONFIG_FILE" <<TOML
# Obsidian Second Brain Agent — configuration
# Generated by install.sh on $(date +%Y-%m-%d)

[vault]
path = "$ABS_VAULT"
projects_folder = "Projects"

[claude]
projects_path = "~/.claude/projects"

[extraction]
model = "haiku"
max_conversation_chars = 50000
TOML
    CONFIG_STATUS="created"
    echo "  ✓ Config: $CONFIG_FILE (created)"
fi

echo ""

# ─── Phase 4: Verify + Summary ──────────────────────────────────────────────

echo "Phase 4: Verify"

ERRORS=0

# Verify symlinks resolve
for link in settings.local.json hooks commands agents rules skills statusline.py; do
    target="$CLAUDE_DIR/$link"
    if [ -L "$target" ] && [ -e "$target" ]; then
        : # OK
    else
        echo "  ✗ Broken symlink: $target"
        ERRORS=$((ERRORS + 1))
    fi
done

if [ $ERRORS -eq 0 ]; then
    echo "  ✓ All symlinks resolve"
fi

# Verify MCP server (runs as script, not importable as package)
MCP_PYTHON="$REPO_DIR/mcp-server/.venv/bin/python"
if [ -f "$MCP_PYTHON" ] && \
   (cd "$REPO_DIR/mcp-server" && "$MCP_PYTHON" server.py --help &>/dev/null); then
    echo "  ✓ MCP server runs (dedicated venv)"
elif [[ "$MCP_STATUS" == installed* ]]; then
    echo "  ~ MCP server installed (verify manually: cd ~/agents/mcp-server && python server.py --help)"
fi

# Verify PyYAML
if python3 -c "import yaml" 2>/dev/null; then
    echo "  ✓ PyYAML importable"
fi

echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────

echo "=== Installation Summary ==="
echo "  Platform:    $PLATFORM_LABEL"
echo "  Symlinks:    ✓ $LINKS_TOTAL/$LINKS_TOTAL linked"
echo "  MCP Server:  $MCP_STATUS"
echo "  PyYAML:      $PYYAML_STATUS"

# Vault summary
if [ "$PLATFORM" = "wsl" ] && [ -n "$WIN_VAULT" ]; then
    echo "  Vault:       $VAULT_PATH → $WIN_VAULT ($VAULT_STATUS)"
else
    echo "  Vault:       $VAULT_PATH ($VAULT_STATUS)"
fi

echo "  Config:      $CONFIG_FILE ($CONFIG_STATUS)"

if [ "$BACKUP_CREATED" = true ]; then
    echo ""
    echo "  Backups:     $BACKUP_DIR"
fi

echo ""
echo "  Note: settings.json (plugins, credentials) stays local and is not overwritten."
echo ""

if [ $ERRORS -gt 0 ]; then
    echo "  ⚠ $ERRORS error(s) detected — check output above."
    exit 1
fi

echo "  Run: claude   (all commands available)"
echo ""
