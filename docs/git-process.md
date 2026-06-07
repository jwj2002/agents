# Standardized Git Process

This is the canonical git process for projects managed by `~/agents`. It
applies to Claude, Codex, humans, and any future automation surface.

The rule is simple: agent-owned issue work defaults to shipped work. If gates
pass, the agent commits, opens a PR, validates, squash merges, syncs `main`,
prunes stale refs, deletes the merged branch, and closes or updates the linked
issue. Stopping before merge is allowed only when a documented stop gate applies.

## Shared Contract

Every managed project should expose the process through:

- `AGENTS.md` for shared agent instructions.
- `CLAUDE.md` as the Claude adapter that points to `AGENTS.md`.
- Optional `.codex/config.toml` as the Codex adapter.
- `.github/pull_request_template.md` for required PR evidence.
- Standard GitHub labels for priority, blocking, validation, and spec slicing.

Claude and Codex must follow the same git rules. Tool-specific commands may be
thin wrappers, but the behavior should be implemented by shared shell or Python
helpers whenever possible.

## Default Ship Mode

For agent-owned issues, the expected lifecycle is:

1. Run `~/agents/bin/agent-git preflight`.
2. Create a branch from latest `origin/main`.
3. Implement the scoped change.
4. Prove the change through the project's validation ladder.
5. Commit only scoped files.
6. Open a PR with Summary, Test Plan, and issue linkage.
7. Rebase or update on latest `origin/main`.
8. Confirm CI and readiness gates.
9. Squash merge the PR.
10. Sync `main`, prune stale refs, and delete the merged branch.
11. Confirm the linked issue closed or update it with the remaining blocker.

The shared helper for this lifecycle is:

```bash
~/agents/bin/agent-git ship \
  --issue 123 \
  --summary "implemented the scoped change" \
  --test-evidence "pytest tests/test_example.py -q" \
  --allowed-path src/
```

Preview the full gate sequence without creating or merging a PR:

```bash
~/agents/bin/agent-git ship --dry-run --issue 123 --summary "..." --test-evidence "..."
```

Stopping is not completion. If an agent stops before merge, it must leave a PR
or issue comment with the blocker, current branch, validation status, and exact
next action.

## Stop Gates

Agents must stop before automatic merge when any of these apply:

- Tests or CI fail and cannot be fixed within scope.
- The implementation requires user approval because it is destructive,
  security-sensitive, production-data-sensitive, or changes public contracts.
- Branch protection requires a human review the agent cannot satisfy.
- The repo has unrelated dirty user work that blocks safe validation or merge.
- The issue scope is ambiguous enough that shipping would likely be wrong.
- GitHub, network, or credential failures prevent PR creation or merge.
- The user explicitly asks for draft or local-only work.

## Preflight

Before creating a branch or editing files, inspect:

```bash
~/agents/bin/agent-git preflight
```

Use JSON output when another tool or agent will consume the result:

```bash
~/agents/bin/agent-git preflight --json
```

Use `--path <path>` one or more times when the intended files are known and
open PR overlap should be checked for those paths.

Use `--include-ignored` only when ignored generated files matter for the
investigation; default output intentionally avoids dumping ignored cache
directories.

Determine:

- current branch and upstream
- default branch freshness
- dirty tracked, untracked, and ignored files
- whether dirty files are user work, generated output, runtime state, or
  agent-owned changes
- open PRs touching the same files
- project-specific validation commands

Unrelated user changes must be left untouched. If they block the task, ask the
user before moving, stashing, committing, deleting, restoring, or rewriting them.

## Branches

Start implementation branches from latest `origin/main`:

```bash
git fetch origin --prune
git switch -c <type>/issue-<number>-<slug> origin/main
```

Allowed branch types:

- `feature/`
- `fix/`
- `docs/`
- `test/`
- `chore/`
- `perf/`
- `refactor/`
- `wip/` for recoverable interruption branches only

Rules:

- Never commit directly to `main`.
- One branch maps to one PR.
- One PR maps to one logical change.
- Do not reuse merged or closed branches.
- Keep branches under 24 hours when possible and under 48 hours unless the
  issue documents why.

## Dirty Tree Protocol

Do not use anonymous stash as a cleanup shortcut.

Allowed:

- Leave unrelated user changes untouched.
- Add ignored patterns for generated files when that is the correct project fix.
- Commit agent-owned work on the active task branch.
- Create a named `wip/<date>-<slug>` branch when work must be made recoverable
  before interruption.

Forbidden without explicit user approval:

- `git reset --hard`
- `git checkout -- <path>`
- `git restore <path>` for files the agent did not create or intentionally edit
- deleting untracked files not created by the agent
- stashing unrelated user work
- committing unrelated user work

## File Conflicts And Parallel Work

Before editing, check open PR overlap when GitHub is available.

If another open PR touches the same files:

- independent same-file work should serialize
- dependent work should branch from the merged predecessor
- documentation-only overlap may proceed only when called out in the PR body

Parallel agents must use separate worktrees when operating in the same repo.

Create isolated worktrees through the shared helper:

```bash
~/agents/bin/agent-git worktree add \
  --issue 123 \
  --slug add-auth \
  --changed-path src/auth/
```

The default path is `.worktrees/issue-123-add-auth`, and the default branch is
`feature/issue-123-add-auth`. Use `--dry-run` to inspect the planned command
and open PR overlap before creating the worktree.

Remove completed worktrees with:

```bash
~/agents/bin/agent-git worktree remove --path .worktrees/issue-123-add-auth
```

Same-file work must serialize unless the user explicitly approves overlap.

## Validation Ladder

Each project defines its own commands, but agents must follow the same ladder:

1. Static or formatting checks, if present.
2. Unit tests for touched code, if present.
3. Integration or smoke tests for touched workflows, if present.
4. Manual verification when automation does not exist.

The PR must state exactly what ran and what failed or was skipped. "Not run" is
acceptable only with a concrete reason.

## Implementation Gates

An issue is not complete merely because files were added. Each issue must prove:

- **Implemented:** requested files, functions, scripts, docs, or config exist.
- **Wired:** behavior is reachable from the installer, command, workflow, agent
  instruction, CI job, or user-facing entrypoint that should invoke it.
- **Exercised:** at least one automated or manual test runs through that
  entrypoint.
- **Observed:** the PR includes command output summary, artifact, check result,
  or fixture evidence.
- **Documented:** user or agent-facing docs explain operational behavior.
- **Shipped:** PR is squash merged, `main` is synced, stale refs are pruned, and
  the issue is closed or explicitly blocked.

## Commits And PRs

Commits use Conventional Commits:

```text
type(scope): imperative summary
```

Rules:

- lowercase type
- no trailing period
- 72 character summary target
- one logical issue per PR
- commit only files in scope

Every PR must include:

- Summary
- Test Plan
- risk or rollback notes for non-trivial changes
- issue reference, usually `Closes #N`
- file conflict note if overlapping PRs were found

Use draft PRs only when validation is incomplete or user review is required
before merge.

Use the shared readiness helper before creating or merging an agent-owned PR:

```bash
~/agents/bin/agent-git readiness \
  --issue 123 \
  --summary "implemented the scoped change" \
  --test-evidence "pytest tests/test_example.py -q" \
  --allowed-path src/ \
  --generate-pr-body
```

Use `--stage merge` before merge to distinguish final readiness from initial PR
creation. The helper validates local branch evidence; GitHub CI remains the
source of truth for hosted checks.

## Merge And Cleanup

Default merge strategy is squash merge. Before merge:

- rebase or update on latest `origin/main`
- re-run relevant validation after conflict resolution
- confirm CI state
- confirm one logical change
- confirm implementation gates are satisfied or blocked by another issue

After merge:

```bash
~/agents/bin/agent-git cleanup --branch <merged-branch>
```

If a squash-merged local branch cannot be deleted with `-d`, verify the PR merge
first and then use:

```bash
~/agents/bin/agent-git cleanup --branch <branch> --squash-merged-branch
```

Preview cleanup without changing git state:

```bash
~/agents/bin/agent-git cleanup --dry-run
```

## Standard Labels

Universal labels for managed GitHub repositories:

- `P0`
- `P1`
- `P2`
- `blocked`
- `bug`
- `enhancement`
- `documentation`
- `tests`

Agent workflow labels for repositories using spec-driven issue planning:

- `from-spec`
- `build-slice`

Repo-local labels such as `git-process`, `ci`, `cleanup`, and domain labels
should be installed only when the repository opts in.

To sync universal labels for a managed GitHub project:

```bash
~/agents/new-project-agents.sh --sync-labels /path/to/project
```

To sync labels without touching project files:

```bash
~/agents/new-project-agents.sh --labels-only /path/to/project
```

For repositories that use spec-driven issue planning, include agent workflow
labels:

```bash
~/agents/new-project-agents.sh --sync-labels --with-agent-workflow-labels /path/to/project
```

Preview changes without writing files or labels:

```bash
~/agents/new-project-agents.sh --dry-run --labels-only --with-agent-workflow-labels /path/to/project
```
