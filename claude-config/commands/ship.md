---
description: Ship a green diff — commit → rebase → PR → review → merge → verify → prune → docs
argument-hint: [--auto]
---

# Ship Command

**Role**: One command from green diff to shipped. Composes the PR workflow with
guards that prevent dropped commits, red CI, and broken main.

---

## Usage

```bash
/ship           # Full sequence; pauses before merge for confirmation (kill switch)
/ship --auto    # Same guards; skips confirmation prompt at step 7 (merge tail runs unattended)
```

`--auto` is safe only because every prior guard must already have passed. The
`gship` shell alias is the ergonomic form: `alias gship='claude /ship --auto'`.

---

## Process

### Step 1 — Branch Guard

Assert the working tree is not on `main` or `master`. Fail fast:

```bash
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "BLOCKED: /ship cannot run on main. Create a feature branch first."
  exit 1
fi
echo "Branch: $BRANCH"
```

Assert one logical change (one issue, one PR). If the branch already has a merged
or closed PR, stop and ask the user whether to open a new branch.

### Step 2 — Stash, Stage + Commit

Stash any unrelated uncommitted changes so they cannot interfere with the rebase:

```bash
# Stash unrelated uncommitted changes (if any unstaged files exist beyond your intent)
git stash --include-untracked
# (restore with: git stash pop  — happens automatically after step 3)
```

Prompt for a conventional commit message (`type(scope): description`). Stage
all relevant files and commit. The pre-commit hook fires automatically
(lint + format + version bump):

```bash
git add -p            # or: git add <specific files>
git commit            # hook: ruff fix/format, relationship_id gate, version bump
```

If the commit is rejected by the pre-commit hook, surface the hook output and
STOP — the hook caught a real issue.

### Step 3 — Rebase

```bash
git fetch origin
git rebase origin/main
```

On conflict:
- Print conflicting files.
- `git rebase --abort`.
- `git stash pop` (restore the stash from step 2).
- STOP and report: "REBASE CONFLICT — resolve manually, then re-run /ship."

On success, restore the stash:

```bash
git stash pop   # restores any unrelated uncommitted changes from step 2
```

### Step 4 — Push

```bash
git push --force-with-lease origin HEAD
```

Never `--force`. `--force-with-lease` is safe after a clean rebase — it rejects
the push if the remote has diverged beyond our rebase base.

### Step 5 — PR + Review Gates

If no open PR exists for this branch, create one per `pr.md §Create PR`. Then:

1. **Fresh-context review**: Run `pr-fresh-reviewer` per `pr.md §Pre-PR Fresh-Context Review`.
   - **Gate**: CRITICAL findings → STOP. Do NOT proceed until fixed.
   - WARNING findings: include in PR body; continue.

2. **COMPLEX-signal check**: Run the signal detection block per `pr.md §Pre-merge Codex review for COMPLEX changes`.
   - If COMPLEX signals fire, recommend `/codex:adversarial-review` before proceeding.
   - This is advisory — the user decides whether to run it. `/ship` pauses and
     prompts: "COMPLEX signals detected. Run /codex:adversarial-review? [y/N to skip]"

### Step 6 — CI Watch

```bash
gh pr checks --watch
```

**Gate**: Any red or pending check → STOP. Print the failing check URL. Do NOT
proceed to merge until all checks are green.

### Step 7 — HEAD Parity Check

This guard prevents the squash-drops-commits caveat (see `feedback_squash_merge_drops_commits.md`):
a PR created before the last push can squash-merge an older snapshot, silently
dropping commits.

```bash
PR_NUMBER=$(gh pr view --json number -q .number)
PR_HEAD=$(gh pr view --json headRefOid -q .headRefOid)
LOCAL_HEAD=$(git rev-parse HEAD)

if [ "$PR_HEAD" != "$LOCAL_HEAD" ]; then
  echo "HEAD MISMATCH: PR HEAD $PR_HEAD != local HEAD $LOCAL_HEAD"
  echo "Pushing to sync and re-checking CI..."
  git push --force-with-lease origin HEAD
  gh pr checks --watch
  PR_HEAD=$(gh pr view --json headRefOid -q .headRefOid)
  LOCAL_HEAD=$(git rev-parse HEAD)
  if [ "$PR_HEAD" != "$LOCAL_HEAD" ]; then
    echo "BLOCKED: PR HEAD still does not match local HEAD after push. Investigate manually."
    exit 1
  fi
fi
echo "HEAD parity confirmed: $LOCAL_HEAD"
```

**Kill switch** (plain `/ship` without `--auto`): after parity is confirmed,
pause and require explicit confirmation before the irreversible merge:

```
Ready to merge PR #N:
  Branch : {branch}
  PR HEAD: {sha} (matches local)
  CI     : all green

Proceed with squash-merge? [y/N]
```

Only continue on explicit `y`. Any other input aborts. With `--auto`, skip
this prompt — the guards above are the contract that makes auto safe.

### Step 8 — Merge

```bash
gh pr merge $PR_NUMBER --squash --delete-branch
```

`--delete-branch` is idempotent when the repo has auto-delete enabled. Always
squash — never standard merge or rebase merge.

### Step 9 — Post-Merge Verification

```bash
git checkout main && git pull origin main
ruff check . && ruff format --check .
pytest tests/ --timeout=60
# Frontend (if applicable): cd frontend && npm run lint && npm run build
```

**No `-x` flag.** Running with `-x` stops at the first failure and hides
downstream regressions — a full suite run is mandatory here.

Full checklist: `~/.claude/rules/post-merge-verification.md`

**If any check fails**: STOP immediately. Do NOT prune branches. Report:

```
POST-MERGE FAILURE on main — do NOT prune.
Create a hotfix: git checkout -b fix/hotfix-<description> origin/main
```

Do not proceed to step 10 until main is green.

### Step 10 — Prune

```bash
git fetch --prune origin

# Safe-delete the merged feature branch
git branch -d $BRANCH

# Clean any other local branches whose remotes are gone
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs -r git branch -D
```

### Step 11 — Docs

Auto-derive a changelog entry from the squash commit message. Conventional
commit format maps to categories:

| Prefix | Changelog category |
|--------|--------------------|
| `feat` | Added |
| `fix`  | Fixed |
| `refactor` / `perf` | Changed |
| `chore` / `docs` | Maintenance |

Check whether the PR touched files listed in any `docs-targets:` frontmatter
annotation on the branch's MAP-PLAN artifact (if present). If so, prompt:

```
PR #N touched documented surfaces. Update README/CLAUDE.md? [y/N]
```

This step is best-effort — a failure here does not block step 12.

### Step 12 — Telemetry + Emit

```python
import sys
sys.path.insert(0, '$HOME/.claude/hooks')
from state_manager import record_metrics
from pathlib import Path
record_metrics(Path('.'), issue_number, 'PASS', complexity, stack, ['ship'])
```

Derive `issue_number` from the branch name (`issue-{N}` pattern), `complexity`
and `stack` from the MAP-PLAN artifact if available, else infer from diff size.

Print:

```
Shipped  PR #N  {pr_url}
```

---

## Guard Summary

| Guard | When it fires | Blocks |
|-------|---------------|--------|
| Branch check | Step 1 | Always |
| Pre-commit hook | Step 2 | Always |
| Rebase conflict | Step 3 | Always |
| CRITICAL review | Step 5 | Always |
| Red CI | Step 6 | Always |
| HEAD parity | Step 7 | Always |
| Kill switch (`y/N`) | Step 7 | Plain `/ship` only |
| Post-merge test failure | Step 9 | Always (blocks prune) |

`--auto` bypasses only the kill switch (the `y/N` prompt). All other guards
fire regardless.

---

## Shell Alias

Add to `~/.zshrc` (after the existing Claude workflow aliases):

```bash
# /ship auto-tail alias: commit→merge→squash→prune without confirmation prompts
alias gship='claude /ship --auto'
```

---

## Related Commands

- `/pr` — Create or review a PR without merging
- `/orchestrate` — Generate a full MAP→PATCH→PROVE implementation plan
- `/quick` — Ad-hoc task without orchestration overhead
- `/codex:adversarial-review` — Second-model adversarial review for risky diffs
