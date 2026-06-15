#!/bin/bash
# Shared, platform-aware post-install logic for all machine profiles.
#
# A machine *profile* (work/personal) selects config.toml + env.template only.
# The automation *scheduler* is chosen by the ACTUAL detected platform — NOT by
# the profile name — so any profile is safe to run on macOS, Ubuntu/Linux, or
# WSL:
#
#   macOS              → launchd
#   Linux (systemd)    → systemd --user timer + cron
#   Linux (no systemd) → cron only
#   WSL  (systemd on)  → systemd --user timer + cron
#   WSL  (no systemd)  → cron only (warns; enable systemd in /etc/wsl.conf)
#
# Sourced by machines/<profile>/post-install.sh, which then calls:
#   run_profile_post_install "$REPO_DIR" "<profile-name>"
#
# Callers run with `set -e`; every function here degrades gracefully (warn,
# never abort the whole install) when a scheduler or dependency is missing.

# ─── Platform detection ──────────────────────────────────────────────────────

detect_platform() {
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "macos"
    elif grep -qi microsoft /proc/version 2>/dev/null; then
        echo "wsl"
    else
        echo "linux"
    fi
}

# Is a usable systemd --user instance present? (PID-1 systemd + reachable bus)
systemd_user_available() {
    command -v systemctl >/dev/null 2>&1 || return 1
    [ -d /run/systemd/system ] || return 1
    systemctl --user show-environment >/dev/null 2>&1
}

# ─── Obsidian agent automation (platform-aware) ──────────────────────────────

setup_obsidian_automation() {
    local repo_dir="$1"
    local python_bin="$2"
    local agent_dir="$repo_dir/obsidian-agent"

    if [ ! -d "$agent_dir" ]; then
        echo "  ⚠ obsidian-agent/ not found at $agent_dir — skipping automation"
        return 0
    fi
    # python -m obsidian_agent resolves the package via the working directory.
    cd "$agent_dir" || { echo "  ⚠ cannot cd to $agent_dir — skipping"; return 0; }

    local platform
    platform="$(detect_platform)"

    case "$platform" in
        macos)
            echo "  Platform: macOS → launchd"
            "$python_bin" -m obsidian_agent --install-launchd \
                || echo "  ⚠ launchd setup failed (continuing without real-time automation)"
            ;;
        linux)
            if systemd_user_available; then
                echo "  Platform: Linux → systemd --user timer + cron"
                "$python_bin" -m obsidian_agent --install-systemd \
                    || echo "  ⚠ systemd timer setup failed (continuing)"
            else
                echo "  Platform: Linux (no systemd --user) → cron only"
            fi
            "$python_bin" -m obsidian_agent --install-cron \
                || echo "  ⚠ cron setup failed (continuing)"
            ;;
        wsl)
            if systemd_user_available; then
                echo "  Platform: WSL (systemd enabled) → systemd --user timer + cron"
                "$python_bin" -m obsidian_agent --install-systemd \
                    || echo "  ⚠ systemd timer setup failed (continuing)"
            else
                echo "  Platform: WSL (no systemd) → cron only"
                echo "    Tip: add '[boot]\\nsystemd=true' to /etc/wsl.conf for real-time updates."
            fi
            "$python_bin" -m obsidian_agent --install-cron \
                || echo "  ⚠ cron setup failed (continuing — ensure the cron daemon is running)"
            ;;
    esac
}

# ─── Email helper dependencies (PEP 668 safe) ────────────────────────────────

setup_email_deps() {
    local python_bin="$1"

    if "$python_bin" -c "import azure.identity, httpx" 2>/dev/null; then
        echo "  ✓ azure-identity + httpx already installed"
        return 0
    fi

    echo "  Installing azure-identity httpx..."
    # Plain --user first; fall back to --break-system-packages for
    # externally-managed interpreters (Ubuntu 24.04+, PEP 668).
    "$python_bin" -m pip install --user azure-identity httpx 2>/dev/null \
        || "$python_bin" -m pip install --user --break-system-packages azure-identity httpx 2>/dev/null \
        || echo "  ⚠ Failed to install email deps — install manually (pipx, a venv, or: pip install azure-identity httpx)"
}

# ─── Entry point ─────────────────────────────────────────────────────────────

run_profile_post_install() {
    local repo_dir="$1"
    local profile_name="${2:-unknown}"

    local platform
    platform="$(detect_platform)"

    echo "=== Post-Install (profile: $profile_name, platform: $platform) ==="
    echo ""

    local python_bin
    python_bin="$(command -v python3 || command -v python || true)"
    if [ -z "$python_bin" ]; then
        echo "  ⚠ python3 not found — skipping obsidian-agent automation + email deps."
        echo "    Install Python 3 and re-run: ./install-all.sh --profile $profile_name"
        return 0
    fi

    echo "Setting up obsidian-agent automation..."
    setup_obsidian_automation "$repo_dir" "$python_bin"
    echo ""

    echo "Checking email helper dependencies..."
    setup_email_deps "$python_bin"
    echo ""

    echo "=== Post-install complete ($profile_name / $platform) ==="
    case "$platform" in
        macos)
            echo "  Check status:  launchctl list | grep obsidian-agent"
            echo "  View logs:     ~/Library/Logs/obsidian-agent/" ;;
        linux|wsl)
            echo "  Check timer:   systemctl --user status obsidian-agent-watcher.timer 2>/dev/null || echo '(cron only)'"
            echo "  Check cron:    crontab -l | grep obsidian-agent" ;;
    esac
    echo "  Email: configure credentials in ~/.claude/.env"
    echo ""
}
