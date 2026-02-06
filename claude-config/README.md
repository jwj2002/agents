# Claude Code Configuration

Portable Claude Code configuration that can be installed on any machine. Provides slash commands, agent workflows, hooks, MCP server, and global rules that work across all projects.

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- Git
- Python 3.10+ (for hooks, MCP server, statusline)

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/jwj2002/agents.git ~/agents

# 2. Run the install script
~/agents/claude-config/install.sh

# 3. (Optional) Install MCP server
cd ~/agents/mcp-server && pip install -e .
```

The install script creates symlinks from `~/.claude/` to this repo:

```
~/.claude/commands/            → ~/agents/claude-config/commands/
~/.claude/agents/              → ~/agents/claude-config/agents/
~/.claude/hooks/               → ~/agents/claude-config/hooks/
~/.claude/rules/               → ~/agents/claude-config/rules/
~/.claude/skills/              → ~/agents/claude-config/skills/
~/.claude/settings.local.json  → ~/agents/claude-config/settings.local.json
~/.claude/statusline.py        → ~/agents/claude-config/statusline.py
```

Existing files are backed up to `~/.claude/config-backup-{timestamp}/` before symlinking.

After installation, all commands and rules are immediately available in every Claude Code session.

## What's Included

| Directory | Purpose |
|-----------|---------|
| `commands/` | Slash commands available in Claude Code |
| `agents/` | Agent instructions for the orchestrate workflow (versioned) |
| `hooks/` | Lifecycle hooks (session start, pre-compact) with error logging |
| `rules/` | Global rules — always-loaded core patterns + conditional loading |
| `skills/` | Multi-step skill definitions (orchestrate, test-plan) |
| `settings.local.json` | Hooks, permissions, MCP servers, statusline config |
| `statusline.py` | Custom terminal status bar (dynamic hostname) |

## Commands

### Workflow

| Command | Usage | Description |
|---------|-------|-------------|
| `/orchestrate` | `/orchestrate 184` | Full issue workflow: MAP → PLAN → CONTRACT → PATCH → PROVE |
| `/pr` | `/pr` | PR creation with checklist, merge strategy, post-merge cleanup |
| `/review` | `/review` | Code review staged changes |
| `/changelog` | `/changelog` | Generate changelog from merged PRs |
| `/standup` | `/standup` | Generate daily standup report (v2 vault support) |
| `/obsidian` | `/obsidian` | Update Obsidian vault with session info |

### Issue Management

| Command | Usage | Description |
|---------|-------|-------------|
| `/feature` | `/feature "Add dark mode"` | Create feature issue via `gh issue create` with labels |
| `/bug` | `/bug "Login fails on Safari"` | Create bug report via `gh issue create` with investigation |
| `/spec-draft` | `/spec-draft "User auth"` | Interactive spec creation with codebase discovery |

### Learning System

| Command | Usage | Description |
|---------|-------|-------------|
| `/learn` | `/learn --cross-project` | Analyze failures, extract patterns across projects |
| `/learn --validate` | `/learn --validate` | A/B test pattern effectiveness (before/after rates) |
| `/metrics` | `/metrics --week` | Agent performance dashboard with version correlation |
| `/agent-update` | `/agent-update --agent patch` | Apply learned improvements (Edit tool, version++) |
| `/postmortem-extract` | `/postmortem-extract` | Convert postmortems → structured failure records |

### FastAPI Scaffolding

| Command | Usage | Description |
|---------|-------|-------------|
| `/scaffold-project` | `/scaffold-project myapp --with-auth` | Generate a complete FastAPI project from scratch |
| `/scaffold-module` | `/scaffold-module items --fields "name:str"` | Add a module to an existing project |

## Rules

| File | Loading | Description |
|------|---------|-------------|
| `core-patterns.md` | Always (~10 lines) | Top 3 failure patterns with one-line prevention |
| `fastapi-layered-pattern.md` | Conditional (`**/backend/**`, `**/api/**`) | Definitive FastAPI layered architecture reference |
| `orchestrate-workflow.md` | Conditional (`.agents/**`) | Multi-phase workflow definition |
| `spec-review-workflow.md` | Conditional (`**/specs/**`, `**/.agents/**`) | Spec finalization gate workflow |

**Optimization**: `core-patterns.md` is always loaded (~10 lines). Full FastAPI reference (~500 lines) only loads in backend contexts via `paths:` frontmatter.

## Agents (Orchestrate Workflow)

Used by the `/orchestrate` command. Each agent has a specific role and version:

```
Issue → MAP/MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PATCH → PROVE
         investigate      test matrix      API spec     implement   verify

* CONTRACT is MANDATORY for fullstack issues
```

| Agent | Version | Role |
|-------|---------|------|
| `_base.md` | 3.0 | Shared behaviors, canonical schemas, root cause enum |
| `map.md` | 1.0 | Read-only codebase analysis (COMPLEX issues) |
| `map-plan.md` | 1.0 | Combined analysis + planning (TRIVIAL/SIMPLE) |
| `plan.md` | 1.0 | File-by-file implementation plan (COMPLEX) |
| `contract.md` | 1.0 | Backend↔frontend API contract (MANDATORY fullstack) |
| `test-planner.md` | 1.0 | Test matrix with edge cases (optional) |
| `patch.md` | 1.0 | Implementation with minimal diffs |
| `prove.md` | 1.0 | Verification, evidence capture, outcome recording |
| `spec-reviewer.md` | 1.0 | Specification review and issue creation |

**Artifact validation**: Each agent validates predecessor artifacts exist before starting. Stops if missing.

**Agent versioning**: All agents have `version: X.Y` in frontmatter. `/agent-update` increments minor version. Metrics record `agent_versions` for correlation.

**Parallel execution**: For COMPLEX issues with `--with-tests`, MAP + TEST-PLANNER run concurrently.

## Hooks

| Hook | Trigger | Purpose |
|------|---------|---------|
| `precompact_checkpoint.py` | Before context compaction | Saves conversation state to YAML checkpoint |
| `sessionstart_restore_state.py` | Session start | Restores context from most recent checkpoint |

Both hooks log errors to `~/.claude/hooks.log` with timestamps.

## MCP Server

Provides tools for querying Obsidian vault and agent metrics from within Claude Code.

| Tool | Description |
|------|-------------|
| `vault_status` | Read STATUS.md for a project → structured JSON |
| `vault_search` | Search daily logs across projects |
| `vault_dashboard` | Cross-project overview from DASHBOARD.md |
| `agent_metrics` | Query metrics.jsonl → success rates, trends |
| `failure_patterns` | Read failures.jsonl → top failure patterns |

**Location**: `~/agents/mcp-server/`
**Config**: `mcpServers` section in `settings.local.json`
**Standalone**: `python3 server.py vault_dashboard` (works without MCP SDK)

## Self-Learning System

```
/orchestrate (issue)
    → MAP → PLAN → PATCH → PROVE
                               │ Record outcome
                   ┌───────────┴────────────┐
             metrics.jsonl            failures.jsonl
                   └───────────┬────────────┘
                          /learn (weekly, --cross-project)
                               │
                         patterns.md
                               │
                       /agent-update (Edit tool, version++)
                               │
                        Next /orchestrate → agents read patterns.md
```

## Canonical Schemas

### metrics.jsonl

```json
{
  "issue": 184,
  "date": "2026-02-06",
  "status": "PASS | BLOCKED",
  "complexity": "TRIVIAL | SIMPLE | COMPLEX",
  "stack": "backend | frontend | fullstack",
  "agents_run": ["MAP-PLAN", "PATCH", "PROVE"],
  "agent_versions": {"map-plan": "1.0", "patch": "1.0"},
  "root_cause": null,
  "blocking_agent": null
}
```

### Root Cause Codes

`ENUM_VALUE`, `COMPONENT_API`, `MULTI_MODEL`, `API_MISMATCH`, `ACCESS_CONTROL`, `MISSING_TEST`, `SQLITE_COMPAT`, `STRUCTURE_VIOLATION`, `SCOPE_CREEP`, `VERIFICATION_GAP`, `OTHER`

## Updating

Since `~/.claude/` symlinks to this repo, editing files here updates Claude Code immediately:

```bash
cd ~/agents/claude-config
# Edit files...
git add . && git commit -m "Update config" && git push
```

On other machines:

```bash
cd ~/agents && git pull
```

## What's NOT Tracked

These stay local and are not included in this repo:

- `~/.claude/projects/` — Session logs (large, machine-specific)
- `~/.claude/history.jsonl` — Command history
- `~/.claude/cache/`, `debug/`, `todos/` — Temp/state data
- `~/.claude/.claude.json` — Auth tokens
- `~/.claude/hooks.log` — Hook error logs (generated locally)

## Related

- [fastapi-architect-agent](https://github.com/jwj2002/fastapi-architect-agent) — Standalone CLI + AI agent for the same FastAPI patterns (works without Claude Code)
- [Full setup reference](../docs/CLAUDE-SETUP.md) — Comprehensive documentation of the entire system
