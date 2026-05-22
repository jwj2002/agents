#!/usr/bin/env bash
# sync-templates.sh — copy ~/agents/templates/obsidian/*.md into each
# subscribed vault's _templates/ directory.
#
# Idempotent: skips files that already match the source byte-for-byte.
# Reads vault names (top-level keys) from ~/.claude/dashboard-subscriptions.json.
#
# Usage:
#   sync-templates.sh                          # all vaults from subscription file
#   sync-templates.sh --dry-run                # show what would change
#   sync-templates.sh --vault NAME             # sync just one vault
#   sync-templates.sh --subscriptions PATH     # override subscription file (testing)
#   sync-templates.sh --vaults-base PATH       # override vaults base dir (testing)
#
# Compatible with macOS system bash 3.2.

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="$SCRIPT_DIR/obsidian"

DRY_RUN=0
ONE_VAULT=""
SUBSCRIPTIONS="${HOME}/.claude/dashboard-subscriptions.json"
VAULTS_BASE="${HOME}/vaults"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --vault) ONE_VAULT="$2"; shift ;;
    --subscriptions) SUBSCRIPTIONS="$2"; shift ;;
    --vaults-base) VAULTS_BASE="$2"; shift ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ ! -d "$TEMPLATES_DIR" ]; then
  echo "ERROR: template source dir not found: $TEMPLATES_DIR" >&2
  exit 2
fi

if [ ! -f "$SUBSCRIPTIONS" ]; then
  echo "ERROR: subscriptions file not found: $SUBSCRIPTIONS" >&2
  echo "Hint: bootstrap-laptop.sh creates this file. Or pass --subscriptions PATH." >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq not installed (needed to read $SUBSCRIPTIONS)" >&2
  exit 2
fi

copied=0
unchanged=0
skipped=0

sync_one_vault() {
  vault="$1"
  vault_dir="$VAULTS_BASE/$vault"
  if [ ! -d "$vault_dir" ]; then
    echo "skip: vault dir not present at $vault_dir"
    skipped=$((skipped + 1))
    return
  fi
  dest_dir="$vault_dir/_templates"
  if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$dest_dir"
  fi
  for src in "$TEMPLATES_DIR"/*.md; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    dest="$dest_dir/$name"
    if [ -f "$dest" ] && cmp -s "$src" "$dest"; then
      unchanged=$((unchanged + 1))
      continue
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "would copy: $name → $vault/_templates/"
    else
      cp "$src" "$dest"
      echo "copied: $name → $vault/_templates/"
    fi
    copied=$((copied + 1))
  done
}

if [ -n "$ONE_VAULT" ]; then
  sync_one_vault "$ONE_VAULT"
else
  while IFS= read -r vault; do
    [ -z "$vault" ] && continue
    sync_one_vault "$vault"
  done < <(jq -r 'keys[]' "$SUBSCRIPTIONS")
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "summary: would-copy=$copied unchanged=$unchanged skipped-vaults=$skipped"
else
  echo "summary: copied=$copied unchanged=$unchanged skipped-vaults=$skipped"
fi
