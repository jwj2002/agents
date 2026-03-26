# Contributing Policy: Multi-Agent Parallel Development

**Version**: 1.0
**Date**: 2026-03-14
**Scope**: All projects managed by AI agents under ~/agents/

---

## Core Tenets

1. **Main stays green at all times** — main is always deployable, always passes all checks
2. **One branch = one PR = one logical change** — no branch reuse, no mega-commits
3. **Agents own files, not branches** — parallel work is safe when agents touch different files
4. **Squash merge everything** — clean linear history on main
5. **No direct commits to main** — all changes go through PRs with status checks

---

## Branching Strategy: GitHub Flow + Worktree Isolation

```
main (protected, always green)
  │
  ├── feature/issue-123-add-auth     (Agent A, worktree A)
  ├── fix/issue-124-login-bug        (Agent B, worktree B)
  ├── feature/issue-125-dashboard    (Agent C, worktree C)
  └── ... (short-lived, <24 hours)
```

### Rules

| Rule | Detail |
|------|--------|
| Branch from | Always `main` (latest) |
| Branch lifetime | < 24 hours preferred, 48 hours max |
| Branch naming | `{type}/issue-{N}-{slug}` |
| Types | `feature/`, `fix/`, `chore/`, `docs/`, `test/`, `perf/` |
| One branch per | One GitHub issue or one logical change |
| Rebase before PR | `git fetch origin && git rebase origin/main` |
| Merge strategy | Squash merge only |
| Delete after merge | Always (enable `deleteBranchOnMerge` on repo) |

### Branch Naming Convention

```
feature/issue-123-add-oauth-login     # New feature tied to issue
fix/issue-456-null-pointer-crash      # Bug fix tied to issue
chore/update-dependencies             # Maintenance (no issue required)
docs/update-api-reference             # Documentation only
test/issue-789-add-integration-tests  # Test additions
perf/issue-321-optimize-query         # Performance improvement
```

**Never**:
- Reuse a branch for multiple PRs
- Name a branch after a person or date
- Use `feat/` (use `feature/` consistently)

---

## Parallel Agent Workflow

### File Ownership Model

Before agents start parallel work, the orchestrator assigns **non-overlapping file sets** per agent. Two agents must never edit the same file simultaneously.

```
Agent A: src/auth/login.py, src/auth/oauth.py
Agent B: src/api/users.py, src/api/schemas.py
Agent C: tests/test_auth.py, tests/test_users.py
```

If two agents must touch the same file, **serialize them** — Agent B starts after Agent A's PR merges.

### Worktree Isolation

Each agent works in its own git worktree:

```bash
# Create isolated worktree for agent
git worktree add ../project-agent-A feature/issue-123-add-auth

# Agent works in ../project-agent-A/
# Changes are isolated from other agents

# After PR merges, clean up
git worktree remove ../project-agent-A
```

Claude Code agents use `isolation: "worktree"` parameter for automatic worktree management.

### Parallel Work Pre-Checks

Before starting work, every agent MUST:

1. **Sync main**: `git fetch origin main`
2. **Branch from latest main**: `git checkout -b {branch} origin/main`
3. **Verify no conflicts with in-flight PRs**: `gh pr list --state open --json headRefName,files`
4. **Claim file ownership**: Check that no open PR touches the same files

### Parallel Work Post-Checks

Before creating a PR, every agent MUST:

1. **Rebase on latest main**: `git fetch origin && git rebase origin/main`
2. **Run all checks locally**:
   ```bash
   # Python projects
   ruff check .                    # Lint
   ruff format --check .           # Format
   mypy src/                       # Type check (if configured)
   pytest tests/ -x --timeout=60   # Tests
   ```
3. **Resolve any conflicts** — if rebase has conflicts, fix them; never force-push over someone else's work
4. **Verify the change is minimal** — only files related to the issue are modified

---

## Commit Message Convention

All commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body explaining WHY, not WHAT]

[optional footer: issue references, breaking changes]
```

### Types

| Type | When |
|------|------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `perf` | Performance improvement |
| `chore` | Maintenance, dependency updates |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `refactor` | Code restructure, no behavior change |
| `ci` | CI/CD configuration changes |
| `style` | Formatting, whitespace (no logic change) |

### Rules

- Subject line: imperative mood, lowercase, no period, max 72 chars
- One issue per commit message (no `(#123, #124, #125)` bundles)
- Body explains **why**, not what (the diff shows what)
- Reference the issue: `Closes #123` or `Fixes #456`

### Examples

```
feat(auth): add OAuth2 login flow

Closes #123
```

```
fix(memory): prevent duplicate embeddings on re-index

The ingestion pipeline was creating duplicate chunks when re-indexing
a file that had already been indexed. Added content hash dedup check.

Fixes #456
```

**Never**:
- `debug:` commits (remove debug code before PR)
- `fix: fix the fix` (amend or squash into the original)
- `feat: Various improvements (#100-#107)` (one issue per commit)

### Squash Merge Commit Message

When squash-merging a PR, the commit message on main should be:

```
type(scope): PR title (#PR-number)
```

GitHub can auto-populate this from the PR title. Enforce PR titles follow Conventional Commits.

---

## Pull Request Process

### Creating a PR

```bash
# 1. Ensure branch is up to date
git fetch origin && git rebase origin/main

# 2. Push branch
git push -u origin feature/issue-123-description

# 3. Create PR with structured body
gh pr create --title "feat(scope): description" --body "$(cat <<'EOF'
## Summary
- What this PR does and why

## Changes
- File-by-file description of changes

## Test Plan
- [ ] Unit tests pass
- [ ] Integration tests pass (if applicable)
- [ ] Manual verification steps

## Issue
Closes #123

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### PR Requirements (Enforced)

| Check | Required | How |
|-------|----------|-----|
| Status checks pass | Yes | GitHub branch protection |
| Lint clean | Yes | `ruff check` in CI |
| Format clean | Yes | `ruff format --check` in CI |
| Tests pass | Yes | `pytest` in CI |
| No merge conflicts | Yes | Rebase on latest main |
| PR title follows convention | Yes | CI check or bot |
| Linked to issue | Recommended | `Closes #N` in body |
| Self-review checklist complete | Recommended | PR template |

### PR Size Guidelines

| Size | Files Changed | Lines Changed | Guideline |
|------|--------------|---------------|-----------|
| Small | 1-3 | < 100 | Ideal — fast review, low risk |
| Medium | 4-8 | 100-500 | Acceptable — one logical feature |
| Large | 9+ | 500+ | Split into smaller PRs if possible |

If a feature requires 500+ lines of changes, break it into sequential PRs that each leave main in a working state.

---

## Merge Queue

Enable GitHub's native merge queue on all protected repositories:

```
Settings → Branches → Branch protection → main
  ✓ Require merge queue
    - Merge method: Squash merge
    - Max group size: 5
    - Min group size: 1
    - Wait time: 0 minutes
    - Required checks: lint, test, build
```

The merge queue ensures:
1. Each PR is tested against the latest main + all PRs ahead in the queue
2. Two PRs that pass CI independently but conflict semantically are caught
3. Main never breaks, even under high merge velocity

---

## CI/CD Pipeline

### Minimum Viable CI (GitHub Actions)

Every project MUST have CI that runs on PR creation and push:

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest tests/ -x --timeout=120
```

### Extended CI (as project matures)

| Check | Priority | When to Add |
|-------|----------|-------------|
| Lint + format | P0 | Day 1 |
| Unit tests | P0 | Day 1 |
| Type checking (mypy/pyright) | P1 | When types are established |
| Integration tests | P1 | When external services exist |
| Security scan (bandit/safety) | P2 | When handling user data |
| Build/package | P2 | When distributing artifacts |
| Coverage threshold | P3 | When coverage > 60% |

---

## Branch Protection Configuration

### Required Settings

```
Settings → Branches → Add rule → main

✓ Require a pull request before merging
  - Required approving reviews: 0 (solo dev) or 1 (team)
  - Dismiss stale reviews on new push: ✓

✓ Require status checks to pass before merging
  - Require branches to be up to date: ✓
  - Status checks: check (from CI workflow)

✓ Require linear history (enforces squash/rebase merge)

✓ Do not allow bypassing the above settings

✗ Require signed commits (optional, add when needed)
✗ Require deployments to succeed (add when staging exists)

✓ Restrict deletions
✓ Block force pushes
```

### Auto-Delete Branches

```
Settings → General → Pull Requests
  ✓ Automatically delete head branches
```

---

## Workflow Use Cases

### Use Case 1: Quick Fix (Single File, < 30 min)

```
1. git fetch origin && git checkout -b fix/issue-N-slug origin/main
2. Make the fix (1-3 files)
3. Run checks: ruff check . && ruff format --check . && pytest tests/ -x
4. git add <specific-files> && git commit -m "fix(scope): description"
5. git push -u origin fix/issue-N-slug
6. gh pr create --title "fix(scope): description" --body "Fixes #N"
7. CI passes → squash merge → branch auto-deleted
```

**Agent command**: Plan mode (1-3 files, high confidence)

### Use Case 2: Feature Implementation (Multi-file, 1-4 hours)

```
1. git fetch origin && git checkout -b feature/issue-N-slug origin/main
2. Implement feature across files
3. Run full check suite
4. git add <specific-files> && git commit -m "feat(scope): description"
5. git push -u origin feature/issue-N-slug
6. gh pr create with full body (summary, changes, test plan)
7. CI passes → squash merge → branch auto-deleted
```

**Agent command**: Plan mode or `/orchestrate` depending on complexity

### Use Case 3: Orchestrated Multi-Issue Work (Cross-cutting, 4+ hours)

```
1. /orchestrate issue-N
   - MAP phase: classify complexity, identify files
   - PLAN phase: file-by-file implementation plan
   - PATCH phase: implement changes
   - PROVE phase: verify, test, record outcome

2. Each issue gets its own branch: feature/issue-N-slug
3. Sequential PRs if issues have dependencies
4. Parallel PRs if issues are independent (different files)
```

**Critical rule**: Even orchestrated work produces ONE PR per issue. Never bundle multiple issues into one PR.

### Use Case 4: Parallel Agent Execution (2+ agents, simultaneous)

```
Orchestrator:
  1. Fetch open PRs: gh pr list --state open --json files
  2. Assign file ownership per agent (no overlap)
  3. Launch agents with worktree isolation

Agent A (worktree-A):                    Agent B (worktree-B):
  1. git checkout -b feature/A main        1. git checkout -b feature/B main
  2. Edit src/auth/*.py                    2. Edit src/api/*.py
  3. Run checks                            3. Run checks
  4. Push + create PR                      4. Push + create PR
  5. CI passes → merge                     5. CI passes → merge

Post-merge:
  - Remaining agents rebase on new main
  - Continue with next task
```

### Use Case 5: Hotfix (Production Bug, Urgent)

```
1. git fetch origin && git checkout -b fix/issue-N-hotfix origin/main
2. Minimal fix (smallest possible change)
3. Run checks (at minimum: tests covering the fix)
4. git add <specific-files> && git commit -m "fix(scope): critical description"
5. git push -u origin fix/issue-N-hotfix
6. gh pr create --title "fix(scope): description" --body "Fixes #N (hotfix)"
7. Fast-track review → squash merge
```

### Use Case 6: Large Feature (Multi-PR, Phased)

When a feature requires 500+ lines, break it into phases:

```
Phase 1: Schema/model changes
  - feature/issue-N-phase-1-schema → PR → merge

Phase 2: Service/business logic
  - feature/issue-N-phase-2-service → PR → merge (branched from updated main)

Phase 3: API/routes
  - feature/issue-N-phase-3-api → PR → merge

Phase 4: UI/frontend
  - feature/issue-N-phase-4-ui → PR → merge
```

**Rules for phased work**:
- Each phase leaves main in a working state
- Use feature flags if the feature is incomplete but code is on main
- Each phase is a separate branch from the latest main (not stacked branches)
- Never merge Phase 2 before Phase 1 is on main

### Use Case 7: Spec → Issues → Implementation

Full lifecycle from idea to shipped code. Three distinct phases with a hard
gate between spec finalization and implementation.

```
Phase A: Drafting (agent-driven)
  1. /spec-draft "feature name"
     - Agent creates branch: docs/spec-{slug} from origin/main
     - Agent explores codebase, asks guided questions
     - Agent writes docs/specs/spec_{name}.md (status: draft)
     - Agent commits, pushes, creates DRAFT PR
     → Output: draft PR with spec ready for team review

Phase B: Review & Finalization (human-driven)
  2. Team reviews draft PR, leaves comments
  3. Agent or human addresses feedback (commits on same branch)
  4. Repeat until team approves
  5. Update spec frontmatter: status: draft → status: final
  6. Undraft PR → squash merge to main
     → GATE: spec is now on main as single commit

Phase C: Issue Creation & Implementation (agent-driven)
  7. /spec-review docs/specs/spec_{name}.md --create-issues
     - ENFORCED: must be on main branch, spec status must be "final"
     - Generates GitHub issues with dependency analysis
  8. Issues are grouped into waves by dependency
  9. Independent issues run in parallel (Use Case 4)
  10. Dependent issues run sequentially
  11. Each issue is implemented via Use Case 2, 3, or 4
```

**The gate between Phase B and C is critical**: no implementation issues are
created until the spec is finalized and merged to main. This prevents:
- Coding against a draft that changes
- Multiple agents reading different spec versions
- Rework when spec decisions are reversed during review

### Use Case 8: Documentation Updates (README, guides, architecture docs)

Documentation lives in the repo alongside code. It follows the same branch/PR flow
but with lighter gates — no test suite required, focus on accuracy and completeness.

**When**: Updating README, adding architecture docs, writing guides, updating
API reference, maintaining changelogs, onboarding docs.

```
1. git fetch origin && git checkout -b docs/issue-N-slug origin/main
   (or docs/update-architecture-overview if no issue)
2. Write or update documentation
3. Pre-PR checks (docs-specific):
   - Links are valid (no broken references to files or sections)
   - Code examples are accurate (match current API/codebase)
   - No stale version numbers, dates, or file paths
   - Consistent formatting (heading levels, list style, code fences)
   - If referencing code: verify the referenced code exists and is current
4. git add <doc-files> && git commit -m "docs(scope): description"
5. git push -u origin docs/issue-N-slug
6. gh pr create --title "docs(scope): description"
7. Review for accuracy → squash merge
```

**Branch naming**: `docs/` prefix
**Commit type**: `docs(scope): description`
**CI**: Lint/format checks still run but test failures in unrelated code should
not block a docs-only PR. If the project has a docs CI job (markdown lint,
link checker), that is the required gate.

**Key rules**:
- Docs PRs should NOT include code changes (keep them separate)
- If docs accompany a code change, include them in the code PR — don't split
  a feature across a code PR and a docs PR
- Architecture docs should reference actual file paths so they stay traceable
- Date-stamp decision records: "Decided 2026-03-14: use WebSocket over WebRTC"

**Agent routing**: Direct execution (no Plan Mode or Orchestrate needed).
Read the existing doc, make changes, verify accuracy against codebase.

### Use Case 9: Spec Drafting & Iteration (design docs, RFCs, proposals)

Specs are iterative — they go through multiple rounds of review before
they're "final." They follow a different lifecycle than code or docs.

**When**: Writing a new feature spec, RFC, design proposal, architecture
decision record (ADR), or any document that requires review and approval
before implementation begins.

```
Drafting Phase:
  1. /spec-draft "feature name"
     - Agent creates branch: docs/spec-{slug}
     - Agent explores codebase, asks guided questions
     - Agent writes spec to docs/specs/spec_{name}.md (status: draft)
     - Agent commits, pushes, creates DRAFT PR
     → Output: draft PR ready for team review

Review Phase (iterate on the draft):
  2. Team reviews draft PR, leaves comments
  3. Agent (or human) addresses feedback on the same branch:
     - Edit spec → commit → push (additional commits are fine on draft PRs)
     - Each revision is a new commit: "docs(spec): address review — round N"
  4. Repeat until team approves

Finalization Phase:
  5. Update spec frontmatter: status: draft → status: final
  6. Final commit: "docs(spec): finalize spec for feature-name"
  7. Mark PR as ready for review (undraft)
  8. Squash merge → spec is now on main as single commit

Issue Creation Phase (AFTER merge to main):
  9. /spec-review docs/specs/spec_{name}.md --create-issues
     - GATE: spec must be on main and status must be "final"
     - Generates GitHub issues with dependency graph
  10. Implementation begins via Use Cases 2-7
```

**Branch naming**: `docs/spec-{slug}`
**Commit type**: `docs(spec): description`
**PR state**: Start as **draft** — specs aren't ready to merge until finalized

**Key rules**:
- `/spec-draft` creates the branch and draft PR — the agent handles git workflow
- `/spec-review --create-issues` only runs AFTER the spec PR is merged to main
  (enforced: checks current branch and spec status frontmatter)
- Specs live in the repo (not in Google Docs, Notion, or email)
- Specs are versioned — main always has the latest approved version
- Draft PRs allow multiple commits without polluting main (squash on merge)
- Never start implementation before the spec PR is merged
- If the spec changes after implementation starts, update the spec on main
  via a separate `docs/` PR, then adjust implementation accordingly
- Include a "Decision Log" section in specs for recording choices and rationale:
  ```markdown
  ## Decision Log
  | Date | Decision | Rationale |
  |------|----------|-----------|
  | 2026-03-14 | Use RRF over simple interleaving | Better precision at top-k, see benchmarks in #601 |
  ```

**Spec lifecycle**:
```
  /spec-draft "feature"
    → DRAFT (on branch, draft PR created automatically)
    → REVIEW (team reviews PR, leaves comments)
    → ITERATE (agent/human addresses feedback on branch)
    → FINALIZE (status: final, PR undrafted, squash merged to main)
    → /spec-review --create-issues (on main, generates GitHub issues)
    → IMPLEMENTATION (Use Cases 2-7)
    → COMPLETED (spec remains on main as historical record)
```

**What belongs in a spec vs. what doesn't**:

| In the Spec | Not in the Spec |
|-------------|-----------------|
| Problem statement and motivation | Implementation code |
| Proposed solution and alternatives considered | Detailed function signatures (put in code) |
| API contracts (endpoints, request/response shapes) | Test code |
| Data model changes (schema, migrations) | CI/CD configuration |
| Security considerations | Deployment scripts |
| Decision log with rationale | Meeting notes (put in project docs) |
| Success criteria / acceptance tests | Timeline estimates |
| Dependencies and sequencing | Assignment of who does what |

**Agent routing**: `/spec-draft` for creation (handles branching + draft PR),
`/spec-review` for issue generation (only after spec is merged to main).
Human review is expected between drafting and finalization.

---

## Spec Workflow Reference

### `/spec-draft` — What It Does

| Step | Action | Git Operation |
|------|--------|---------------|
| 1 | Classify feature type (CRUD, Fullstack, etc.) | — |
| 2 | Discover related patterns in codebase | Read-only |
| 3 | Ask guided questions based on feature type | — |
| 4 | Auto-fill from codebase discovery | Read-only |
| 5 | Generate risk flags (ENUM_VALUE, COMPONENT_API, etc.) | — |
| 6 | Completeness check — flag missing sections | — |
| 7 | Create branch `docs/spec-{slug}` from `origin/main` | `git checkout -b` |
| 8 | Write spec to `docs/specs/spec_{name}.md` with `status: draft` | `git add` + `git commit` |
| 9 | Push branch and create **draft PR** | `git push` + `gh pr create --draft` |

**Output**: Draft PR URL, spec file path, completeness score, risk flags.

**Spec file location**: `docs/specs/spec_{name}.md`

**Spec frontmatter**:
```yaml
---
title: Feature Name
status: draft          # draft → final (updated during review)
created: 2026-03-14
author: user
type: CRUD|Integration|UI|Enhancement|Fullstack
complexity: TRIVIAL|SIMPLE|COMPLEX
---
```

**Required spec sections**:
- Summary, Goals, Scope (In/Out)
- Technical Specification (varies by type)
- Risk Flags (auto-generated)
- Decision Log (filled during review)
- Acceptance Criteria
- Open Questions

### `/spec-review` — What It Does

| Step | Action | Gate |
|------|--------|------|
| 1 | Validate spec file exists | File must exist |
| 2 | Check branch — warn if not on `main` | Warning only |
| 3 | Check spec `status:` frontmatter | **BLOCKS `--create-issues` if status is `draft`** |
| 4 | Extract all requirements from spec | — |
| 5 | Search codebase for existing implementations | Read-only |
| 6 | Classify gaps: Implemented / Partial / Missing / Differs | — |
| 7 | Generate spec review artifact | Write to `.agents/outputs/` |
| 8 | Create GitHub issues (if `--create-issues`) | `gh issue create` |

**Modes**:
- `--dry-run` (default): Analyze only, report gaps, no issues created
- `--create-issues`: Create GitHub issues for each gap. **Requires**: on `main` branch AND spec `status: final`

**Output**: Gap summary (counts by status), issue URLs (if created), recommended implementation order.

### End-to-End Flow Diagram

```
                    ┌──────────────────────────────┐
                    │  /spec-draft "feature name"  │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  Agent creates branch +      │
                    │  writes spec + draft PR      │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  Team reviews draft PR       │
                    │  Comments + iteration        │◄──── Repeat as needed
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  status: draft → final       │
                    │  Undraft PR → squash merge   │
                    └──────────────┬───────────────┘
                                   │
                    ═══════════════╪═══════════════  ← GATE: spec on main
                                   │
                    ┌──────────────▼───────────────┐
                    │  /spec-review --create-issues│
                    │  (must be on main, status:   │
                    │   final)                     │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  GitHub issues created with  │
                    │  dependency graph            │
                    └──────────────┬───────────────┘
                                   │
               ┌───────────────────┼───────────────────┐
               │                   │                   │
     ┌─────────▼──────┐  ┌────────▼───────┐  ┌────────▼───────┐
     │  /orchestrate   │  │  /orchestrate  │  │  /orchestrate  │
     │  issue-A        │  │  issue-B       │  │  issue-C       │
     │  (parallel)     │  │  (parallel)    │  │  (waits for A) │
     └────────┬────────┘  └────────┬───────┘  └────────┬───────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  All issues implemented      │
                    │  Main stays green throughout │
                    └──────────────────────────────┘
```

---

## Conflict Prevention Checklist

### Before Starting Work

- [ ] `git fetch origin main` — have the latest main
- [ ] `gh pr list --state open` — check for in-flight PRs
- [ ] No open PR touches my target files
- [ ] Branch created from `origin/main` (not a stale local main)

### Before Creating PR

- [ ] `git fetch origin && git rebase origin/main` — rebased on latest
- [ ] No merge conflicts after rebase
- [ ] All checks pass locally (lint, format, test)
- [ ] Only relevant files are staged (no accidental inclusions)
- [ ] Commit message follows Conventional Commits
- [ ] PR title follows Conventional Commits

### After PR Created

- [ ] CI status checks pass
- [ ] PR is linked to issue (if applicable)
- [ ] No other PRs merged to main that conflict with this PR
- [ ] If main advanced, rebase and re-push

### After PR Merged

- [ ] Remote branch is deleted (auto-delete should handle this)
- [ ] Local branch cleaned up: `git branch -d feature/issue-N-slug`
- [ ] Prune stale remote refs: `git fetch --prune origin`
- [ ] If other agents are running, notify them to rebase

---

## Branch Hygiene

Stale branches accumulate when auto-delete isn't enabled or when branches
are created but never merged. This section covers prevention and cleanup.

### Prevention (Repo Settings)

Every repo MUST have auto-delete enabled:
```
Settings → General → Pull Requests
  ✓ Automatically delete head branches
```

This handles 90% of stale branches. The remaining 10% are branches that
were never merged (abandoned work, experiments, superseded PRs).

### Cleanup: After Every PR Merge

Every agent MUST run this after a PR is merged:
```bash
# Prune remote tracking refs that no longer exist on origin
git fetch --prune origin

# Delete the local branch
git branch -d feature/issue-N-slug
```

### Cleanup: Before Starting New Work

Every agent SHOULD prune before creating a new branch:
```bash
# Sync and prune in one step
git fetch --prune origin
```

### Cleanup: Periodic Hygiene (Weekly)

Run this weekly (or when branch list looks cluttered):

```bash
# 1. List remote branches already merged to main (safe to delete)
git branch -r --merged origin/main | grep -v 'main\|HEAD'

# 2. Delete merged remote branches (if auto-delete missed them)
git branch -r --merged origin/main | grep -v 'main\|HEAD' | \
  sed 's|origin/||' | xargs -I{} git push origin --delete {}

# 3. Clean local branches tracking deleted remotes
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs -r git branch -D

# 4. List unmerged remote branches (may be abandoned — review manually)
git branch -r --no-merged origin/main | grep -v 'main\|HEAD'
```

Step 4 requires human judgment — unmerged branches may be:
- **Active work**: Leave them (check for recent commits)
- **Abandoned PRs**: Close the PR, then delete the branch
- **Superseded work**: Merged via a different branch/PR (like the `feature/issue-544-545` case) — safe to delete

### Cleanup: Onboarding an Existing Repo

When first applying this policy to a repo with existing stale branches:

```bash
# 1. See how many remote branches exist
git branch -r | wc -l

# 2. List merged branches (safe to bulk-delete)
git branch -r --merged origin/main | grep -v 'main\|HEAD'

# 3. List unmerged branches with last commit date
git for-each-ref --sort=-committerdate --format='%(committerdate:short) %(refname:short)' refs/remotes/origin | grep -v 'main\|HEAD'

# 4. Delete merged branches in bulk
git branch -r --merged origin/main | grep -v 'main\|HEAD' | \
  sed 's|origin/||' | xargs -I{} git push origin --delete {}

# 5. Review unmerged branches older than 30 days — likely abandoned
git for-each-ref --sort=-committerdate --format='%(committerdate:short) %(refname:short)' refs/remotes/origin | \
  grep -v 'main\|HEAD' | while read date ref; do
    if [[ "$date" < "$(date -v-30d +%Y-%m-%d)" ]]; then
      echo "STALE ($date): $ref"
    fi
  done
```

---

## Anti-Patterns (Never Do These)

| Anti-Pattern | Why It's Bad | Correct Approach |
|-------------|-------------|-----------------|
| Reuse one branch for multiple PRs | Can't revert individual changes; confusing history | One branch per PR |
| Bundle multiple issues in one commit | Can't bisect or blame individual issues | One issue per commit |
| `debug:` commits on main | Noise in history, debug code in production | Remove before PR; use proper logging |
| Implement then immediately revert | Wasted effort, cluttered history | Validate approach before coding |
| Config flip-flops | Shows undecided architecture | Decide with data before implementing |
| Force push to shared branches | Destroys other agents' work | Rebase and push normally |
| Skip CI with `--no-verify` | Breaks main | Fix the issue causing CI failure |
| Merge without rebasing | Creates unnecessary merge commits | Always rebase before merge |
| Long-lived feature branches | Diverge from main, painful merges | Keep branches under 24 hours |
| "Fix the fix" follow-up commits | Cluttered history | Amend on branch, or fix in same PR |

---

## Repository Setup Checklist

When onboarding a new project, configure these settings:

### GitHub Settings

- [ ] Branch protection on `main` (see configuration above)
- [ ] Enable merge queue
- [ ] Allow only squash merging (disable merge commit and rebase)
- [ ] Auto-delete head branches after merge
- [ ] Add CI workflow (`.github/workflows/ci.yml`)

### Local Settings

- [ ] Pre-commit hook for lint/format (via `.pre-commit-config.yaml` or local hook)
- [ ] `.gitignore` covers all generated files, secrets, IDE configs
- [ ] `CONTRIBUTING.md` or `CLAUDE.md` references this policy

### Project Configuration

- [ ] Lint config (ruff.toml, .eslintrc, etc.)
- [ ] Test config (pytest.ini, jest.config.js, etc.)
- [ ] Type check config (mypy.ini, tsconfig.json, etc.)

---

## Escalation Matrix

| Situation | Action |
|-----------|--------|
| Two agents need the same file | Serialize: Agent B waits for Agent A's PR to merge |
| Rebase conflict | Agent resolves conflict; if unsure, ask human |
| CI fails on PR | Agent fixes the issue; never skip CI |
| CI fails on main | Stop all merges. Hotfix immediately (Use Case 5) |
| Large refactor needed | Open RFC/spec issue first; don't start coding |
| Uncertain about approach | Enter Plan Mode; present plan for review before coding |
| PR too large (500+ lines) | Split into phased PRs (Use Case 6) |
| Dependency between issues | Implement sequentially, not in parallel |

---

*This policy is the single source of truth for git workflow across all agent-managed projects. All agents, commands, and workflows must comply. Updates to this policy require a PR.*
