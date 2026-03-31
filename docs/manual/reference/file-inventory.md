# File Inventory

Complete listing of all files in the `~/agents/claude-config/` repository, organized by category. All paths are relative to `~/agents/claude-config/` and symlinked to `~/.claude/` via `install.sh`.

## Agents (11 files)

Symlinked to `~/.claude/agents/`. Agent definitions are markdown files that define role, constraints, input requirements, output format, and verification gates.

| File | Size | Purpose |
|------|------|---------|
| `_base.md` | 10.3 KB | Base agent inherited by all others: pre-flight, artifact naming, validation, AGENT_RETURN directive |
| `map.md` | 3.6 KB | Investigator for COMPLEX issues (read-only, phase 1) |
| `map-plan.md` | 6.5 KB | Combined investigator + architect for TRIVIAL/SIMPLE issues (read-only, phase 1+2) |
| `plan.md` | 4.1 KB | Architect for COMPLEX issues (read-only, phase 2) |
| `contract.md` | 3.3 KB | Interface designer for fullstack issues (read-only, phase 2.5) |
| `plan-checker.md` | 3.1 KB | Plan validator (read-only, phase 2.8) |
| `patch.md` | 5.8 KB | Implementer --- the only agent that modifies code (phase 3) |
| `prove.md` | 7.3 KB | Reviewer and outcome recorder (phase 4) |
| `test-planner.md` | 7.9 KB | Test architect for `--with-tests` flag (optional, phase 1.5) |
| `spec-reviewer.md` | 6.1 KB | Spec analyst and GitHub issue creator (pre-pipeline) |
| `code-reviewer.md` | 1.3 KB | Proactive lightweight review (runs on Haiku model) |

## Commands (15 files)

Symlinked to `~/.claude/commands/`. Slash commands invokable by the user during a session.

| File | Size | Purpose |
|------|------|---------|
| `orchestrate.md` | 18.4 KB | Full agent pipeline for GitHub issues (`/orchestrate`) |
| `learn.md` | 8.5 KB | Pattern extraction from failures (`/learn`) |
| `metrics.md` | 15.8 KB | Performance dashboard (`/metrics`) |
| `pr.md` | 3.1 KB | PR creation with checklist (`/pr`) |
| `spec-review.md` | 3.4 KB | Spec analysis and issue creation (`/spec-review`) |
| `spec-draft.md` | 7.5 KB | Interactive specification creation (`/spec-draft`) |
| `feature.md` | 2.8 KB | Feature request issue creation (`/feature`) |
| `feature-from-spec.md` | 2.7 KB | Create issues from spec gaps (`/feature-from-spec`) |
| `bug.md` | 2.3 KB | Bug report with investigation (`/bug`) |
| `test-plan.md` | 2.5 KB | Pre-implementation test planning (`/test-plan`) |
| `scaffold-project.md` | 22.4 KB | Full FastAPI project scaffolding (`/scaffold-project`) |
| `scaffold-module.md` | 7.5 KB | Domain module addition (`/scaffold-module`) |
| `quick.md` | 2.0 KB | Ad-hoc fix without orchestrate (`/quick`) |
| `review.md` | 0.4 KB | Code review of staged changes (`/review`) |
| `frontend-design.md` | --- | Frontend design plugin integration (`/frontend-design`) |

## Rules (7 files)

Symlinked to `~/.claude/rules/`. Conditional and always-loaded instruction files.

| File | Size | Trigger | Purpose |
|------|------|---------|---------|
| `core-patterns.md` | 0.7 KB | Always | Top 3 failure patterns (89% coverage) |
| `git-workflow.md` | 3.2 KB | Always | Branch, commit, and PR conventions |
| `implementation-routing.md` | 2.1 KB | Always | Plan mode vs orchestrate decision matrix |
| `github-accounts.md` | 1.0 KB | Always | Multi-account GitHub configuration |
| `fastapi-layered-pattern.md` | 23.6 KB | `**/backend/**`, `**/api/**`, `**/services/**` | Full layered architecture reference |
| `orchestrate-workflow.md` | 16.7 KB | `.agents/**/*.md` | Agent efficiency, artifact naming, CONTRACT rules |
| `spec-review-workflow.md` | 12.0 KB | `**/specs/**`, `**/.agents/**` | Spec finalization gate and issue creation |

## Hooks (6 files)

Symlinked to `~/.claude/hooks/`. Python scripts attached to Claude Code lifecycle events.

| File | Size | Event | Purpose |
|------|------|-------|---------|
| `sessionstart_restore_state.py` | 4.8 KB | SessionStart | Restore PERSISTENT_STATE and critical patterns (~500 tokens) |
| `precompact_checkpoint.py` | 7.5 KB | PreCompact | Extract state from transcript, update YAML, auto-clean old files |
| `verify_completion.py` | 3.3 KB | Stop | Anti-rationalization: block if uncommitted changes or TODOs exist |
| `notify_completion.py` | 3.5 KB | Stop | macOS Notification Center alert with iPhone relay via Handoff |
| `state_manager.py` | 4.5 KB | (shared module) | Centralized PERSISTENT_STATE.yaml read/write operations |
| `worktree_manager.py` | 6.5 KB | (shared module) | Git worktree lifecycle for `--parallel` flag |

## Skills (3 directories)

Symlinked to `~/.claude/skills/`. Multi-step workflow definitions with reference documentation.

| Directory | Files | Purpose |
|-----------|-------|---------|
| `orchestrate/` | SKILL.md (2.4 KB), ORCHESTRATE_REFERENCE.md (7.5 KB) | Multi-agent pipeline execution |
| `test-plan/` | SKILL.md (2.1 KB) | Test matrix generation with edge cases |
| `spec-review/` | SKILL.md (1.2 KB) | Spec analysis and gap identification |

## Templates (2 entries)

Not symlinked --- referenced by orchestrate and other commands directly.

| File | Size | Purpose |
|------|------|---------|
| `agent-prompt.md` | 2.5 KB | Shared prompt template with variable substitution for all agents |
| `github-actions/` | --- | GitHub Actions workflow templates (Copilot review setup) |

## Config Files

| File | Size | Purpose |
|------|------|---------|
| `settings.json` | 2.1 KB | Global settings: hooks, MCP servers, permissions, plugins (symlinked) |
| `statusline.py` | 1.2 KB | Custom ANSI status bar: hostname, user, date, context usage (symlinked) |
| `install.sh` | 11.5 KB | Idempotent symlink installer (macOS/WSL/Linux aware) |
| `project-template/` | --- | Starter `CLAUDE.md` and `.claude/rules/` for new projects |

## Per-Project Files (Not in Repo)

These files live in each project repository, not in `~/agents/claude-config/`:

```
~/projects/<project>/
  CLAUDE.md                              # Project-specific agent instructions
  .claude/
    settings.json                        # Project permissions
    memory/
      patterns.md                        # Project-specific learned patterns
      patterns-full.md                   # Extended patterns (~660 lines)
      metrics.jsonl                      # Issue outcome tracking
      failures.jsonl                     # Failure details
      pattern-events.jsonl               # /learn --apply tracking
  .agents/
    outputs/
      map-plan-{issue}-{mmddyy}.md      # Agent artifacts
      patch-{issue}-{mmddyy}.md
      prove-{issue}-{mmddyy}.md
      archive/                           # Post-merge artifact archive
      claude_checkpoints/
        PERSISTENT_STATE.yaml            # Workflow state
  .worktrees/                            # Worktree isolation (gitignored)
    issue-{N}/                           # Full repo copy on own branch
```

!!! note "Machine-Local Files"
    `~/.claude/settings.local.json` and `~/.claude/memory/` are machine-specific and not symlinked from the repo. Each machine configures its own MCP server paths and maintains its own global pattern files.
