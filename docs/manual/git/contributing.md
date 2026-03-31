# Contributing Policy

This policy governs how multiple AI agents work in parallel on the same codebase without breaking each other's work or polluting the git history.

## Core Tenets

1. **Main stays green at all times** --- main is always deployable, always passes all checks
2. **One branch = one PR = one logical change** --- no branch reuse, no mega-commits
3. **Agents own files, not branches** --- parallel work is safe when agents touch different files
4. **Squash merge everything** --- clean linear history on main
5. **No direct commits to main** --- all changes go through PRs with status checks

## Parallel Agent Work

### File Ownership Model

Before agents start parallel work, the orchestrator assigns **non-overlapping file sets** per agent:

```
Agent A: src/auth/login.py, src/auth/oauth.py
Agent B: src/api/users.py, src/api/schemas.py
Agent C: tests/test_auth.py, tests/test_users.py
```

Two agents must never edit the same file simultaneously. If overlap exists, **serialize** --- Agent B waits for Agent A's PR to merge.

### Pre-Work Checks

Every agent must run these checks before starting:

```bash
# 1. Sync main
git fetch origin main

# 2. Branch from latest main
git checkout -b {branch} origin/main

# 3. Verify no conflicts with in-flight PRs
gh pr list --state open --json headRefName,files

# 4. Confirm no open PR touches the same files
```

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

Claude Code agents use the `--parallel` flag on `/orchestrate`, which automatically creates and manages worktrees at `.worktrees/issue-{N}/`.

### Wave Scheduling

Group independent issues into parallel waves; dependent issues run sequentially:

```
Wave 1 (parallel): #630 (injection scanner), #631 (PII scanner), #633 (audit log)
    -> No file overlap, all three run simultaneously

Wave 2 (serial): #632 (taint tracking)
    -> Depends on #630 and #631, starts after Wave 1 merges
```

### Rebase Before PR

After other agents merge, remaining agents must rebase on the new main before creating their PR:

```bash
git fetch origin && git rebase origin/main
```

This catches semantic conflicts early --- two changes that pass CI independently may fail when combined.

!!! note "Merge Queue"
    Enable GitHub's merge queue on protected repositories. The queue tests each PR against the latest main plus all PRs ahead in the queue, preventing the race condition where two independently-passing PRs conflict when merged together.

## The "Personal Probes Disaster"

This real-world failure demonstrates why branch reuse is forbidden.

### What Happened

One branch (`feature/personal-probes`) was reused for 7 consecutive PRs over 2 hours:

| PR | Type | Actual Content |
|----|------|---------------|
| #396 | feat | Add personal probes |
| #397 | fix | Cache-busting for static assets |
| #398 | fix | Skip HSTS on LAN IPs |
| #399 | fix | Handle missing getUserMedia |
| #400 | fix | Make save_memory proactive |
| #401 | perf | Skip grid context scoring |
| #402 | fix | STT digit filter |

**Problems**: Could not revert one change without analyzing all seven. History showed 7 merges from the same branch. Impossible to determine which diff belonged to which PR.

### What Should Have Happened

```
7 independent branches, 7 independent PRs
    -> Each independently revertable
    -> Each with clear, isolated diffs
    -> No file overlap = all 7 run in parallel
    -> Total time: ~30 minutes (parallel) vs ~2 hours (serial reuse)
```

!!! warning "Branch Reuse Is the Root Cause"
    Branch reuse makes git history unusable. It prevents independent reverts, obscures which changes belong to which logical unit, and blocks parallel execution. One branch = one PR = one logical change.

## Escalation Matrix

| Situation | Action |
|-----------|--------|
| Two agents need the same file | Serialize: Agent B waits for Agent A's PR to merge |
| Rebase conflict | Agent resolves conflict; if unsure, ask human |
| CI fails on PR | Agent fixes the issue; never skip CI |
| CI fails on main | Stop all merges. Hotfix immediately |
| Large refactor needed | Open RFC/spec issue first; do not start coding |
| PR too large (500+ lines) | Split into phased PRs |
| Dependency between issues | Implement sequentially, not in parallel |

## Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Approach |
|-------------|-------------|-----------------|
| Reuse one branch for multiple PRs | Cannot revert individual changes | One branch per PR |
| Bundle multiple issues in one commit | Cannot bisect or blame individual issues | One issue per commit |
| `debug:` commits on main | Noise in history, debug code in production | Remove before PR |
| Implement then immediately revert | Wasted effort, cluttered history | Validate approach before coding |
| Force push to shared branches | Destroys other agents' work | Rebase and push normally |
| Long-lived feature branches | Diverge from main, painful merges | Keep branches under 24 hours |
| Config flip-flops | Shows undecided architecture | Decide with data before implementing |

## Repository Setup Checklist

When onboarding a new project:

- [ ] Branch protection on `main` (require status checks, linear history)
- [ ] Enable merge queue (squash merge, required checks)
- [ ] Allow only squash merging (disable merge commit and rebase options)
- [ ] Auto-delete head branches after merge
- [ ] Add CI workflow (`.github/workflows/ci.yml`)
- [ ] Add `.gitignore` covering generated files, secrets, IDE configs
- [ ] Create `CLAUDE.md` referencing this policy
