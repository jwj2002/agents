# Git Workflow

Canonical source: `docs/git-process.md`.

This manual page intentionally avoids restating the full process. The canonical
doc defines branch rules, dirty-tree handling, default ship mode, stop gates,
implementation gates, validation, merge, cleanup, labels, and parallel work.

Short version:

- branch from latest `origin/main`
- keep one branch, one PR, one logical change
- preserve unrelated user work
- prove implementation is wired and exercised
- squash merge when gates pass
- sync `main`, prune, and delete merged branches

If this page conflicts with `docs/git-process.md`, the canonical doc wins.
