#!/bin/bash
# Install pre-commit git hook for code review
#
# Usage: ./install-hook.sh /path/to/project

PROJECT_DIR="${1:-.}"
HOOK_DIR="$PROJECT_DIR/.git/hooks"
HOOK_FILE="$HOOK_DIR/pre-commit"

if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "Error: $PROJECT_DIR is not a git repository"
    exit 1
fi

mkdir -p "$HOOK_DIR"

# Check if pre-commit hook already exists
if [ -f "$HOOK_FILE" ]; then
    echo "Warning: pre-commit hook already exists at $HOOK_FILE"
    echo "Backing up to $HOOK_FILE.backup"
    cp "$HOOK_FILE" "$HOOK_FILE.backup"
fi

cat > "$HOOK_FILE" << 'EOF'
#!/bin/bash
# Pre-commit hook: Code review before commit
#
# This hook runs code review on staged changes.
# To bypass: git commit --no-verify

echo "Running code review..."
echo ""

python3 ~/agents/code-review/review.py --strict

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "Commit blocked by code review."
    echo "Fix issues and try again, or bypass with: git commit --no-verify"
    exit 1
fi

exit 0
EOF

chmod +x "$HOOK_FILE"
echo "Installed pre-commit hook: $HOOK_FILE"
echo ""
echo "Code review will run before each commit."
echo "To bypass: git commit --no-verify"
