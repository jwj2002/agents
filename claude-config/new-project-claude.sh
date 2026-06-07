#!/bin/bash
# Compatibility wrapper for the unified project agent bootstrap.
#
# Prefer:
#   ~/agents/new-project-agents.sh /path/to/repo

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "new-project-claude.sh is a compatibility wrapper."
echo "Prefer: $ROOT_DIR/new-project-agents.sh"
echo ""

exec "$ROOT_DIR/new-project-agents.sh" "$@"
