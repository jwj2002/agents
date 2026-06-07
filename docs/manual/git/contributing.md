# Contributing Policy

Canonical source: `docs/git-process.md`.

This page records the reason for the policy, not a second copy of every rule:
multiple agents must be able to work in the same repository without breaking
each other's work, losing user changes, or polluting history.

Core tenets:

1. `main` stays green.
2. One branch equals one PR equals one logical change.
3. Agent-owned issue work defaults to shipped work when gates pass.
4. Same-file parallel work serializes.
5. Implementation must be wired and exercised through its intended entrypoint.
6. Squash merge is the default.

For branch naming, dirty-tree protocol, ship mode, stop gates, implementation
gates, labels, PR requirements, cleanup, and parallel worktrees, use
`docs/git-process.md`.
