# Standardized Git Process For All Projects

**Status:** Draft 2026-06-06

**Scope:** All projects managed by the agents repo, regardless of whether work
is performed by Claude, Codex, a human, or another automation surface.

---

## Why this exists

The current git discipline is useful but not portable enough. The strongest
rules live in `claude-config/rules/git-workflow.md`, which means Claude sees
them first and Codex or future agents only inherit them indirectly if project
bootstrap happens to expose the right files. Git workflow docs also exist in
multiple places, so drift is likely.

That is not good enough for multi-agent development. Git failures are usually
process failures: dirty trees, branch reuse, bundled changes, stale bases,
unreviewed conflicts, accidental main commits, incomplete cleanup, and agents
working on the same files without coordination. The process needs to be a
project-level contract, not a Claude feature.

This spec defines the cross-project git process every installed project should
receive and every first-class agent should follow.

---

## Goals

- Make the optimized git process portable to every current and future project
  installed through `~/agents`.
- Treat Claude and Codex as first-class git operators with the same rules,
  expectations, and enforcement points.
- Reduce avoidable git issues by making branch, commit, PR, merge, and cleanup
  discipline explicit.
- Make shipped work the default outcome for agent-owned issues: commit, open
  PR, validate, squash merge, sync, prune, and close unless a defined stop gate
  blocks shipping.
- Support autonomous agent work without allowing silent damage to user work,
  unrelated local changes, or main branch stability.
- Add labels that make workflow state, priority, and implementation slices
  visible in GitHub.
- Consolidate overlapping git docs into one canonical process with thin
  project-local pointers.
- Add validation so agents can prove the implementation is wired, exercised,
  and actually usable before opening or merging a PR.

---

## Non-goals

- This spec does not define product delivery methodology beyond git hygiene.
- This spec does not require one hosting provider forever, but the initial
  implementation may use `gh` because current workflows prefer GitHub CLI.
- This spec does not force every repo to use identical test commands. It defines
  how project-specific checks must be discovered and run.
- This spec does not authorize agents to overwrite, reset, stash, or discard
  unrelated user work.

---

## Current gaps

1. **The strongest workflow rules are Claude-centered.** Codex can read shared
   docs, but the process is not yet a Codex-native or project-native contract.
2. **Docs are duplicated.** `claude-config/rules/git-workflow.md`,
   `docs/manual/git/workflow.md`, `docs/manual/git/contributing.md`, and other
   docs overlap. Duplication will drift.
3. **There is no required preflight command.** Agents can say they checked the
   tree, but there is no canonical script that verifies branch, base, dirty
   state, open PR conflicts, issue linkage, and test evidence.
4. **Parallel work is underspecified across projects.** The rules mention
   worktrees and file conflict checks, but project bootstrap does not appear to
   install a reusable protocol or helper.
5. **Dirty tree handling is still too dependent on judgment.** The agents repo
   already has a known dirty telemetry shard. Every project needs a clear rule
   for user changes, generated files, local runtime state, and ignored artifacts.
6. **Labels are not standardized.** Some useful labels exist in this repo, but
   there is no optimized cross-project label taxonomy. A standard that is too
   large will become noise and agents will apply it inconsistently.
7. **Merge discipline is not mechanically guarded.** Squash merge, branch
   cleanup, and post-merge sync are rules, not enforced gates.
8. **No shared interruption protocol.** Long-running autonomous work needs a
   recoverable handoff state when an agent must stop before completion.
9. **"Complete" is too easy to claim.** Prior work can look done because files
   were created, while installer hooks, command routing, agent instructions,
   tests, or end-to-end usage are not actually wired. The process needs
   completion gates that prove the feature works through its intended entrypoint.

---

## Process contract

Every project installed through `~/agents` should expose a local git process
contract in agent-readable form:

- `AGENTS.md`: shared instructions for all agents.
- `CLAUDE.md`: Claude entrypoint that points to `AGENTS.md`.
- Optional `.codex/config.toml`: Codex project config.
- Optional `.codex/agents/` and `.codex/skills/`: Codex-native helpers.
- `docs/git-process.md`: human-readable project-local copy or pointer.
- `.github/pull_request_template.md`: required summary and validation evidence.
- `.github/labels.yml` or equivalent bootstrap data for standard labels.
- Project-specific check command declaration, preferably in one of:
  - `Makefile`
  - `package.json`
  - `pyproject.toml`
  - `justfile`
  - `AGENTS.md`

The installed contract must say that agents follow the same git rules whether
they are Claude, Codex, or another tool.

---

## Optimized git flow

### 1. Intake

Before modifying files, the agent must identify the work item.

- Preferred: a GitHub issue with clear scope and labels.
- Acceptable: an explicit user request in the current session.
- For autonomous multi-step work: create or update issues before implementation
  unless the user explicitly asks for local-only work.

Every implementation branch should map to one logical issue or one explicitly
bounded user request.

### 1A. Default ship mode

Agents should default to shipping issues end to end. For an agent-owned issue,
the expected lifecycle is:

1. Preflight the repo.
2. Create a correctly named branch from latest `origin/main`.
3. Implement the scoped change.
4. Prove the change through the project's validation ladder.
5. Commit the scoped files.
6. Open a PR with evidence.
7. Rebase or update on latest main.
8. Confirm CI and readiness gates.
9. Squash merge the PR.
10. Sync main, prune, and delete the merged branch.
11. Confirm the linked issue closed or update it with the remaining blocker.

Agents should stop before merge only when a stop gate applies:

- Tests or CI fail and cannot be fixed within scope.
- The implementation requires user approval because it is destructive,
  security-sensitive, production-data-sensitive, or changes public contracts.
- Branch protection requires a human review that the agent cannot satisfy.
- The repo has unrelated dirty user work that blocks safe validation or merge.
- The issue scope is ambiguous enough that shipping would likely be wrong.
- GitHub, network, or credential failures prevent PR creation or merge.
- The user explicitly asks for draft/local-only work.

Stopping is not completion. When a stop gate applies, the agent must leave a
clear issue or PR comment with the blocker, current branch, validation status,
and exact next action.

### 2. Preflight

Before creating a branch or editing files, the agent must inspect:

```bash
git status --short
git branch --show-current
git fetch origin --prune
gh pr list --state open --json number,title,headRefName,files
```

The agent must determine:

- current branch
- upstream branch
- uncommitted changes
- whether dirty files are user work, generated output, local runtime state, or
  agent-owned changes from this task
- open PRs that touch the same files
- project-specific validation commands

If uncommitted changes are unrelated to the task, the agent must leave them
alone. If unrelated changes block the task, the agent must ask before moving,
stashing, committing, deleting, or rewriting them.

### 3. Branch creation

All implementation work starts from the latest default branch:

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
- Keep branches short lived: less than 24 hours preferred, 48 hours maximum
  unless the issue explicitly documents why.

### 4. Dirty tree protocol

Agents must not use anonymous stash as a cleanup shortcut.

Allowed actions:

- Leave unrelated user changes untouched.
- Add ignored patterns for generated files only when that is the correct
  project fix.
- Commit agent-owned work on the active task branch.
- Create a named `wip/<date>-<slug>` branch when work must be made recoverable
  before interruption.

Forbidden actions without explicit user approval:

- `git reset --hard`
- `git checkout -- <path>`
- `git restore <path>` for files the agent did not create or intentionally edit
- deleting untracked files not created by the agent
- stashing unrelated user work
- committing unrelated user work

### 5. File conflict protocol

Before editing, agents must check open PR overlap when GitHub is available.

If another open PR touches the same files:

- If the changes are independent but same-file, serialize the work.
- If the changes are dependent, branch from the merged predecessor after it
  lands.
- If the overlap is documentation-only and low risk, the agent may proceed only
  after calling out the overlap in the PR body.

Parallel agents must use separate worktrees when operating in the same repo.

### 6. Implementation

Agents should keep changes scoped to the issue.

Rules:

- No drive-by refactors.
- No formatting unrelated files unless the project formatter requires it.
- No debug commits or temporary logging in final commits.
- No bundle commits that close multiple unrelated issues.
- Prefer small PRs that keep main working after every merge.
- Split features larger than roughly 500 changed lines into build slices.

### 7. Validation

Each project must define a validation ladder.

Minimum ladder:

1. Static or formatting checks, if present.
2. Unit tests for touched code, if present.
3. Integration or smoke tests for touched workflows, if present.
4. Manual verification steps when automation does not exist.

The agent must record exactly what ran and what failed or was skipped. "Not run"
is acceptable only when paired with a concrete reason.

### 7A. Wiring and implementation gates

An issue is not complete merely because code or docs were added. Each issue must
define gates that prove the change works through the intended entrypoint.

Minimum gates:

- **Implemented:** the requested files, functions, scripts, docs, or config
  exist.
- **Wired:** the new behavior is reachable from the installer, command,
  workflow, agent instruction, CI job, or user-facing entrypoint that is
  supposed to invoke it.
- **Exercised:** at least one automated or manual test runs through that
  entrypoint.
- **Observed:** the agent captures the command, output summary, artifact, PR
  check, or fixture result that proves the behavior executed.
- **Documented:** user or agent-facing docs explain the new behavior when the
  behavior is operationally meaningful.
- **Shipped:** the branch is merged, main is synced, stale refs are pruned, and
  the issue is closed or explicitly blocked.

Build-slice issues must include slice-specific gates. If a slice adds a helper
but does not wire it into installer or agent instructions, that must be called
out as a deliberate dependency on another issue, not marked complete by
implication.

### 8. Commit

Commits must use Conventional Commits:

```text
type(scope): imperative summary
```

Rules:

- Lowercase type.
- No trailing period.
- 72 character summary target.
- Reference one issue in the PR body, not by bundling many issue IDs into one
  commit message.
- Commit only files in scope.

### 9. PR creation

Every PR must include:

- Summary
- Test Plan
- Risk or rollback notes for non-trivial changes
- Issue reference, usually `Closes #N`
- File conflict note if overlapping PRs were found

Use draft PRs when validation is incomplete or user review is required before
merge.

### 10. Merge

Default merge strategy: squash merge.

For agent-owned issues, merge is part of the default workflow, not a separate
optional user step. After readiness gates pass, the agent should squash merge
and clean up automatically unless a stop gate from "Default ship mode" applies.

Before merge:

- Rebase or update on latest `origin/main`.
- Re-run the relevant validation ladder after conflict resolution.
- Confirm CI state.
- Confirm the PR still maps to one logical change.
- Confirm implementation gates are satisfied or explicitly documented as blocked
  by another issue.

After merge:

```bash
git switch main
git pull --ff-only
git fetch --prune origin
git branch -d <merged-branch>
```

If the local branch cannot be safely deleted, the agent must report why.

---

## Labels

Labels should be optimized, not exhaustive. A standard label must earn its place
by helping with triage, routing, automation, reporting, or merge discipline
across most managed repositories. Labels that only describe one repository, one
program, or one implementation project should stay local to that repository.

### Universal standard labels

These labels should be available in every managed GitHub repository:

- `P0`: urgent production breakage, blocked mainline, or work that must happen
  before anything dependent can proceed.
- `P1`: important work that should be scheduled soon.
- `P2`: normal priority.
- `blocked`: cannot proceed without another issue, decision, external input, or
  upstream merge.
- `bug`: behavior is broken.
- `enhancement`: new or improved capability.
- `documentation`: docs-only or docs-primary work.
- `tests`: test coverage, test infrastructure, or validation gaps.

### Agent workflow labels

These labels should be available in repositories where agents create or execute
spec-driven implementation issues:

- `from-spec`: issue derived from an accepted spec.
- `build-slice`: one independently mergeable part of a larger feature or spec.

These are still broadly useful for agent-managed repositories, but they are not
general GitHub defaults. Repositories that do not use spec-derived issue
planning do not need them.

### Repo-local labels

These labels can be useful inside `agents` or another repository with a clear
need, but they should not be installed everywhere by default:

- `git-process`: standardized git workflow, tooling, or documentation.
- `ci`: continuous integration or check failures.
- `cleanup`: branch, stale doc, generated file, or repository hygiene.
- `needs-triage`: scope or priority unclear.
- domain labels such as `team-knowledge`, `telemetry-validation`, or
  `fleet-usage-monitor`.

Do not standardize labels such as `agent-discipline` unless there is a concrete
workflow that filters, reports on, or automates them. Most agent discipline
belongs in issue text, specs, PR templates, and enforced checks rather than a
label.

Label rules:

- Every implementation issue should have exactly one priority label.
- Every blocked issue should explain the blocker in the issue body or latest
  comment, not only through the `blocked` label.
- Every spec-derived issue should have `from-spec`.
- Every split feature issue should have `build-slice`.
- Repo-local labels should be documented in that repo's `AGENTS.md` or
  contribution docs.

---

## Installer requirements

The agents project should provide a bootstrap path that can be run on current
and future projects:

```bash
~/agents/new-project-agents.sh /path/to/project
```

Target behavior:

- Install or update shared `AGENTS.md` git process instructions.
- Install or update Claude and Codex pointers without making either secondary.
- Add or refresh `docs/git-process.md`.
- Add or refresh `.github/pull_request_template.md`.
- Add or refresh the universal standard labels through `gh label create/edit`.
- Add agent workflow labels only when the repository uses spec-driven issue
  planning.
- Do not install repo-local labels unless the project explicitly opts in.
- Detect project validation commands and write them into `AGENTS.md`, or leave
  a clearly marked TODO when detection is not reliable.
- Install ship-mode instructions so agents understand that issue work defaults
  to commit, PR, squash merge, sync, prune, and close when gates pass.
- Refuse destructive changes when local files already exist with user edits.
- Provide an idempotent dry-run mode.

Recommended command shape:

```bash
~/agents/new-project-agents.sh --git-process /path/to/project
~/agents/new-project-agents.sh --git-process --with-codex-config /path/to/project
~/agents/new-project-agents.sh --git-process --dry-run /path/to/project
```

---

## Enforcement opportunities

The process should not remain docs-only. Recommended enforcement layers:

1. **Agent instructions:** `AGENTS.md`, `CLAUDE.md`, Codex config, skills.
2. **Preflight CLI:** a shared command such as
   `~/agents/bin/agent-git preflight`.
3. **PR template:** requires validation evidence and issue linkage.
4. **GitHub labels:** makes priority, blocking, validation, and spec slicing
   visible without creating noisy metadata.
5. **CI check:** optional repository workflow that validates PR title, linked
   issue, labels, and template sections.
6. **Post-merge helper:** syncs main, prunes remotes, deletes merged branches.
7. **Ship helper:** ties preflight, readiness, squash merge, cleanup, and issue
   closure into one repeatable workflow with explicit stop gates.

The most important missing piece is the preflight CLI. Without it, every agent
must independently remember the process and users will keep seeing inconsistent
behavior.

---

## Proposed implementation issues

### Issue 1 - Create canonical git process docs

Create canonical docs and remove or reduce duplicate workflow docs.

Acceptance criteria:

- `docs/git-process.md` is the canonical human-readable process.
- `AGENTS.md` includes the required agent git discipline.
- `CLAUDE.md` and Codex config point to the shared instructions.
- Existing duplicate docs point to the canonical doc instead of restating the
  full process.

Labels for this agents-repo issue: `documentation`, `git-process`, `P1`.

### Issue 2 - Add standard labels bootstrap

Add label setup to the project installer.

Acceptance criteria:

- Installer can create/update required labels using `gh`.
- Installer is idempotent.
- Installer has dry-run output.
- Existing labels are not deleted unless explicitly requested.

Labels for this agents-repo issue: `enhancement`, `git-process`, `P1`.

### Issue 3 - Build git preflight helper

Add a shared CLI that inspects git state before agents modify files.

Acceptance criteria:

- Reports current branch, upstream, default branch freshness, dirty files, and
  open PR file overlap.
- Distinguishes tracked, untracked, ignored, and generated-looking files.
- Exits non-zero on main branch implementation work, stale base, unresolved
  conflicts, and unsafe dirty tree states.
- Supports JSON output for agents and text output for humans.

Labels for this agents-repo issue: `enhancement`, `git-process`, `P1`.

### Issue 4 - Add PR validation helper

Add a helper that verifies PR readiness before create or merge.

Acceptance criteria:

- Confirms branch naming, issue linkage, commit format, changed files, and test
  evidence.
- Can generate PR body sections from collected evidence.
- Works for both Claude and Codex workflows.

Labels for this agents-repo issue: `enhancement`, `git-process`, `tests`, `P1`.

### Issue 5 - Add post-merge cleanup helper

Add a helper for sync, prune, and branch cleanup after merge.

Acceptance criteria:

- Pulls latest main with fast-forward only.
- Prunes stale remotes.
- Deletes merged local branches safely.
- Reports branches that cannot be deleted and why.

Labels for this agents-repo issue: `enhancement`, `git-process`, `P2`.

### Issue 6 - Add parallel agent worktree protocol

Document and automate the safe path for multiple agents working in one repo.

Acceptance criteria:

- Defines worktree naming and location.
- Checks open PR file overlap.
- Documents serialization rules for same-file edits.
- Provides cleanup steps for completed worktrees.

Labels for this agents-repo issue: `documentation`, `enhancement`,
`git-process`, `P2`.

### Issue 7 - Add default ship workflow

Add a workflow or helper that makes shipped work the default for agent-owned
issues.

Acceptance criteria:

- Defines stop gates that prevent unsafe automatic merge.
- Runs preflight, readiness validation, PR creation, squash merge, main sync,
  prune, and branch cleanup in order.
- Updates the linked issue or PR with validation evidence and blockers.
- Works for both Claude and Codex workflows.
- Includes fixture or dry-run coverage for success, failed validation, branch
  protection, dirty tree, and missing GitHub credentials.

Labels for this agents-repo issue: `enhancement`, `git-process`, `P1`.

---

## Validation strategy

Use a fixture repository to prove the process before broad rollout.

Required scenarios:

- clean repo, no open PRs
- dirty user-edited file unrelated to task
- dirty generated file
- untracked file
- current branch is `main`
- stale branch behind `origin/main`
- open PR touching same file
- missing GitHub CLI auth
- repo without GitHub remote
- project with no detectable test command
- successful PR-ready branch
- post-merge cleanup with deleted remote branch
- successful ship flow from issue to closed merged PR
- failed ship flow with a clear stop gate and issue/PR comment
- helper added but not wired into installer or agent entrypoint

Each scenario should have expected text and JSON output for the preflight
helper.

---

## Rollout plan

1. Accept this spec.
2. Create the implementation issues above with the standard labels.
3. Implement canonical docs and installer label bootstrap first.
4. Add preflight and PR validation helpers.
5. Add default ship workflow support.
6. Wire helpers into Claude and Codex instructions.
7. Run the installer on this agents repo as the first real project.
8. Run the installer on one non-agents project and capture gaps.
9. Expand to all active projects.

---

## Open questions

1. Should `gh` be a hard dependency for managed projects, or should the
   installer degrade gracefully for non-GitHub repositories?
2. Should the preflight helper block work on a dirty generated file, or only
   warn when the generated path is already ignored?
3. Should label bootstrap edit existing label colors and descriptions, or only
   create missing labels?
4. Which repositories require human review despite the default ship mode, and
   how should that repository-specific stop gate be declared?
5. Where should worktrees live by default: beside the repo, under
   `~/worktrees`, or under a project-local `.worktrees` directory?

---

## Acceptance criteria for the spec program

- Claude and Codex both receive the same project git rules.
- New projects installed through `~/agents` get git process docs, labels, PR
  template, and validation guidance.
- Current projects can be upgraded idempotently.
- Agents have a shared preflight command instead of relying on memory.
- PRs include consistent validation evidence.
- Post-merge cleanup is routine and documented.
- Parallel agent work has a worktree and conflict protocol.
- Duplicate git docs are consolidated or reduced to pointers.
- Agent-owned issues default to shipped work: committed, validated, squash
  merged, synced, pruned, and closed unless a documented stop gate applies.
- Each build-slice issue proves the implementation is wired through its intended
  entrypoint, not merely present in the repository.
