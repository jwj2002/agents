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
    if command -v cmd.exe &>/dev/null; then
        WIN_USER=$(cmd.exe /C "echo %USERNAME%" 2>/dev/null | tr -d '\r' || true)
    else
        WIN_USER=""
    fi
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

# ─── Prerequisite Check ────────────────────────────────────────────────────

PREREQ_WARN=0

if ! command -v python3 &>/dev/null; then
    echo "⚠ python3 not found — hooks, statusline, and MCP server require it"
    PREREQ_WARN=$((PREREQ_WARN + 1))
fi

if ! command -v npx &>/dev/null; then
    echo "⚠ npx not found — npx-based MCP servers (apple-mcp, gmail-send) require it"
    PREREQ_WARN=$((PREREQ_WARN + 1))
fi

if [ $PREREQ_WARN -gt 0 ]; then
    echo ""
    echo "  Install missing prerequisites and re-run this script."
    echo ""
fi

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

link_item "$SCRIPT_DIR/settings.json"       "$CLAUDE_DIR/settings.json"       "settings.json"
link_item "$SCRIPT_DIR/CLAUDE.md"           "$CLAUDE_DIR/CLAUDE.md"           "CLAUDE.md"
link_item "$SCRIPT_DIR/hooks"               "$CLAUDE_DIR/hooks"               "hooks/"
link_item "$SCRIPT_DIR/commands"            "$CLAUDE_DIR/commands"            "commands/"
link_item "$SCRIPT_DIR/agents"              "$CLAUDE_DIR/agents"              "agents/"
link_item "$SCRIPT_DIR/rules"               "$CLAUDE_DIR/rules"              "rules/"
link_item "$SCRIPT_DIR/skills"              "$CLAUDE_DIR/skills"              "skills/"
link_item "$SCRIPT_DIR/templates"           "$CLAUDE_DIR/templates"           "templates/"
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

# ─── Phase 2.5: Plugins ─────────────────────────────────────────────────────

echo "Phase 2.5: Plugins"

CODEX_PLUGIN_STATUS="skipped"

if command -v claude &>/dev/null; then
    # Add OpenAI Codex marketplace (if not already added)
    if claude plugin marketplace list 2>/dev/null | grep -q "openai-codex"; then
        CODEX_PLUGIN_STATUS="marketplace exists"
        echo "  ✓ Codex marketplace (already configured)"
    else
        if claude plugin marketplace add openai/codex-plugin-cc 2>/dev/null; then
            echo "  ✓ Codex marketplace added"
        else
            CODEX_PLUGIN_STATUS="marketplace failed"
            echo "  ✗ Failed to add Codex marketplace"
        fi
    fi

    # Install all required plugins
    INSTALLED_LIST=$(claude plugin list 2>/dev/null)
    PLUGINS_INSTALLED=0
    PLUGINS_TOTAL=0

    for PLUGIN in \
        "codex@openai-codex" \
        "security-guidance@claude-plugins-official" \
        "typescript-lsp@claude-plugins-official" \
        "pyright-lsp@claude-plugins-official" \
        "pr-review-toolkit@claude-plugins-official" \
        "playwright@claude-plugins-official" \
        "frontend-design@claude-plugins-official"; do
        PLUGINS_TOTAL=$((PLUGINS_TOTAL + 1))
        if echo "$INSTALLED_LIST" | grep -q "$PLUGIN"; then
            echo "  ✓ $PLUGIN (already installed)"
            PLUGINS_INSTALLED=$((PLUGINS_INSTALLED + 1))
        else
            if claude plugin install "$PLUGIN" 2>/dev/null; then
                echo "  ✓ $PLUGIN installed"
                PLUGINS_INSTALLED=$((PLUGINS_INSTALLED + 1))
            else
                echo "  ✗ Failed to install $PLUGIN"
            fi
        fi
    done
    CODEX_PLUGIN_STATUS="$PLUGINS_INSTALLED/$PLUGINS_TOTAL installed"
else
    echo "  ⚠ claude CLI not found — skipping plugin install"
fi

echo ""

# ─── Phase 2.6: MCP Servers ────────────────────────────────────────────────
#
# Claude Code reads MCP servers from ~/.claude.json (NOT ~/.claude/settings.json).
# The `claude mcp add --scope user` command registers them in the right place.
# Each server is registered idempotently — existing entries are overwritten.

echo "Phase 2.6: MCP Servers (user-level, ~/.claude.json)"

MCP_SERVERS_REGISTERED=0
MCP_SERVERS_TOTAL=0

if command -v claude &>/dev/null; then
    register_mcp() {
        # register_mcp <name> <command> [args...]
        # `claude mcp add` is NOT idempotent — it exits 1 with "already exists"
        # if the server is registered. Remove first (no-op if absent), then add,
        # so paths stay correct if REPO_DIR moved between runs.
        local name="$1"
        shift
        MCP_SERVERS_TOTAL=$((MCP_SERVERS_TOTAL + 1))

        claude mcp remove --scope user "$name" >/dev/null 2>&1 || true

        local err
        if err=$(claude mcp add --scope user "$name" -- "$@" 2>&1); then
            echo "  ✓ $name registered"
            MCP_SERVERS_REGISTERED=$((MCP_SERVERS_REGISTERED + 1))
        else
            echo "  ✗ Failed to register $name: $err"
        fi
    }

    # knowledge-mcp was retired in Phase 6C (issue #146). The Knowledge MCP
    # server's data — projects/decisions/patterns/learning-rules — now lives
    # as filesystem YAMLs read directly by the action / dashboard / project /
    # review-session CLIs. The TypeScript server is archived under
    # _archived/knowledge-mcp/. See specs/knowledge-surfaces.md.

    # --- vault-metrics (Python, uses dedicated venv) ---
    MCP_VENV_PYTHON="$REPO_DIR/mcp-server/.venv/bin/python"
    MCP_SERVER_PY="$REPO_DIR/mcp-server/server.py"
    if [ -x "$MCP_VENV_PYTHON" ] && [ -f "$MCP_SERVER_PY" ]; then
        register_mcp vault-metrics "$MCP_VENV_PYTHON" "$MCP_SERVER_PY"
    elif [ -f "$MCP_SERVER_PY" ]; then
        echo "  ✗ vault-metrics: venv not found (created in Phase 2)"
        MCP_SERVERS_TOTAL=$((MCP_SERVERS_TOTAL + 1))
    fi

    # --- context7 (npm package, no local install needed) ---
    register_mcp context7 npx -y @upstash/context7-mcp@latest

    # --- apple-mcp (macOS only — Apple Contacts, Notes, Calendar, etc.) ---
    if [ "$PLATFORM" = "macos" ]; then
        register_mcp apple-mcp npx -y apple-mcp@latest
    else
        echo "  - apple-mcp: skipped (macOS only, current platform: $PLATFORM_LABEL)"
    fi

    # --- npm cache warm-up for npx-based MCP servers ---
    #
    # Cold `npx -y <pkg>@latest` resolves the dist-tag, downloads the tarball,
    # then runs lifecycle scripts. On a cold npm cache this can take 5–30s and
    # exceed Claude Code's MCP handshake timeout, so the first `claude mcp list`
    # after install (or after `npm cache clean`) shows context7 / apple-mcp as
    # "Failed to connect" even though they're correctly registered. Once the
    # cache is warm the same servers start in ~1s. See issue #77.
    #
    # We pre-warm by running each server once with stdin closed; servers exit
    # immediately on EOF without doing any real work. This is best-effort:
    # network failures here do not break install (the registration already
    # succeeded; the user can warm the cache later by re-running `claude mcp list`).
    # Note: playwright is registered via the Claude plugin system (Phase 2.5),
    # not Phase 2.6, so warming it isn't this script's job — the plugin owns
    # its own lifecycle. This warm-up only covers the Phase 2.6 npx servers.
    if command -v npx &>/dev/null; then
        echo "  Warming npm cache for npx-based MCP servers (one-time, ~10s)..."
        # Background npx directly (no subshell) so $! captures the npx PID,
        # which lets the timeout-kill below actually target the download.
        npx -y @upstash/context7-mcp@latest </dev/null >/dev/null 2>&1 &
        WARM_PID1=$!
        WARM_PIDS="$WARM_PID1"
        if [ "$PLATFORM" = "macos" ]; then
            npx -y apple-mcp@latest </dev/null >/dev/null 2>&1 &
            WARM_PID2=$!
            WARM_PIDS="$WARM_PIDS $WARM_PID2"
        fi
        # Bound the wait — if a download is genuinely stuck, don't block install.
        WAIT_DEADLINE=$(( $(date +%s) + 30 ))
        WARM_TIMED_OUT=0
        for pid in $WARM_PIDS; do
            while kill -0 "$pid" 2>/dev/null; do
                if [ "$(date +%s)" -ge "$WAIT_DEADLINE" ]; then
                    kill "$pid" 2>/dev/null || true
                    WARM_TIMED_OUT=1
                    break
                fi
                sleep 1
            done
            wait "$pid" 2>/dev/null || true
        done
        if [ "$WARM_TIMED_OUT" -eq 1 ]; then
            echo "  ~ npm cache warm-up timed out (best-effort; first session may still see Failed to connect)"
        else
            echo "  ✓ npm cache warmed"
        fi
    fi
else
    echo "  ⚠ claude CLI not found — skipping MCP server registration"
    echo "    Install Claude Code, then re-run this script."
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

# ─── Phase 3.5: Git Hooks ────────────────────────────────────────────────────

echo "Phase 3.5: Git hooks"

HOOKS_DIR="$REPO_DIR/.git/hooks"
POST_MERGE="$HOOKS_DIR/post-merge"

if [ -d "$HOOKS_DIR" ]; then
    cat > "$POST_MERGE" << 'HOOK'
#!/bin/bash
# Post-merge hook: runs after every git pull
# Re-runs install.sh if config files changed (idempotent, ~5-10s)

REPO_DIR="$(git rev-parse --show-toplevel)"

# --- Config re-install ---
CONFIG_CHANGED=$(git diff-tree -r --name-only ORIG_HEAD HEAD -- claude-config/ codex-config/ install-all.sh 2>/dev/null)

if [ -n "$CONFIG_CHANGED" ]; then
    echo "[post-merge] Config files changed — re-running installer..."
    "$REPO_DIR/claude-config/install.sh" 2>&1 | sed 's/^/[post-merge] /'
else
    echo "[post-merge] No config changes — skipping install"
fi
HOOK
    chmod +x "$POST_MERGE"
    echo "  ✓ post-merge hook (auto-rerun installer on config changes)"
else
    echo "  ⚠ Not a git repo — skipping post-merge hook"
fi

echo ""

# ─── Phase 4: Verify + Summary ──────────────────────────────────────────────

echo "Phase 4: Verify"

ERRORS=0

# Verify symlinks resolve
for link in settings.json hooks commands agents rules skills templates statusline.py; do
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

# ─── Phase 4.5: Hook script path validation ─────────────────────────────────
# Walks settings.json and verifies every interpreted hook command points at
# an existing script. Catches the PR #75→#76 class of bug (hook references
# a script that didn't ship). Standalone validator; install.sh just delegates.

HOOK_VALIDATOR="$SCRIPT_DIR/scripts/validate-hooks.py"
if [ -f "$HOOK_VALIDATOR" ]; then
    if SETTINGS_PATH="$SCRIPT_DIR/settings.json" python3 "$HOOK_VALIDATOR"; then
        : # OK
    else
        echo "  ✗ Hook validation failed — fix the missing script paths above"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ⚠ Hook validator not found at $HOOK_VALIDATOR — skipping"
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

# Verify python3 command (hooks and statusline require it)
if command -v python3 &>/dev/null; then
    echo "  ✓ python3 available"
elif command -v python &>/dev/null; then
    echo "  ⚠ python3 not found (hooks use python3). Suggestion:"
    echo "    alias python3=python   # add to your shell profile"
    echo "    Or: ln -s \$(which python) /usr/local/bin/python3"
fi

echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────

echo "=== Installation Summary ==="
echo "  Platform:     $PLATFORM_LABEL"
echo "  Symlinks:     ✓ $LINKS_TOTAL/$LINKS_TOTAL linked"
echo "  MCP Server:   $MCP_STATUS"
echo "  MCP Servers:  $MCP_SERVERS_REGISTERED/$MCP_SERVERS_TOTAL registered in ~/.claude.json"
echo "  PyYAML:       $PYYAML_STATUS"
echo "  Codex Plugin: $CODEX_PLUGIN_STATUS"

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
echo "  Note: settings.json is symlinked from the repo."
echo "  Note: Gmail and Google Calendar MCPs need manual auth — run 'claude' and use the /mcp command."
echo ""

if [ $ERRORS -gt 0 ]; then
    echo "  ⚠ $ERRORS error(s) detected — check output above."
    exit 1
fi

echo "  Run: claude   (all commands available)"
echo ""
