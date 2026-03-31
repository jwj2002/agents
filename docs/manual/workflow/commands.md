# Command Reference

All slash commands are defined in `claude-config/commands/` and available globally via symlink. Project-specific commands can be added in `.claude/commands/` within any project.

## Workflow Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/orchestrate` | `/orchestrate 184 [flags]` | Full agent pipeline for a GitHub issue |
| `/quick` | `/quick Fix typo in README` | Direct execution for small, scoped tasks |
| `/pr` | `/pr [number] [--merge]` | PR creation, review, and merge workflow |
| `/review` | `/review` | Pre-commit code review of staged changes |

### /orchestrate

Runs the MAP - PLAN - PATCH - PROVE pipeline for a GitHub issue.

```bash
/orchestrate 184                      # Standard
/orchestrate 184 --with-tests         # Add TEST-PLANNER phase
/orchestrate 184 --resume             # Resume interrupted workflow
/orchestrate 184 --parallel           # Isolated worktree execution
```

See [Orchestrate Workflow](orchestrate.md) for full documentation.

### /quick

Executes small tasks directly without sub-agents, artifacts, or GitHub issues.

```bash
/quick Fix typo in README
/quick Add missing import in accounts/services.py
/quick Update env example with new variable
```

See [Quick Mode](quick-mode.md) for decision criteria and process.

### /pr

Creates, reviews, or merges pull requests with a pre-flight checklist.

```bash
/pr                   # Create PR from current branch
/pr 123               # Review existing PR #123
/pr --merge 123       # Merge PR #123 after checks pass
```

The PR workflow includes:

- Branch verification (must not be on main)
- Backend/frontend lint and test gates
- Auto-generated PR body with scope, verification, and test plan
- Post-merge cleanup (branch deletion, artifact archival, worktree removal)

### /review

Runs a lightweight code review on staged changes using the Haiku model.

```bash
/review
```

## Issue Management Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/feature` | `/feature "Add payment module"` | Create feature request issue |
| `/bug` | `/bug "Login fails on Safari"` | Create bug report with investigation |
| `/spec-draft` | `/spec-draft payments` | Interactive specification creation |
| `/spec-review` | `/spec-review specs/payments.md` | Analyze spec vs codebase |
| `/feature-from-spec` | `/feature-from-spec specs/payments.md` | Create issues from spec gaps |

### /feature

Creates a GitHub feature issue with automatic scope classification and labels.

```bash
/feature "Add payment processing module"
```

Runs `gh issue create` with a structured template including scope, stack detection, and complexity estimate.

### /bug

Creates a GitHub bug report with context investigation.

```bash
/bug "Login fails on Safari with 403 error"
```

Investigates the codebase for relevant context before creating the issue.

### /spec-draft

Interactive multi-step specification creation with codebase discovery.

```bash
/spec-draft payments
```

Guides through requirements gathering, discovers existing code patterns, and flags risks.

### /spec-review

Analyzes a specification against the current codebase to find gaps and inconsistencies.

```bash
/spec-review specs/payments.md
/spec-review specs/payments.md --create-issues
```

With `--create-issues`, automatically creates GitHub issues for each gap found.

### /feature-from-spec

Creates GitHub issues from specification analysis. Used by the spec-reviewer agent.

```bash
/feature-from-spec specs/payments.md
```

## Testing Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/test-plan` | `/test-plan 184` | Pre-implementation test planning |

### /test-plan

Runs the TEST-PLANNER agent to generate a test matrix with edge cases and priority levels.

```bash
/test-plan 184
/test-plan specs/payments.md
```

Generates a test plan artifact with test signatures that the PATCH agent follows during implementation.

## Learning and Metrics Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/learn` | `/learn [flags]` | Extract patterns from failures |
| `/metrics` | `/metrics [--week] [--json]` | Performance dashboard |

### /learn

Analyzes `metrics.jsonl` and `failures.jsonl` to extract failure patterns and update prevention knowledge.

```bash
/learn                     # Analyze current project
/learn --since 2026-01-01  # From specific date
/learn --cross-project     # Aggregate across all projects
/learn --validate          # Compare before/after success rates
/learn --apply             # Write prevention into agent files
/learn --apply --dry-run   # Preview changes without writing
```

| Flag | Purpose |
|------|---------|
| `--since DATE` | Analyze failures from a specific date |
| `--cross-project` | Aggregate patterns across all projects |
| `--validate` | Compare success rates before/after pattern addition |
| `--apply` | Write prevention checklists into agent .md files |
| `--dry-run` | Preview without modifying files |

### /metrics

Displays an agent performance dashboard with success rates and trends.

```bash
/metrics              # Current week
/metrics --week       # Last 7 days
/metrics --month      # Last 30 days
/metrics --json       # Machine-readable output
```

## Scaffolding Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/scaffold-project` | `/scaffold-project myapp` | Generate full project skeleton |
| `/scaffold-module` | `/scaffold-module items` | Add module to existing project |

### /scaffold-project

Generates a complete FastAPI project with 30+ files including auth, migrations, and tests.

```bash
/scaffold-project myapp
/scaffold-project myapp --with-auth
```

### /scaffold-module

Adds a domain module to an existing project with all layers.

```bash
/scaffold-module items
/scaffold-module items -f "name:str, amount:Decimal"
```

Generates: `models.py`, `schemas.py`, `repository.py`, `services.py`, `deps.py`, `router.py`.

## External Agent Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/obsidian` | `/obsidian [--dry-run]` | Capture session to Obsidian vault |
| `/standup` | `/standup` | Generate daily standup from vault |
| `/changelog` | `/changelog` | Update changelog from merged PRs |
| `/codex-review` | `/codex-review` | Second opinion from OpenAI Codex |

!!! note "External commands require additional setup"
    `/obsidian` requires the obsidian-agent module. `/codex-review` requires an OpenAI API key and the Codex plugin.

## All Commands at a Glance

| Command | Category | Requires Issue | Creates Files |
|---------|----------|---------------|---------------|
| `/orchestrate` | Workflow | Yes | Artifacts in `.agents/outputs/` |
| `/quick` | Workflow | No | Modified source files only |
| `/pr` | Workflow | No | PR on GitHub |
| `/review` | Workflow | No | None |
| `/feature` | Issue Mgmt | No | GitHub issue |
| `/bug` | Issue Mgmt | No | GitHub issue |
| `/spec-draft` | Issue Mgmt | No | Spec file |
| `/spec-review` | Issue Mgmt | No | Optional GitHub issues |
| `/feature-from-spec` | Issue Mgmt | No | GitHub issues |
| `/test-plan` | Testing | Optional | Test plan artifact |
| `/learn` | Learning | No | Updates patterns.md |
| `/metrics` | Learning | No | None (read-only) |
| `/scaffold-project` | Scaffolding | No | 30+ project files |
| `/scaffold-module` | Scaffolding | No | 6 module files |
| `/obsidian` | External | No | Vault entries |
| `/standup` | External | No | Report output |
| `/changelog` | External | No | CHANGELOG.md |
| `/codex-review` | External | No | None |
