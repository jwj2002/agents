# Git Workflow

All agents follow a strict git workflow designed for multi-agent parallel development. The cardinal rule: **main stays green at all times**.

## Branch Naming

Every branch follows the pattern `{type}/issue-{N}-{slug}`:

| Type | When |
|------|------|
| `feature/` | New feature or capability |
| `fix/` | Bug fix |
| `chore/` | Maintenance, dependency updates |
| `docs/` | Documentation only |
| `test/` | Adding or updating tests |
| `perf/` | Performance improvement |

```
feature/issue-123-add-oauth-login
fix/issue-456-null-pointer-crash
chore/update-dependencies
docs/update-api-reference
```

!!! warning "Never"
    Never reuse a branch for multiple PRs. Never name a branch after a person or date. Never use `feat/` --- use `feature/` consistently.

### Branch Creation

Always branch from the latest `origin/main`:

```bash
git fetch origin && git checkout -b feature/issue-123-slug origin/main
```

### Branch Lifetime

Branches should live less than **24 hours** (48 hours maximum). Short-lived branches reduce merge conflicts and keep work focused.

## Commit Conventions

All commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description
```

- **Imperative mood**, lowercase, no period, max 72 characters
- Body explains **why**, not what (the diff shows what)
- Reference the issue: `Closes #123` or `Fixes #456`

| Type | When |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `perf` | Performance improvement |
| `chore` | Maintenance |
| `docs` | Documentation only |
| `test` | Test additions |
| `refactor` | Code restructure, no behavior change |
| `ci` | CI/CD configuration |
| `style` | Formatting only |

```
feat(auth): add OAuth2 login flow

Closes #123
```

!!! note "One Issue Per Commit"
    Never bundle multiple issues in one commit message. `feat: various improvements (#100-#107)` is forbidden. Each issue gets its own commit.

## Pre-PR Checklist

Before creating any PR, run these steps in order:

```bash
# 1. Rebase on latest main
git fetch origin && git rebase origin/main

# 2. Run checks (Python projects)
ruff check . && ruff format --check .
pytest tests/ -x --timeout=60

# 3. Verify only relevant files changed
git diff --name-only origin/main
```

If any check fails, fix it before creating the PR. Never skip checks with `--no-verify`.

## PR Creation

```bash
gh pr create --title "feat(scope): description" --body "$(cat <<'EOF'
## Summary
- What and why

## Test Plan
- [ ] Unit tests pass
- [ ] Manual verification

## Issue
Closes #123
EOF
)"
```

| Requirement | Detail |
|-------------|--------|
| Title | Conventional Commits format |
| Body | Summary, Test Plan, issue reference |
| Merge strategy | Squash merge only |
| After merge | Branch auto-deleted (repo setting) |

## Merge Strategy

**Squash merge only** --- all branches are squashed into a single commit on main. This produces a clean linear history where each commit maps to exactly one PR and one logical change.

The squash commit message on main should be:

```
type(scope): PR title (#PR-number)
```

## Post-Merge Cleanup

After every PR merge, run these cleanup steps:

```bash
# Prune stale remote refs
git fetch --prune origin

# Delete local branch
git branch -d feature/issue-123-slug
```

Before starting new work, prune stale branches:

```bash
# List merged remote branches (candidates for deletion)
git branch -r --merged origin/main | grep -v 'main\|HEAD'

# Clean local branches that track deleted remotes
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs -r git branch -D
```

!!! tip "Enable Auto-Delete"
    Set `Settings -> General -> Automatically delete head branches` on every repository. This handles 90% of stale branches automatically.

## Large Features (500+ Lines)

Split into phased PRs, each leaving main in a working state:

| Phase | Content | Example Branch |
|-------|---------|----------------|
| 1 | Schema/model changes | `feature/issue-601-phase-1-schema` |
| 2 | Service/business logic | `feature/issue-601-phase-2-service` |
| 3 | API/integration | `feature/issue-601-phase-3-api` |
| 4 | Tests | `feature/issue-601-phase-4-tests` |

Each phase branches from the **updated main** (after the previous phase merges). Never stack branches on top of each other.

## Emergency: Main is Broken

```
1. Stop all merges immediately
2. Create fix/hotfix-{description} from last green commit
3. Minimal fix only (smallest possible change)
4. Fast-track PR -> merge
5. Resume normal work
```

## Never-Do List

- Reuse one branch for multiple PRs
- Bundle multiple issues in one commit
- Ship `debug:` commits to main
- Implement then immediately revert (validate first)
- Force push to shared branches
- Skip CI with `--no-verify`
- Merge without rebasing on latest main
- Commit directly to main
