#!/usr/bin/env bash
# run-pathb-archival.sh — execute Path B archival moves.
#
# Runs four `git mv` operations to archive the legacy YAML state and the
# retired dashboard / review_session CLIs. Idempotent (skips moves whose
# destination already exists). All moves use `git mv` so history is
# preserved and rollback is `git mv` in reverse.
#
# Usage:
#   run-pathb-archival.sh --dry-run     # print intended moves; execute nothing
#   run-pathb-archival.sh --for-real    # do it
#
# Must run from inside the agents repo (uses `git rev-parse --show-toplevel`).
#
# Reversible: every move is `git mv`. To undo: run the move in reverse.

set -eu

MODE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  MODE="dry-run" ;;
    --for-real) MODE="for-real" ;;
    -h|--help)
      sed -n '2,17p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$MODE" ]; then
  echo "usage: $(basename "$0") --dry-run | --for-real" >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git not installed" >&2
  exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  echo "ERROR: not inside a git repo" >&2
  exit 2
fi
cd "$REPO_ROOT"

# pairs: <src>:<dst>
MOVES="\
knowledge/projects:_archived/projects-pre-pathb
knowledge/decisions:_archived/decisions-pre-pathb
dashboard:_archived/dashboard
review_session:_archived/review_session"

moved=0
skipped=0

while IFS= read -r pair; do
  [ -z "$pair" ] && continue
  src="${pair%%:*}"
  dst="${pair##*:}"

  if [ ! -e "$src" ]; then
    echo "skip: $src does not exist"
    skipped=$((skipped + 1))
    continue
  fi
  if [ -e "$dst" ]; then
    echo "skip: $dst already exists"
    skipped=$((skipped + 1))
    continue
  fi

  if [ "$MODE" = "dry-run" ]; then
    echo "would: git mv $src $dst"
  else
    mkdir -p "$(dirname "$dst")"
    git mv "$src" "$dst"
    echo "moved: $src → $dst"
  fi
  moved=$((moved + 1))
done <<EOF
$MOVES
EOF

echo
if [ "$MODE" = "dry-run" ]; then
  echo "summary: would-move=$moved skip=$skipped"
  echo
  echo "Re-run with --for-real to execute."
else
  echo "summary: moved=$moved skip=$skipped"
  echo
  echo "Next: review with 'git status' and commit:"
  echo "  git commit -m 'chore: archive legacy modules per Path B cutover (#168)'"
fi
