# Project Setup

Every project that uses Claude Code benefits from a local configuration structure. This guide covers bootstrapping a new project with the right files and directories.

## Quick Bootstrap

Run the project bootstrap script from inside any git repository:

```bash
~/agents/claude-config/new-project-claude.sh /path/to/your/project
```

Or from within the project directory:

```bash
~/agents/claude-config/new-project-claude.sh
```

The script copies template files without overwriting anything that already exists.

!!! example "What the bootstrap creates"
    ```
    Created: CLAUDE.md
    Created: .claude/settings.json
    Created: .claude/commands/.gitkeep
    Created: .claude/context/project-stack.md
    Created: .claude/memory/.gitkeep
    Created: .claude/rules/project-rules.md
    Skipped: CLAUDE.md (already exists)
    ```
    Files that already exist are skipped, so the script is safe to re-run.

## What Gets Created

```
your-project/
├── CLAUDE.md                        # Project instructions for Claude Code
└── .claude/
    ├── settings.json                # Project-level permissions
    ├── commands/                    # Project-specific slash commands
    │   └── .gitkeep
    ├── context/
    │   └── project-stack.md         # Tech stack reference
    ├── memory/                      # Metrics, failures, patterns
    │   └── .gitkeep
    └── rules/
        └── project-rules.md         # Project-specific rules
```

After bootstrap, the orchestrate workflow also uses:

```
your-project/
├── .agents/
│   └── outputs/                     # Workflow artifacts land here
│       ├── archive/                 # Post-merge artifact storage
│       └── claude_checkpoints/
│           └── PERSISTENT_STATE.yaml
└── .worktrees/                      # Parallel execution (gitignored)
```

!!! tip "Gitignore recommendations"
    Add `.agents/outputs/` to `.gitignore` unless you want to track artifacts. Always gitignore `.worktrees/`.

## CLAUDE.md Template

The `CLAUDE.md` file at the project root is the primary instruction file Claude Code reads. Fill in each section:

```markdown
# CLAUDE.md

This file provides project-specific guidance to Claude Code.

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

- Definition of done:
- Required test coverage:
- Rollback expectations:
```

### What to Include

| Section | Content | Example |
|---------|---------|---------|
| **Purpose** | One-line project description | "Financial planning SaaS" |
| **Non-goals** | What Claude should never do | "Never create `src/` directory" |
| **Development Commands** | Exact commands for setup, run, test, lint | `ruff check . && pytest -q` |
| **Architecture Constraints** | Patterns that must be followed | "Layered: Router -> Service -> Repo" |
| **Forbidden changes** | Files/dirs that must not be modified | "Never push to production branch" |
| **Delivery Rules** | Definition of done, test requirements | "All tests pass, lint clean" |

!!! warning "Be specific about forbidden actions"
    Vague constraints like "be careful with the database" are ignored. Write "Never run DROP TABLE or DELETE without WHERE clause" instead.

## Project Stack Context

The `project-stack.md` file gives Claude Code quick context about your technology choices:

```markdown
# Project Stack

- Language/runtime: Python 3.12, Node 20
- Frameworks: FastAPI 0.115, React 19, Vite 6
- Storage: PostgreSQL 16, Redis 7
- Infra/deploy: Docker, AWS ECS
- External services: Stripe, SendGrid
```

## Project-Level Settings

The `.claude/settings.json` file controls permissions:

```json
{
  "permissions": {
    "allow": [
      "Bash(cd backend && ruff check .)",
      "Bash(cd backend && pytest -q)"
    ],
    "deny": []
  }
}
```

Add frequently-used commands to `allow` so Claude Code does not prompt for permission each time.

## Project-Specific Rules

Add concrete, actionable rules to `.claude/rules/project-rules.md`:

```markdown
# Project Rules

- All Python files use SQLAlchemy 2.0 style (Mapped[T], mapped_column)
- Pydantic models use ConfigDict(from_attributes=True)
- Repositories never call commit() -- services own the transaction
- Frontend components use named exports, not default exports
- Test database is SQLite in-memory -- avoid PostgreSQL-only syntax
```

## Project-Specific Commands

Create project-specific slash commands in `.claude/commands/`:

```markdown
---
description: Run the full test suite for this project
---

# Run Tests

```bash
cd backend && pytest -q --timeout=60
cd frontend && npm run test
```
```

Save as `.claude/commands/test.md` to enable `/test` within this project.

## Memory and Learning

The `.claude/memory/` directory accumulates over time:

| File | Created By | Purpose |
|------|-----------|---------|
| `patterns.md` | `/learn` | Auto-extracted failure patterns |
| `patterns-critical.md` | `/learn` | Top patterns (loaded every session) |
| `patterns-full.md` | `/learn` | Complete pattern database |
| `metrics.jsonl` | PROVE agent | One line per completed issue |
| `failures.jsonl` | PROVE agent | Failure details for learning |
| `pattern-events.jsonl` | `/learn --apply` | Pattern application tracking |

These files are committed to the project repository so patterns persist across machines.

## Global vs Project Override

Claude Code resolves configuration with project-first fallback:

```
1. .claude/agents/patch.md         (project override)
2. ~/.claude/agents/patch.md       (global default)
```

This applies to agents, commands, and rules. To customize an agent for a specific project, copy it from `~/.claude/agents/` into the project's `.claude/agents/` and modify it.

!!! note "Project overrides are rare"
    Most projects use the global agents unchanged. Only override when a project has unique architectural patterns that require different agent behavior.

!!! tip "CLAUDE.md best practices"
    - **Be specific, not aspirational** -- write "Never run DROP TABLE" instead of "Be careful with the database"
    - **Include exact commands** -- agents copy-paste your commands, so test them first
    - **Update after failures** -- every agent mistake that a CLAUDE.md entry would have prevented is a missed guardrail
