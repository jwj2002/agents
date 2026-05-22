#!/usr/bin/env bash
# bootstrap-laptop.sh — one-time per-device setup for Path B.
#
# Idempotent. Safe to re-run after every laptop refresh.
# Performs (per-OS branch):
#   - required-tool check (jq, git, python3)
#   - register this device's canonical host name → ~/.claude/host-name
#   - macOS: warn if FileVault disabled (spec §6.5 #7)
#   - WSL: symlink ~/vaults → /mnt/c/Users/$WIN_USER/vaults
#   - seed community-plugins.json in each subscribed vault
#   - enforce per-vault git remote allowlist from ~/.claude/vault-remotes.yaml
#     (spec §6.5 #4 — opt-in via that config file)
#   - run templates/sync-templates.sh
#
# Usage:
#   bootstrap-laptop.sh
#   bootstrap-laptop.sh --noninteractive       # auto-accept host-name from uname
#   bootstrap-laptop.sh --host-name NAME       # explicit host name
#   bootstrap-laptop.sh --home PATH            # override HOME (testing)
#   bootstrap-laptop.sh --os macos|linux|wsl   # force OS branch (testing)
#
# Environment overrides (testing):
#   BOOTSTRAP_OS    — macos | linux | wsl
#   BOOTSTRAP_HOME  — alternate HOME root
#   WIN_USER        — Windows username for WSL symlink target
#
# Compatible with macOS system bash 3.2.

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NONINTERACTIVE=0
HOST_NAME_ARG=""
OS_OVERRIDE="${BOOTSTRAP_OS:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --noninteractive) NONINTERACTIVE=1 ;;
    --host-name) HOST_NAME_ARG="$2"; shift ;;
    --home) export HOME="$2"; shift ;;
    --os) OS_OVERRIDE="$2"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

# Honor BOOTSTRAP_HOME for tests
if [ -n "${BOOTSTRAP_HOME:-}" ]; then
  export HOME="$BOOTSTRAP_HOME"
fi

# ---------- OS detection ----------

detect_os() {
  if [ -n "$OS_OVERRIDE" ]; then
    echo "$OS_OVERRIDE"
    return
  fi
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)
      if [ -r /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
        echo "wsl"
      else
        echo "linux"
      fi
      ;;
    *) echo "unknown" ;;
  esac
}

# ---------- required tools ----------

require_tools() {
  missing=""
  for tool in jq git python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing="$missing $tool"
    fi
  done
  if [ -n "$missing" ]; then
    echo "ERROR: missing required tools:$missing" >&2
    echo "  Install them via your package manager (brew / apt / etc.) and re-run." >&2
    exit 2
  fi
  echo "  required tools available: jq git python3"
}

# ---------- host name ----------

register_host_name() {
  host_file="$HOME/.claude/host-name"
  mkdir -p "$HOME/.claude"

  if [ -n "$HOST_NAME_ARG" ]; then
    chosen="$HOST_NAME_ARG"
  elif [ -f "$host_file" ] && [ -s "$host_file" ]; then
    chosen="$(tr -d '[:space:]' < "$host_file")"
    echo "  host-name already set: $chosen (re-run with --host-name to change)"
    return 0
  else
    suggested="$(uname -n 2>/dev/null | tr '[:upper:]' '[:lower:]' | cut -d. -f1)"
    [ -z "$suggested" ] && suggested="unknown"
    if [ "$NONINTERACTIVE" -eq 1 ]; then
      chosen="$suggested"
    else
      printf "Host name for this device [%s]: " "$suggested"
      if IFS= read -r host_input; then
        chosen="${host_input:-$suggested}"
      else
        chosen="$suggested"
      fi
    fi
  fi

  echo "$chosen" > "$host_file"
  echo "  registered host-name: $chosen ($host_file)"
}

# ---------- macOS: FileVault ----------

check_filevault() {
  if ! command -v fdesetup >/dev/null 2>&1; then
    echo "  fdesetup not available — skipping FileVault check"
    return 0
  fi
  status="$(fdesetup status 2>/dev/null || true)"
  case "$status" in
    *"FileVault is On"*)
      echo "  FileVault: ON ✓"
      ;;
    *)
      cat <<EOF >&2
  WARNING: FileVault appears to be OFF.
    Required for any laptop hosting client vaults (spec §6.5 #7).
    Enable: System Settings → Privacy & Security → FileVault → Turn On.
EOF
      ;;
  esac
}

# ---------- WSL: vault symlink ----------

setup_wsl_vaults_symlink() {
  target_user="${WIN_USER:-$USER}"
  target="/mnt/c/Users/$target_user/vaults"

  if [ -L "$HOME/vaults" ]; then
    current="$(readlink "$HOME/vaults")"
    echo "  ~/vaults already a symlink → $current"
    return 0
  fi
  if [ -d "$HOME/vaults" ]; then
    echo "  WARNING: ~/vaults exists as a directory; refusing to convert." >&2
    echo "    Move it manually if you want the Windows-side location:" >&2
    echo "      mv ~/vaults ~/vaults.local && ln -s $target ~/vaults" >&2
    return 0
  fi
  if [ ! -d "$target" ]; then
    echo "  Windows-side vaults dir not found at $target — creating it"
    mkdir -p "$target" || {
      echo "  WARNING: could not create $target — skipping symlink" >&2
      return 0
    }
  fi
  ln -s "$target" "$HOME/vaults"
  echo "  symlinked: ~/vaults → $target"
}

# ---------- subscription recovery ----------
#
# On a fresh device the user typically has a vault (e.g. via Obsidian Sync
# or a git clone of the vault repo) but no ~/.claude/dashboard-subscriptions.json.
# After Path B's lib/project_resolver legacy-format removal, the resolver
# can't find any projects without that file — the picker and project CLIs
# break. This step scans existing vaults and rebuilds the subscription
# file when it's missing/empty. Idempotent: never overrides a populated
# subscription file (user's scope is authoritative once they've curated it).

recover_subscriptions() {
  subs="$HOME/.claude/dashboard-subscriptions.json"
  vaults_base="$HOME/vaults"

  if [ -f "$subs" ]; then
    if SUBS_PATH="$subs" python3 - <<'PYEOF'
import json, os, sys
try:
    data = json.load(open(os.environ["SUBS_PATH"]))
    has_content = any(
        isinstance(v, dict) and v.get("subscribed")
        for v in (data or {}).values()
    )
except Exception:
    has_content = False
sys.exit(0 if has_content else 1)
PYEOF
    then
      echo "  skip: $subs already populated"
      return 0
    fi
  fi

  if [ ! -d "$vaults_base" ]; then
    echo "  skip: no $vaults_base — nothing to recover from"
    return 0
  fi

  SUBS_PATH="$subs" VAULTS_BASE="$vaults_base" python3 - <<'PYEOF'
import json, os
from pathlib import Path

vaults_base = Path(os.environ["VAULTS_BASE"])
subs_path = Path(os.environ["SUBS_PATH"])
out = {}
for vault_dir in sorted(vaults_base.iterdir()):
    if not vault_dir.is_dir():
        continue
    if vault_dir.name.startswith("_") or vault_dir.name.startswith("."):
        continue
    projects_dir = vault_dir / "Projects"
    if not projects_dir.is_dir():
        continue
    projects = sorted(p.stem for p in projects_dir.glob("*.md"))
    if projects:
        out[vault_dir.name] = {"subscribed": projects, "ssh_writes": []}

if not out:
    print("  no vaults with project notes — nothing to recover")
else:
    subs_path.parent.mkdir(parents=True, exist_ok=True)
    subs_path.write_text(json.dumps(out, indent=2) + "\n")
    total = sum(len(v["subscribed"]) for v in out.values())
    print(f"  recovered: {len(out)} vault(s), {total} project subscription(s)")
PYEOF
}

# ---------- Obsidian community plugins ----------

PLUGINS_JSON='["obsidian-tasks-plugin","dataview","templater-obsidian","calendar","obsidian-git"]'

seed_obsidian_plugins() {
  subs="$HOME/.claude/dashboard-subscriptions.json"
  vaults_base="$HOME/vaults"

  if [ ! -f "$subs" ]; then
    echo "  skip: no subscriptions file at $subs"
    return 0
  fi

  count=0
  while IFS= read -r vault; do
    [ -z "$vault" ] && continue
    vault_dir="$vaults_base/$vault"
    [ -d "$vault_dir" ] || continue
    plugins_file="$vault_dir/.obsidian/community-plugins.json"
    mkdir -p "$vault_dir/.obsidian"
    if [ -f "$plugins_file" ] && [ "$(cat "$plugins_file")" = "$PLUGINS_JSON" ]; then
      continue
    fi
    echo "$PLUGINS_JSON" > "$plugins_file"
    count=$((count + 1))
  done < <(jq -r 'keys[]' "$subs" 2>/dev/null)

  if [ "$count" -gt 0 ]; then
    echo "  seeded community-plugins.json in $count vault(s)"
    echo "  → in Obsidian: Settings → Community plugins → enable each per vault"
  else
    echo "  all subscribed vaults already have plugin manifests"
  fi
}

# ---------- per-vault git remote allowlist ----------
# Opt-in: only enforced if ~/.claude/vault-remotes.yaml exists.
# Format (one vault per line, vault: url):
#   JNS-Personal-Vault: git@github.com:jwj2002/jns-personal-vault.git
#   Vital-Work-Vault: git@gitlab.internal:vault/work.git

enforce_git_remote_allowlist() {
  cfg="$HOME/.claude/vault-remotes.yaml"
  if [ ! -f "$cfg" ]; then
    echo "  skip: no $cfg (allowlist enforcement is opt-in)"
    return 0
  fi
  vaults_base="$HOME/vaults"
  while IFS= read -r line; do
    case "$line" in
      ""|"#"*) continue ;;
    esac
    vault="${line%%:*}"
    expected_url="$(echo "${line#*:}" | sed 's/^ *//')"
    [ -z "$vault" ] || [ -z "$expected_url" ] && continue
    vault_dir="$vaults_base/$vault"
    if [ ! -d "$vault_dir/.git" ]; then
      echo "  $vault: not a git repo yet — skip"
      continue
    fi
    current="$(git -C "$vault_dir" remote get-url origin 2>/dev/null || echo "")"
    remote_count="$(git -C "$vault_dir" remote 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$remote_count" -gt 1 ]; then
      echo "  WARNING: $vault has $remote_count remotes (allowlist expects exactly one)" >&2
      git -C "$vault_dir" remote -v >&2
      continue
    fi
    if [ -z "$current" ]; then
      git -C "$vault_dir" remote add origin "$expected_url"
      echo "  $vault: added origin → $expected_url"
    elif [ "$current" = "$expected_url" ]; then
      echo "  $vault: origin OK ($expected_url)"
    else
      echo "  WARNING: $vault origin mismatch" >&2
      echo "    expected: $expected_url" >&2
      echo "    actual:   $current" >&2
      echo "    Refusing to auto-rewrite; fix manually." >&2
    fi
  done < "$cfg"
}

# ---------- template sync ----------

sync_templates() {
  sync_script="$SCRIPT_DIR/templates/sync-templates.sh"
  if [ ! -x "$sync_script" ]; then
    echo "  skip: sync-templates.sh not found at $sync_script"
    return 0
  fi
  if [ ! -f "$HOME/.claude/dashboard-subscriptions.json" ]; then
    echo "  skip: no subscriptions file yet"
    return 0
  fi
  "$sync_script" || echo "  WARNING: sync-templates.sh exited non-zero" >&2
}

# ---------- main ----------

main() {
  os="$(detect_os)"
  echo "=== Path B bootstrap-laptop.sh ==="
  echo "OS: $os    HOME: $HOME"
  echo

  echo "▸ required tools"
  require_tools

  echo
  echo "▸ host name"
  register_host_name

  case "$os" in
    macos)
      echo
      echo "▸ FileVault"
      check_filevault
      ;;
    wsl)
      echo
      echo "▸ WSL vault symlink"
      setup_wsl_vaults_symlink
      ;;
    linux)
      : # nothing platform-specific
      ;;
    *)
      echo "  unknown OS — skipping platform-specific setup" >&2
      ;;
  esac

  echo
  echo "▸ subscription file (rebuild from vaults if missing)"
  recover_subscriptions

  echo
  echo "▸ Obsidian community plugins"
  seed_obsidian_plugins

  echo
  echo "▸ per-vault git remote allowlist"
  enforce_git_remote_allowlist

  echo
  echo "▸ template sync"
  sync_templates

  echo
  echo "Bootstrap complete."
}

main
