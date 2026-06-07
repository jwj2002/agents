# Project Git Process

This project follows the standardized git process from:

```text
~/agents/docs/git-process.md
```

Use this local file for project-specific overrides only. Shared behavior belongs
in the canonical `~/agents` document so Claude, Codex, and future agents stay in
sync.

Baseline:

- Run preflight before edits.
- Branch from latest `origin/main`.
- Keep one branch, one PR, and one logical change.
- Preserve unrelated user work.
- Prove changes are implemented, wired, exercised, observed, documented when
  operationally meaningful, and shipped or explicitly blocked.
- Default to shipping agent-owned issues when gates pass.
- Squash merge, sync `main`, prune stale refs, and delete merged branches.
