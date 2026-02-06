---
description: Execute a "main stays green" PR workflow for this monorepo
argument-hint: [pr-number]
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

## Post-Merge Cleanup

```bash
# Switch to main and pull
git checkout main && git pull

# Delete local feature branch
git branch -d feature/issue-${ISSUE}-description

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
- `/changelog` — Update changelog after merge
