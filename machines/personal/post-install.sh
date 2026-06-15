#!/bin/bash
# Post-install for the "personal" machine profile.
#
# The profile selects config.toml + env.template only. The automation scheduler
# is chosen by the ACTUAL detected platform (macOS→launchd, Linux→systemd+cron,
# WSL→cron[/systemd]) via machines/lib/post-install-common.sh — so this profile
# runs cleanly on macOS, Ubuntu/Linux, or WSL.

set -e

PROFILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$PROFILE_DIR/../.." && pwd)"

# shellcheck source=../lib/post-install-common.sh
source "$REPO_DIR/machines/lib/post-install-common.sh"

run_profile_post_install "$REPO_DIR" "personal"
