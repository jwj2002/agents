---
description: Execute a "main stays green" PR workflow for this monorepo
argument-hint: [pr-number]
disable-model-invocation: true
---

# PR Workflow

Goal: Execute a "main stays green" PR workflow.

## Usage

```bash
/pr                 # Create PR from current branch
/pr 123             # Review existing PR #123
/pr --merge 123     # Merge PR #123 after checks pass
```

---

## Pre-PR Checklist

Before creating a PR, verify:

```markdown
- [ ] On feature branch (NOT main/master)
- [ ] All changes committed
- [ ] Tests pass locally
- [ ] Linting passes locally
- [ ] Branch is up to date with main
```

### Verification Commands

```bash
# Check branch
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "ERROR: Cannot create PR from main branch"
  exit 1
fi

# Backend verification (if applicable)
cd backend && ruff check . && pytest -q

# Frontend verification (if applicable)
cd frontend && npm run lint && npm run build

# Ensure branch is up to date
git fetch origin main
git log origin/main..HEAD --oneline  # Show commits to include
```

---

## Pre-PR Fresh-Context Review

Spawn the `pr-fresh-reviewer` subagent to look at the diff with no
inheritance from the implementation discussion. Anthropic's published
guidance: a reviewer with fresh context catches what familiarity obscures.

```
Task(
  description='Fresh-context PR review',
  subagent_type='pr-fresh-reviewer',
  prompt='''Review the staged changes for this PR. The diff is the
  authoritative input — do not assume context from any prior discussion.

  Run `git diff origin/main...HEAD` to see all changes.
  Run `gh issue view {ISSUE} --json title,body,labels` to see the issue.

  Check the full E01-E15 behavioral evals as relevant to changed files.
  Apply the file→eval mapping from rules/eval-file-mapping.md.

  Report:
  - CRITICAL findings (block PR): security holes, data loss, broken
    deploys, missing migrations, secrets in code
  - WARNING findings (note in PR): correctness bugs, missing tests,
    inadequate error handling
  - SUGGESTION findings (optional): style, performance, readability

  If no issues: report "No issues found."
  Keep output under 30 lines.
  '''
)
```

**Gate**:
- If CRITICAL findings: STOP. Report to user. Do NOT create the PR until fixed.
- If WARNING findings: Include in PR body under `## Reviewer Notes`. Continue.
- If clean: Note "Fresh-context review: clean" in PR body. Continue.

This runs in addition to (not instead of) the Codex adversarial review for
MODERATE+ orchestrate work, which fires post-PROVE.

---

## Create PR

### Step 1: Summarize Scope

Determine stack from changed files:

```bash
git diff origin/main...HEAD --name-only | head -30
```

- **backend**: Only `backend/` files changed
- **frontend**: Only `frontend/` files changed
- **fullstack**: Both directories changed

### Step 2: Generate PR

```bash
# Extract issue number from branch name
ISSUE=$(echo "$BRANCH" | grep -oP '\d+' | head -1)

gh pr create \
  --title "feat: Brief description (#${ISSUE})" \
  --body "$(cat <<'EOF'
## What
[Brief description of changes]

## Why
[Problem being solved, link to issue]

Closes #ISSUE_NUMBER

## How
[Implementation approach]

## Stack
- [ ] Backend
- [ ] Frontend

## Contract Changes
[If fullstack: describe API changes, or "N/A"]

## Verification
- [ ] `ruff check .` passes
- [ ] `pytest -q` passes (N tests)
- [ ] `npm run lint` passes
- [ ] `npm run build` passes

## How to Test
1. [Step 1]
2. [Step 2]

## Risks / Rollback
[Any deployment risks or rollback steps, or "Low risk - isolated change"]

---
Artifacts: `.agents/outputs/*-ISSUE-*.md`
EOF
)"
```

---

## Review Existing PR

```bash
# View PR details
gh pr view $PR_NUMBER

# Check PR status (CI, reviews)
gh pr checks $PR_NUMBER

# View PR diff
gh pr diff $PR_NUMBER
```

---

## Merge Strategy

**Default**: Squash merge (clean history)

```bash
# Squash merge (recommended)
gh pr merge $PR_NUMBER --squash

# Standard merge (preserves individual commits)
gh pr merge $PR_NUMBER --merge
```

---

## Post-Merge Verification (MANDATORY)

After merge, verify main is healthy BEFORE branch cleanup.
Full checklist: `~/.claude/rules/post-merge-verification.md`

```bash
git checkout main && git pull origin main
ruff check . && ruff format --check .
pytest tests/ -x --timeout=60
```

**If any check fails**: STOP cleanup. Report failure. Suggest `fix/hotfix-*` branch.

---

## Post-Merge Cleanup

```bash
# Switch to main and pull
git checkout main && git pull

# Delete local feature branch
git branch -d feature/issue-${ISSUE}-description

# Archive artifacts for the merged issue
ARCHIVE_DIR=".agents/outputs/archive"
mkdir -p "$ARCHIVE_DIR"
for f in .agents/outputs/*-${ISSUE}-*.md; do
  [ -f "$f" ] && mv "$f" "$ARCHIVE_DIR/"
done

# If this issue used a worktree (--parallel mode), clean it up
python3 -c "
import sys
sys.path.insert(0, '$HOME/.claude/hooks')
from worktree_manager import remove_worktree
result = remove_worktree(${ISSUE})
if result:
    print('Worktree cleaned up: .worktrees/issue-${ISSUE}/')
else:
    print('No worktree found for issue ${ISSUE} (not using --parallel)')
"

# Verify main is green
cd backend && pytest -q
cd frontend && npm run build
```

---

## If Checks Fail

1. Read the failing check output: `gh pr checks $PR_NUMBER`
2. Fix issues on the feature branch
3. Push fixes: `git push`
4. Re-run checks: `gh pr checks $PR_NUMBER --watch`

---

## Related Commands

- `/orchestrate` — Generate implementation with artifacts
- `/review` — Pre-commit code review
