#!/bin/bash
# Install agents configurations with machine profile support.
#
# Usage:
#   ./install-all.sh              # auto-detects profile or prompts
#   ./install-all.sh --profile work
#   ./install-all.sh --profile personal
#   ./install-all.sh --skip-profile   # base install only, no profile
#
# Profiles live in machines/<name>/ and contain:
#   config.toml      — obsidian-agent configuration
#   env.template     — required environment variables (no secrets)
#   post-install.sh  — platform-specific automation (launchd/systemd/cron)

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACHINES_DIR="$ROOT_DIR/machines"
PROFILE=""
SKIP_PROFILE=false

# ─── Parse arguments ────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile|-p)
            PROFILE="$2"
            shift 2
            ;;
        --skip-profile)
            SKIP_PROFILE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--profile <name>] [--skip-profile]"
            echo ""
            echo "Profiles: $(ls -1 "$MACHINES_DIR" 2>/dev/null | tr '\n' ' ')"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ─── Profile detection ──────────────────────────────────────────────────────

detect_profile() {
    # Check for a saved profile marker
    local marker="$HOME/.config/agents-profile"
    if [ -f "$marker" ]; then
        cat "$marker"
        return
    fi

    # Auto-detect by hostname patterns
    local hostname
    hostname="$(hostname 2>/dev/null || echo unknown)"

    # Add your hostname patterns here
    case "$hostname" in
        *JJ-DELLPRO14*|*dell*)
            echo "work"
            return
            ;;
        *mac*|*MBP*|*MacBook*|*personal*)
            echo "personal"
            return
            ;;
    esac

    # Auto-detect by platform
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "work"
        return
    fi

    # Can't detect — return empty
    echo ""
}

select_profile() {
    local profiles
    profiles=($(ls -1 "$MACHINES_DIR" 2>/dev/null))

    if [ ${#profiles[@]} -eq 0 ]; then
        echo "  No profiles found in $MACHINES_DIR"
        return
    fi

    echo ""
    echo "  Available profiles:"
    local i=1
    for p in "${profiles[@]}"; do
        echo "    $i) $p"
        i=$((i + 1))
    done
    echo "    s) Skip profile (base install only)"
    echo ""
    read -rp "  Select profile [1-${#profiles[@]}/s]: " choice

    if [[ "$choice" == "s" || "$choice" == "S" ]]; then
        SKIP_PROFILE=true
        return
    fi

    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#profiles[@]}" ]; then
        PROFILE="${profiles[$((choice - 1))]}"
    else
        echo "  Invalid choice. Skipping profile."
        SKIP_PROFILE=true
    fi
}

echo "=== Agents Unified Installer ==="
echo "  Repo: $ROOT_DIR"

# Resolve profile
if [ "$SKIP_PROFILE" = false ] && [ -z "$PROFILE" ]; then
    PROFILE=$(detect_profile)
    if [ -z "$PROFILE" ]; then
        echo ""
        echo "  Could not auto-detect machine profile."
        select_profile
    else
        echo "  Auto-detected profile: $PROFILE"
        read -rp "  Use this profile? [Y/n]: " confirm
        if [[ "$confirm" =~ ^[nN] ]]; then
            select_profile
        fi
    fi
fi

if [ "$SKIP_PROFILE" = false ] && [ -n "$PROFILE" ]; then
    PROFILE_DIR="$MACHINES_DIR/$PROFILE"
    if [ ! -d "$PROFILE_DIR" ]; then
        echo "  ERROR: Profile '$PROFILE' not found at $PROFILE_DIR"
        exit 1
    fi
    echo "  Profile: $PROFILE ($PROFILE_DIR)"

    # Save profile marker for future runs
    mkdir -p "$HOME/.config"
    echo "$PROFILE" > "$HOME/.config/agents-profile"
else
    echo "  Profile: none (base install only)"
fi

echo ""

# ─── Step 1: Claude config ──────────────────────────────────────────────────

if [ -x "$ROOT_DIR/claude-config/install.sh" ]; then
    echo "[1/3] Installing Claude config"
    "$ROOT_DIR/claude-config/install.sh"
else
    echo "[1/3] Skipped Claude config (install.sh missing or not executable)"
fi

echo ""

# ─── Step 2: Codex config ───────────────────────────────────────────────────

if [ -x "$ROOT_DIR/codex-config/install.sh" ]; then
    echo "[2/3] Installing Codex config"
    "$ROOT_DIR/codex-config/install.sh"
else
    echo "[2/3] Skipped Codex config (install.sh missing or not executable)"
fi

echo ""

# ─── Step 3: Machine profile ────────────────────────────────────────────────

if [ "$SKIP_PROFILE" = false ] && [ -n "$PROFILE" ]; then
    echo "[3/3] Applying machine profile: $PROFILE"

    # Apply obsidian-agent config
    CONFIG_DIR="$HOME/.config/obsidian-agent"
    CONFIG_FILE="$CONFIG_DIR/config.toml"
    if [ -f "$PROFILE_DIR/config.toml" ]; then
        mkdir -p "$CONFIG_DIR"
        if [ -f "$CONFIG_FILE" ]; then
            echo "  ✓ Config: $CONFIG_FILE (already exists — not overwriting)"
            echo "    Profile template: $PROFILE_DIR/config.toml"
        else
            cp "$PROFILE_DIR/config.toml" "$CONFIG_FILE"
            echo "  ✓ Config: $CONFIG_FILE (created from profile)"
        fi
    fi

    # Show env template
    if [ -f "$PROFILE_DIR/env.template" ]; then
        ENV_FILE="$HOME/.claude/.env"
        if [ -f "$ENV_FILE" ]; then
            echo "  ✓ Env: $ENV_FILE (already exists)"
        else
            echo "  ⚠ Env: copy $PROFILE_DIR/env.template to $ENV_FILE and fill in values"
        fi
    fi

    # Run post-install
    if [ -x "$PROFILE_DIR/post-install.sh" ]; then
        echo ""
        echo "  Running post-install for $PROFILE..."
        echo ""
        "$PROFILE_DIR/post-install.sh"
    fi
else
    echo "[3/3] Skipped machine profile"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
if [ -n "$PROFILE" ] && [ "$SKIP_PROFILE" = false ]; then
    echo "  Profile '$PROFILE' applied."
    echo "  Saved to ~/.config/agents-profile (auto-detected on next run)."
fi
echo ""
