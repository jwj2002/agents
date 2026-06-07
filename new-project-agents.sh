#!/bin/bash
# Bootstrap project-local shared agent config from template.
#
# Usage:
#   ./new-project-agents.sh                         # current directory
#   ./new-project-agents.sh /path/to/repo           # explicit path
#   ./new-project-agents.sh --with-codex-config .   # include .codex/config.toml
#   ./new-project-agents.sh --sync-labels .         # create/update universal labels
#   ./new-project-agents.sh --sync-labels --with-agent-workflow-labels .
#   ./new-project-agents.sh --labels-only .         # only sync labels
#   ./new-project-agents.sh --dry-run --sync-labels .

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/project-template"
TARGET_DIR=""
WITH_CODEX_CONFIG=false
DRY_RUN=false
SYNC_LABELS=false
WITH_AGENT_WORKFLOW_LABELS=false
LABELS_ONLY=false

UNIVERSAL_LABELS=(
    "P0|Urgent production breakage or blocked mainline|B60205"
    "P1|Important work that should be scheduled soon|D93F0B"
    "P2|Normal priority|FBCA04"
    "blocked|Blocked by another issue, decision, or external input|BFD4F2"
    "bug|Something is not working|D73A4A"
    "enhancement|New or improved capability|A2EEEF"
    "documentation|Documentation-only or documentation-primary work|0075CA"
    "tests|Test coverage, test infrastructure, or validation gaps|BFDADC"
)

AGENT_WORKFLOW_LABELS=(
    "from-spec|Issue derived from an accepted specification|0E8A16"
    "build-slice|Independently mergeable part of a larger spec or feature|0E8A16"
)

while [ $# -gt 0 ]; do
    case "$1" in
        --with-codex-config)
            WITH_CODEX_CONFIG=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --sync-labels)
            SYNC_LABELS=true
            shift
            ;;
        --labels-only)
            SYNC_LABELS=true
            LABELS_ONLY=true
            shift
            ;;
        --with-agent-workflow-labels)
            WITH_AGENT_WORKFLOW_LABELS=true
            shift
            ;;
        --help|-h)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            if [ -n "$TARGET_DIR" ]; then
                echo "Unexpected argument: $1" >&2
                exit 1
            fi
            TARGET_DIR="$1"
            shift
            ;;
    esac
done

TARGET_DIR="${TARGET_DIR:-$PWD}"

if [ ! -d "$TARGET_DIR" ]; then
    echo "Target directory does not exist: $TARGET_DIR" >&2
    exit 1
fi

if [ ! -d "$TEMPLATE_DIR/common" ]; then
    echo "Template directory not found: $TEMPLATE_DIR/common" >&2
    exit 1
fi

COPIED=0
SKIPPED=0
LABEL_CREATED=0
LABEL_UPDATED=0
LABEL_SKIPPED=0

copy_tree() {
    # copy_tree <source-dir> <target-dir>
    local source_dir="$1"
    local target_root="$2"
    local rel dest

    while IFS= read -r -d '' dir; do
        rel="${dir#$source_dir/}"
        [ "$rel" = "$dir" ] && rel=""
        if [ "$DRY_RUN" = true ]; then
            echo "  mkdir: ${rel:-.}"
        else
            mkdir -p "$target_root/$rel"
        fi
    done < <(find "$source_dir" -type d -print0)

    while IFS= read -r -d '' file; do
        rel="${file#$source_dir/}"
        dest="$target_root/$rel"
        if [ -e "$dest" ]; then
            echo "  skip: $rel (already exists)"
            SKIPPED=$((SKIPPED + 1))
        else
            if [ "$DRY_RUN" = true ]; then
                echo "  add:  $rel (dry-run)"
            else
                cp "$file" "$dest"
                echo "  add:  $rel"
            fi
            COPIED=$((COPIED + 1))
        fi
    done < <(find "$source_dir" -type f -print0)
}

resolve_github_repo() {
    local target_root="$1"

    if ! command -v gh >/dev/null 2>&1; then
        echo "GitHub CLI not found; cannot sync labels" >&2
        return 1
    fi

    if ! git -C "$target_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Target is not a git repository; cannot sync labels: $target_root" >&2
        return 1
    fi

    (cd "$target_root" && gh repo view --json nameWithOwner --jq .nameWithOwner) 2>/dev/null || {
        echo "Could not resolve GitHub repository for: $target_root" >&2
        return 1
    }
}

label_exists() {
    local repo="$1"
    local name="$2"

    gh label list --repo "$repo" --limit 200 --json name --jq '.[].name' |
        grep -Fxq "$name"
}

sync_label() {
    local repo="$1"
    local spec="$2"
    local name description color

    IFS='|' read -r name description color <<< "$spec"

    if [ "$DRY_RUN" = true ]; then
        if label_exists "$repo" "$name"; then
            echo "  label update: $name (dry-run)"
            LABEL_UPDATED=$((LABEL_UPDATED + 1))
        else
            echo "  label create: $name (dry-run)"
            LABEL_CREATED=$((LABEL_CREATED + 1))
        fi
        return
    fi

    if label_exists "$repo" "$name"; then
        gh label edit "$name" --repo "$repo" --description "$description" --color "$color" >/dev/null
        echo "  label update: $name"
        LABEL_UPDATED=$((LABEL_UPDATED + 1))
    else
        gh label create "$name" --repo "$repo" --description "$description" --color "$color" >/dev/null
        echo "  label create: $name"
        LABEL_CREATED=$((LABEL_CREATED + 1))
    fi
}

sync_labels() {
    local target_root="$1"
    local repo spec

    repo="$(resolve_github_repo "$target_root")"

    echo ""
    echo "Syncing standard labels for: $repo"
    if [ "$DRY_RUN" = true ]; then
        echo "  mode: dry-run"
    fi

    for spec in "${UNIVERSAL_LABELS[@]}"; do
        sync_label "$repo" "$spec"
    done

    if [ "$WITH_AGENT_WORKFLOW_LABELS" = true ]; then
        for spec in "${AGENT_WORKFLOW_LABELS[@]}"; do
            sync_label "$repo" "$spec"
        done
    else
        echo "  skip: agent workflow labels (use --with-agent-workflow-labels)"
        LABEL_SKIPPED=$((LABEL_SKIPPED + ${#AGENT_WORKFLOW_LABELS[@]}))
    fi
}

if [ "$LABELS_ONLY" = false ]; then
    copy_tree "$TEMPLATE_DIR/common" "$TARGET_DIR"

    if [ "$WITH_CODEX_CONFIG" = true ]; then
        if [ ! -d "$TEMPLATE_DIR/optional/codex-config" ]; then
            echo "Optional Codex config template not found: $TEMPLATE_DIR/optional/codex-config" >&2
            exit 1
        fi
        copy_tree "$TEMPLATE_DIR/optional/codex-config" "$TARGET_DIR"
    fi
elif [ "$WITH_CODEX_CONFIG" = true ]; then
    echo "--with-codex-config cannot be combined with --labels-only" >&2
    exit 1
fi

if [ "$SYNC_LABELS" = true ]; then
    sync_labels "$TARGET_DIR"
fi

echo ""
echo "Project agent bootstrap complete for: $TARGET_DIR"
echo "  Added:   $COPIED"
echo "  Skipped: $SKIPPED"
if [ "$SYNC_LABELS" = true ]; then
    echo "  Labels created: $LABEL_CREATED"
    echo "  Labels updated: $LABEL_UPDATED"
    echo "  Labels skipped: $LABEL_SKIPPED"
fi
echo ""
if [ "$LABELS_ONLY" = true ]; then
    echo "Next: no project files were changed; labels are synced."
elif [ "$DRY_RUN" = true ]; then
    echo "Next: rerun without --dry-run to apply project files."
else
    echo "Next: edit $TARGET_DIR/AGENTS.md, $TARGET_DIR/CLAUDE.md, and project-specific files under .claude/."
fi
if [ "$WITH_CODEX_CONFIG" = false ] && [ "$LABELS_ONLY" = false ]; then
    echo "Optional: rerun with --with-codex-config if this repo needs trusted project-level Codex config."
fi
