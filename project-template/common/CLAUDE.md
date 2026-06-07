# CLAUDE.md

Claude-specific adapter for this project.

`AGENTS.md` is the **canonical** project instruction file, shared by Claude Code
and Codex. **Read `AGENTS.md` first.** This file carries only the minimum
load-bearing context Claude must always see — even if `AGENTS.md` is not
auto-loaded by the harness — plus Claude-only notes. It does **not** duplicate
AGENTS.md; when shared policy changes, update `AGENTS.md` and keep this thin.

## Project Overview

<!-- Mirror the one-liners from AGENTS.md so Claude always has them. -->

- Purpose:
- Users:
- Non-goals:

## Development Commands

See `AGENTS.md` → "Development Commands" for the full set. Quick pointers:

```bash
# Setup:
# Run:
# Test:
# Lint/format:
```

## Definition of Done

Work is not done when files merely exist. It must be:

- implemented and wired through its intended entrypoint
- exercised by automated or manual validation, with evidence (command output,
  artifact, or check result)
- passing the project's tests, lint, and format checks
- shipped or explicitly blocked by a documented stop gate

## Git / Ship Essentials

- Branch from latest `origin/main`: `{type}/issue-{N}-{slug}`.
- Conventional Commits; one logical change per branch = one PR.
- Never commit directly to `main`; never `--force`/`--no-verify` without approval.
- Rebase on `origin/main` before opening the PR; squash-merge; prune the branch.
- Prefer the shared helpers where present (e.g. `agent-git preflight|readiness|ship`).

## Validation Expectations

Before declaring work complete, run the project's checks and paste the result:

```bash
# e.g. ruff check . && ruff format --check . && pytest -q
```

## Claude Project Files

- `.claude/rules/project-rules.md` — Claude-specific local rules.
- `.claude/context/project-stack.md` — stack/runtime notes.
- `.claude/memory/runbooks.md` — known issue fixes (check BEFORE debugging from scratch).
- `.claude/commands/` — project-local slash commands (Claude-only).

Keep shared rules in `AGENTS.md`. Put Claude-only workflow notes here or in `.claude/`.
