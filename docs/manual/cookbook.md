# Cookbook — Common Workflows

Recipes for the work you actually do day-to-day. Each scenario is a one-liner of intent, the commands, and what you'll see. Links to the deeper reference pages live at the bottom of each section.

---

## Daily work

### Fix a typo or one-line config tweak

You have an obvious change. No issue, no branch ceremony, just do it.

```bash
/quick "fix typo in README intro paragraph"
```

What happens: Claude reads the file, makes the change, runs whatever lint applies. No artifacts written, no agent dispatches. You commit and push manually if you want.

### Implement a small feature (1–3 files)

You have a GitHub issue. Run orchestrate; it'll classify as SIMPLE, run MAP-PLAN → PATCH → PROVE, and leave you with a clean branch ready to PR.

```bash
gh issue view 184                    # confirm the issue is what you expect
/orchestrate 184
```

What happens:
1. Branch `feature/issue-184-...` created off `origin/main`
2. MAP-PLAN agent reads the codebase, writes plan to `.agents/outputs/map-plan-184-MMDDYY.md`
3. PATCH agent implements per the plan
4. PROVE agent runs lint/tests, validates acceptance criteria
5. You see "PROVE status: PASS ✅ — Next: /pr 184"

### Implement a bigger feature (6+ files, migrations, cross-cutting)

Same command — orchestrate auto-classifies as COMPLEX and runs the longer pipeline (MAP, PLAN, PLAN-CHECK separately).

```bash
/orchestrate 207
/orchestrate 207 --discuss           # if requirements feel ambiguous; adds a DISCUSS phase first
/orchestrate 207 --with-tests        # if it's calculation/formula heavy
```

For COMPLEX work, `/pr` will prompt you to run `/codex:adversarial-review` before squash-merging. Take the prompt seriously on migrations or auth changes.

### Create the PR

```bash
/pr
```

What happens:
1. Spawns a fresh-context reviewer subagent (no inheritance from your implementation discussion)
2. If the diff matches COMPLEX-tier signals, prompts you to run `/codex:adversarial-review` first
3. `gh pr create` with a generated title/body
4. CI runs `validate.yml` checks (settings.json valid, install.sh syntax, hook paths resolve, sync.py builds, pattern slug invariant)
5. You squash-merge when CI is green

### Pick up where you left off

You stopped mid-orchestrate. New session, can't remember what phase you were on.

```bash
/orchestrate 184 --resume
```

What happens: orchestrate reads `PERSISTENT_STATE.yaml` (written by the PreCompact hook), figures out the last completed phase, and resumes from the next one. SessionStart hook already restored the active-work context for you.

---

## When things get interesting

### Work on multiple machines (laptop + desktop, etc.)

The repo is the source of truth. Everything else is derived state.

```bash
# On the new machine, one time:
git clone https://github.com/jwj2002/agents.git ~/agents
cd ~/agents/claude-config && ./install.sh

# Day-to-day, on either machine:
git pull                              # post-merge hook auto-rebuilds knowledge.db
```

Pattern IDs use slug format (`pat-<filename-stem>`) so two machines authoring different patterns can't collide. Two machines authoring the same pattern get a real git merge conflict — the right outcome.

### Run multiple issues in parallel

You have two independent issues to ship today.

```bash
# Tab 1
/orchestrate 42 --parallel            # creates worktree at .worktrees/issue-42/

# Tab 2 (separate terminal)
/orchestrate 57 --parallel            # creates worktree at .worktrees/issue-57/
```

Worktrees isolate each branch — both run concurrently without stepping on each other's git state.

### Get a second-opinion review on risky changes

You've finished implementation. Diff includes auth, migrations, or a 50-file cross-cutting refactor.

```bash
/codex:adversarial-review --wait      # foreground, see results inline
/codex:adversarial-review --background # async, check with /codex:status
```

Codex reads the diff fresh (different model, different blind spots) and reports BLOCKING / NON-BLOCKING / CLEAN findings. `/pr` will prompt you to run this for COMPLEX-tier diffs automatically.

### Capture a thought without losing focus

Mid-implementation, an idea hits you. You don't want to context-switch.

```bash
/capture "investigate whether rate-limit middleware should move to a decorator"
```

Goes straight to your inbox. Doesn't interrupt the current session. Triage later with `/inbox`.

### See where everything stands across projects

```bash
/dashboard                            # cross-project overview
/dashboard <project>                  # single-project deep view
```

Pulls live state from git/gh and the knowledge graph: open PRs, blockers, focus item, stale prompts, recent activity.

### Get a focused review without invoking Codex

Before committing, you want a self-review pass.

```bash
/review                               # pre-commit code review
/deep-review                          # comprehensive critical review
```

---

## When something breaks

### MCP servers say "Failed to connect" at session start

`claude mcp list` shows context7 / apple-mcp / playwright as failed. Almost always cold-cache npx timeout, not a real package break.

```bash
~/agents/claude-config/install.sh     # Phase 2.6 warms the npm cache for npx-based MCP servers
claude mcp list                       # all 5 should now show ✓ Connected
```

If it persists after a warm-up, run the failing command manually to see the real error:

```bash
npx -y @upstash/context7-mcp@latest </dev/null
```

### A hook breaks every tool call ("No such file or directory")

You see `PreToolUse:Bash hook error: ... can't open file '/Users/...'` on every command. A hook in `settings.json` is pointing at a script that doesn't exist.

```bash
# Find which hook is broken (run from a terminal, not from the bricked Claude session)
python3 ~/agents/claude-config/scripts/validate-hooks.py

# Edit ~/.claude/settings.json (which symlinks to claude-config/settings.json)
# Remove the offending PreToolUse entry, save
# Restart Claude Code
```

The CI workflow (`validate.yml`) catches this on PR open going forward, but if a bad config slipped through pre-CI, this is the recovery.

### Pattern ID collision after a sync

Adding a new pattern, `sync.py build` fails with `Duplicate pattern IDs detected, refusing to build: ['pat-foo']`.

```bash
ls knowledge/patterns/ | grep foo     # find the two files
# Decide: are they actually the same pattern? Merge content. Or rename one.
# Slug = filename, so renaming the file changes the ID.
```

The duplicate-ID guard in `sync.py` is structural; the slug invariant means this only happens if you copied a file or made a manual editing mistake.

### Session start times out or hangs

A SessionStart hook is taking too long. Most common: `load_learning_rules.py` reading from a vault path that doesn't exist on this machine.

```bash
# Comment out the slow hook in ~/.claude/settings.json temporarily, restart
# Then debug what's wrong with the hook's data dependency
~/.claude/hooks.log                  # check timestamps + errors
```

---

## One-time setup

### Brand-new machine

```bash
# Prerequisites: git, python3, node, gh CLI, claude CLI
git clone https://github.com/jwj2002/agents.git ~/agents
cd ~/agents/claude-config && ./install.sh
# Authenticate gh: gh auth login
# Start using: claude
```

`install.sh` handles symlinks, dependencies, MCP server registration, npm cache warm-up, hook validation, and creates a default Obsidian vault.

### New project that should use Claude Code orchestrate

In an existing project (a clone of one of your repos), tell Claude Code where to find its rules:

```bash
cd ~/projects/<repo>
~/agents/claude-config/new-project-claude.sh
# Edit the generated CLAUDE.md to add project-specific patterns
```

The `CLAUDE.md` you create extends the global one. Project-specific agent overrides go in `<repo>/.claude/agents/`.

### Build the manual locally

```bash
pipx install mkdocs-material          # or: brew install pipx && pipx install mkdocs-material
cd ~/agents && mkdocs serve -a 127.0.0.1:8001
```

---

## Patterns to reach for

Three principles handle most decisions:

| Situation | Reach for |
|---|---|
| Trivial change (typo, single line) | `/quick`, no issue, no branch ceremony |
| Real work with a known shape | `/orchestrate <N>`, let it classify |
| Risky work or repeated failure | `/codex:adversarial-review` for review, `/codex:rescue` for retry |
| Mid-flight idea that doesn't belong here | `/capture`, triage later |
| "Where am I across all this?" | `/dashboard` |

---

## Where to look next

When the cookbook isn't enough, the deeper reference pages explain the why:

- **Why orchestrate works the way it does**: [The Pipeline](workflow/orchestrate.md)
- **Why hooks fire when they do**: [Hook Lifecycle](hooks/lifecycle.md)
- **Why patterns use slug IDs**: [Self-Learning Loop](learning/self-learning-loop.md)
- **All the visual flows**: [Architecture Diagrams](reference/architecture-diagrams.md)
- **What every file does**: [File Inventory](reference/file-inventory.md)
