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

Runs the multi-agent pipeline for a GitHub issue. Used for MODERATE, COMPLEX, FULLSTACK, and PRIOR FAIL routing tiers. Internally selects a pipeline tier (SIMPLE or COMPLEX) to determine which agents run. TRIVIAL classifications are rejected and redirected to `/quick` (per PR #94).

```bash
/orchestrate 184                      # Standard
/orchestrate 184 --with-tests         # Add TEST-PLANNER phase
/orchestrate 184 --resume             # Resume interrupted workflow
/orchestrate 184 --parallel           # Isolated worktree execution
/orchestrate 184 --discuss            # Add DISCUSS phase before investigation
```

!!! example "Example: running orchestrate"

    ```
    You: /orchestrate 42
    Claude: Issue #42 classified as: SIMPLE (backend)
            Using workflow: MAP-PLAN → PATCH → PROVE
            ... [agents run] ...
            Workflow complete. Next: /pr 42
    ```

See [Orchestrate Workflow](orchestrate.md) for full documentation.

### /quick

Handles TRIVIAL routing tier tasks --- executes small tasks directly without sub-agents, artifacts, or GitHub issues.

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

## Planning & Ideas Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/seed` | `/seed "Add rate limiting" --trigger "next major version"` | Capture deferred ideas with trigger conditions. Seeds surface during `/orchestrate` when scope matches. Supports `--list` and `--check`. |

### /seed

Captures deferred ideas with trigger conditions. Seeds are stored and surfaced during `/orchestrate` when the scope matches their trigger.

```bash
/seed "Add rate limiting" --trigger "next major version"
/seed --list                          # View all captured seeds
/seed --check                         # Check which seeds match current scope
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

### /frontend-design

Generates production-grade frontend interfaces with high design quality, avoiding generic AI aesthetics.

```bash
/frontend-design "Settings page with tabs for profile, billing, notifications"
```

## Codex Plugin Commands

These commands are provided by the installed Codex plugin (not by `claude-config/commands/`). They enable cross-model review and delegation to OpenAI's GPT-5.4 family.

| Command | Usage | Purpose |
|---------|-------|---------|
| `/codex:setup` | `/codex:setup` | Verify the local Codex CLI is ready; toggle review gate |
| `/codex:review` | `/codex:review [--background]` | Standard cross-model review of staged or recent changes |
| `/codex:adversarial-review` | `/codex:adversarial-review [--background]` | Adversarial review focused on contract / access-control / data drift |
| `/codex:rescue` | `/codex:rescue [--background] [--write]` | Delegate investigation, a fix, or a follow-up task to Codex |
| `/codex:status` | `/codex:status` | Check the status of background Codex jobs |
| `/codex:result` | `/codex:result <id>` | Retrieve the output of a completed Codex job |
| `/codex:cancel` | `/codex:cancel <id>` | Cancel an in-flight Codex job |

!!! note "Codex commands require the plugin"
    The `/codex:*` commands are provided by the Codex plugin and require an OpenAI API key plus the local Codex CLI. See [Codex Plugin](../integrations/codex-plugin.md) for setup and the full delegation playbook.

## All Commands at a Glance

The 16 slash commands shipped from `claude-config/commands/`:

| Command | Category | Requires Issue | Creates Files |
|---------|----------|---------------|---------------|
| `/orchestrate` | Workflow | Yes | Artifacts in `.agents/outputs/` |
| `/quick` | Workflow | No | Modified source files only |
| `/pr` | Workflow | No | PR on GitHub |
| `/review` | Workflow | No | None |
| `/seed` | Planning & Ideas | No | Seed entry in store |
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
| `/frontend-design` | Design | No | Frontend source files |

The `/codex:*` family lives in the Codex plugin, not in this repo — see the table above.
