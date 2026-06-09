---
description: "Git workflow rules for all agents — branching, commits, PRs, parallel work"
alwaysApply: true
paths: ["**"]
---

# Git Workflow Rules

**Authority**: `~/agents/docs/git-process.md` (canonical full reference)

All agents MUST follow these rules for every git operation. Main stays green at all times.

## Ship by default

**Agent-owned issue work is shipped end-to-end, including the merge — without
pausing to ask for merge approval.** The terminal state of a task is a merged
PR, not an open one. The full default path:

```text
commit → push → PR → validate/review → squash-merge → prune branch
       → sync main → post-merge verify → close/update the issue
```

**Stop before merge ONLY when:**

- The user gives a specific instruction for that task ("PR only", "I'll merge
  this one", "hold", "don't merge yet").
- The issue or spec documents a stop gate (explicit human sign-off, release
  coordination, an irreversible/destructive production operation).

**These are NOT stop gates — they are "fix, then ship":** CI red, unresolved
`REQUEST_CHANGES`, merge conflicts, or branch protection requiring outside
approval. Resolve them and proceed to merge; do not hand merging back to the
user as a question.

High-risk classes (auth, payments, migrations, data-loss, secrets) still ship,
but run the Codex review BEFORE merge (see `implementation-routing.md`). Review
is a gate to clear, not a reason to stop shipping.

Do not ask "want me to merge?" as a matter of course. If there is genuine doubt
about whether a stop gate applies, that is the only time to ask.

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
# 0. Run shared preflight before agent-owned edits
~/agents/bin/agent-git preflight

# 1. Rebase on latest main
git fetch origin && git rebase origin/main

# 2. Run checks (Python projects)
ruff check . && ruff format --check .
pytest tests/ --timeout=60

# 3. Verify only relevant files changed
git diff --name-only origin/main

# 4. Verify branch, issue, commit, scope, and test evidence
~/agents/bin/agent-git readiness --issue <N> --summary "<summary>" --test-evidence "<command/result>"
```

If any check fails, fix it before creating the PR. Never skip checks.

## Completion Gates (MANDATORY)

An issue is not complete merely because files were added. It must be:

- implemented
- wired through the intended entrypoint
- exercised by automated or manual validation
- observed with command output, artifact, check result, or fixture evidence
- documented when operationally meaningful
- shipped or explicitly blocked by a documented stop gate

Prefer the shared ship workflow when available:

```bash
~/agents/bin/agent-git ship --issue <N> --summary "<summary>" --test-evidence "<command/result>"
```

## PR Creation

- **Title**: Must follow Conventional Commits format
- **Body**: Must include Summary, Test Plan, and issue reference (`Closes #N`)
- **Merge strategy**: Squash merge only
- **After merge**: Delete the remote branch (auto-delete should be enabled on repo)

## Branch Cleanup (MANDATORY)

After every PR merge:
```bash
~/agents/bin/agent-git cleanup --branch <merged-branch>

# Equivalent manual fallback:
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

Preferred helper:

```bash
~/agents/bin/agent-git worktree add --issue <N> --slug <slug> --changed-path <path>
```

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
- `git stash` to clear the working tree and not restore it later (stash-and-forget).
  If a dirty tree blocks a pull, see "Working tree hygiene" below.

## Working tree hygiene in `~/agents` (autonomous runs)

If uncommitted changes block a `git pull --ff-only`, never stash anonymously.
Instead, **commit the WIP to a throwaway branch first** so it is recoverable:

```bash
git checkout -b wip/$(date +%Y%m%d)-<context>
git add -A && git commit -m "wip: save state before reset"
git checkout -        # return to the original branch
```

Rationale: anonymous stashes silently bury real work. Four orphaned stashes were
found and cleaned up 2026-06-02 because unattended runs stashed to get a clean
`pull --ff-only` and never restored. A named branch keeps every change recoverable.

> Note: the perpetually-dirty-tree problem caused by telemetry shards
> (`telemetry/<host>/*.jsonl`) is **resolved** (#220 Win C): all shards are now
> gitignored and local-only. REC 0.1's OTEL hub — the intended cross-machine
> transport — is deferred indefinitely, so telemetry stays off the code repo
> (per the REC 0.1 principle) and the tree stays clean. The aggregate hook still
> writes shards locally; `/learn` + `telemetry_gate` still read them locally.
> There is no longer anything to stash or commit — shards never enter git.
