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
commit → push → PR → validate/review → squash-merge → sync main
       → post-merge verify → prune branch → close/update the issue
```

Ordering matters (#367): post-merge verification runs BEFORE pruning. If
verification fails, do NOT prune — the branch is your recovery path; create
`fix/hotfix-<description>` from origin/main instead (see
`post-merge-verification.md`, which this sequence now matches).

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

After every PR merge, and before starting new work, prune merged branches:

```bash
~/agents/bin/agent-git cleanup --branch <merged-branch>
```

Manual fallbacks (`git fetch --prune`, deleting merged remote/local branches)
and the "enable auto-delete head branches" repo setting are in
`~/agents/docs/git-process.md` → "Merge And Cleanup".

## Parallel Agent Work

When multiple agents work simultaneously, give each its own worktree and
serialize same-file work. Full protocol (PR-overlap check, wave scheduling):
`~/agents/docs/git-process.md` → "File Conflicts And Parallel Work". Preferred
helper:

```bash
~/agents/bin/agent-git worktree add --issue <N> --slug <slug> --changed-path <path>
```

## Large Features & Emergencies

- **Large features (500+ lines)**: split into phased PRs, each leaving main
  working — see `~/agents/docs/git-process.md` → "Large Features".
- **Main is broken**: hotfix runbook in `~/agents/docs/git-process.md` →
  "Emergency: Main Is Broken".

## Never Do These

- Reuse one branch for multiple PRs
- Bundle multiple issues in one commit
- Ship `debug:` commits to main
- Implement then immediately revert (validate first)
- Force push to shared branches
- Skip CI with `--no-verify`
- Merge without rebasing on latest main
- `git stash` to clear the working tree and not restore it later (stash-and-forget).
  If a dirty tree blocks a pull, commit WIP to a `wip/<date>-<slug>` branch
  first — full procedure in `~/agents/docs/git-process.md` → "Working Tree
  Hygiene (Autonomous Runs)".
