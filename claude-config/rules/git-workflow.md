---
description: "Git workflow rules for all agents — branching, commits, PRs, parallel work"
alwaysApply: true
paths: ["**"]
---

# Git Workflow Rules

**Authority**: ~/agents/docs/CONTRIBUTING_POLICY.md (full reference)

All agents MUST follow these rules for every git operation. Main stays green at all times.

## Branch Rules

- **Always branch from latest `origin/main`**: `git fetch origin && git checkout -b {branch} origin/main`
- **Naming**: `{type}/issue-{N}-{slug}` where type is `feature/`, `fix/`, `chore/`, `docs/`, `test/`, `perf/`
- **One branch = one PR = one logical change** — NEVER reuse a branch for multiple PRs
- **Branch lifetime**: < 24 hours preferred, 48 hours max
- **Never commit directly to main**

## Commit Rules

- **Conventional Commits**: `type(scope): description` (imperative, lowercase, no period, max 72 chars)
- **One issue per commit** — never bundle `(#123, #124, #125)` in one commit message
- **No `debug:` commits** — remove all debug logging before creating PR
- **No flip-flops** — validate architecture decisions with data BEFORE implementing

## Pre-PR Checklist (MANDATORY)

Before creating any PR, run these steps in order:

```bash
# 1. Rebase on latest main
git fetch origin && git rebase origin/main

# 2. Run checks (Python projects)
ruff check . && ruff format --check .
pytest tests/ --timeout=60

# 3. Verify only relevant files changed
git diff --name-only origin/main
```

If any check fails, fix it before creating the PR. Never skip checks.

## PR Creation

- **Title**: Must follow Conventional Commits format
- **Body**: Must include Summary, Test Plan, and issue reference (`Closes #N`)
- **Merge strategy**: Squash merge only
- **After merge**: Delete the remote branch (auto-delete should be enabled on repo)

## Branch Cleanup (MANDATORY)

After every PR merge:
```bash
# Prune stale remote refs
git fetch --prune origin

# Delete local branch
git branch -d feature/issue-N-slug
```

Before starting any new work, prune stale branches:
```bash
# List merged remote branches (candidates for deletion)
git branch -r --merged origin/main | grep -v 'main\|HEAD'

# Delete stale remote branches that are already merged
# (only if auto-delete is not enabled on the repo)
git push origin --delete <branch-name>

# Clean local branches that track deleted remotes
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs -r git branch -D
```

**Repo setting**: Enable `Settings → General → Automatically delete head branches` on every repo.

## Parallel Agent Work

When multiple agents work simultaneously:

1. **Check for file conflicts**: `gh pr list --state open --json headRefName,files`
2. **No two agents edit the same file** — if overlap exists, serialize (Agent B waits for Agent A)
3. **Use worktree isolation**: Each agent gets its own git worktree
4. **Rebase before PR**: After other agents merge, rebase on the new main
5. **Wave scheduling**: Group independent issues into parallel waves; dependent issues run sequentially

## Large Features (500+ lines)

Split into phased PRs, each leaving main in a working state:
- Phase 1: Schema/model → merge
- Phase 2: Service/logic → merge (branch from updated main)
- Phase 3: API/integration → merge
- Phase 4: Tests → merge

## Emergency: Main is Broken

1. Stop all merges immediately
2. Create `fix/hotfix-{description}` branch from last green commit
3. Minimal fix only
4. Fast-track PR → merge
5. Resume normal work

## Never Do These

- Reuse one branch for multiple PRs
- Bundle multiple issues in one commit
- Ship `debug:` commits to main
- Implement then immediately revert (validate first)
- Force push to shared branches
- Skip CI with `--no-verify`
- Merge without rebasing on latest main
