# AGENTS.md

This file provides project-specific guidance for both Claude Code and OpenAI
Codex.

## Project Overview

- Purpose:
- Users:
- Non-goals:

## Development Commands

```bash
# Setup

# Run

# Test

# Lint/Format
```

## Architecture Constraints

- Required patterns:
- Forbidden changes:
- Data/security constraints:

## Delivery Rules

- Definition of done: agent-owned issue work defaults to shipped work. When
  gates pass, commit, open a PR, validate, squash merge, sync `main`, prune
  stale refs, delete the merged branch, and close or update the linked issue.
- Required test coverage:
- Rollback expectations:

## Git Process

Follow the standardized git process from `~/agents/docs/git-process.md`.
If this project has a local `docs/git-process.md`, use the local copy as the
project-specific adapter.

Required baseline:

- Run preflight before edits: inspect branch, dirty tree, remote freshness, open
  PR overlap, and project validation commands. Prefer
  `~/agents/bin/agent-git preflight` when available.
- Branch from latest `origin/main` using
  `<type>/issue-<number>-<slug>`.
- Keep one branch, one PR, and one logical change.
- Preserve unrelated user work. Do not reset, restore, delete, stash, or commit
  unrelated changes without explicit approval.
- Prove implementation through the intended entrypoint. Completion requires the
  change to be implemented, wired, exercised, observed, documented when
  operationally meaningful, and shipped or explicitly blocked.
- Run `~/agents/bin/agent-git readiness` before opening or merging an
  agent-owned PR when the helper is available.
- Stop before merge only for a documented stop gate: failing validation, unsafe
  approval requirement, branch protection requiring human review, blocking dirty
  user work, ambiguous scope, GitHub/network/credential failure, or explicit
  user request for draft/local-only work.
- Use squash merge by default, then sync `main`, prune, and delete the merged
  branch.

## Shared Agent Rules

- Read the actual files before assuming APIs, schemas, enum values, or
  component props.
- Keep changes scoped to the issue or task.
- Preserve user work and avoid destructive git or filesystem commands unless
  explicitly requested.
- If validation cannot run, state why and what remains unverified.
