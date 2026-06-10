---
description: "Procedure for promoting project-local memory lessons to global rules"
paths: ["**/memory/**", "**/.agents/**"]
---

# Promoting project memory to global rules

> Moved out of CLAUDE.md (#384) to keep the always-loaded prompt under budget.
> Loads on demand — read when a `feedback-*.md` lesson looks cross-project.

When a project-memory file under
`~/.claude/projects/<project>/memory/feedback-*.md` captures a lesson
that's **generally applicable to other projects** (not specific to
that project's domain), promote it to a global rule so every project
inherits it.

**Why this exists.** Project memory files are project-local — working
in `safe174th` you won't see `buddy`'s feedback files. Without
promotion, every project relearns the same lessons. The 2026-06-03
Workspace V1 R1 incident documented this gap: 17 of 21 blockers were
preventable by existing project-local feedback that had never been
promoted.

**Procedure:**

1. **Decide it's promotable.** Cross-project relevance test: would a
   teammate working on an unrelated project benefit from this rule
   without seeing the originating incident? If yes, promote.
2. **Write the new rule** in `~/agents/claude-config/rules/<name>.md`
   with appropriate `paths:` frontmatter for auto-load.
3. **Keep the project-memory file as back-reference.** Add a
   `Companion: ~/.claude/rules/<name>.md` line so future readers
   trace from incident → general rule.
4. **Commit + PR + merge to `~/agents`** following the standard git
   workflow (jwj2002 account per `github-accounts.md`).
5. **Run `~/agents/claude-config/install.sh`** to refresh symlinks
   (no-op if the rule directory was already symlinked; only catches
   first-time symlink + missing-target cases).
6. **For jbox06 (if applicable):** `ssh jbox06 'cd ~/agents && git
   pull --ff-only && ./claude-config/install.sh'`. Without this step,
   VitalAILabs app sessions won't see the new rule.

**What counts as "generally applicable":**
- Workflow discipline (review gates, self-checks, sequencing).
- Cross-stack mistakes (enum collisions, schema drift, fence-post
  errors in distributed systems).
- Tool quirks that bite in any project (`codex` CLI, `gh` CLI, `git`
  edge cases).

**What stays project-local:**
- Domain-specific patterns (e.g., a buddy-only entity-grid lesson).
- Architectural choices recorded for context (resume docs,
  pillar-status logs).
- Operational incident notes specific to that project's infra.
