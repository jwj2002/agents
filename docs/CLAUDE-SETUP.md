# Claude Code Setup — Complete Reference

> **Last reviewed**: 2026-02-06
> **Config repo**: `~/agents/` (git: jjob-spec/agents, upstream: jwj2002/agents)
> **Deploy**: `cd ~/agents/claude-config && ./install.sh` (symlinks to `~/.claude/`)

---

## Architecture Overview

```
~/.claude/                          ← Claude Code reads this (symlinked)
├── settings.local.json             ← Hooks, permissions, statusline, MCP servers
├── hooks/                          ← Session lifecycle scripts
├── commands/                       ← Slash commands (/orchestrate, /pr, etc.)
├── agents/                         ← Agent instructions (MAP, PLAN, PATCH, etc.)
├── rules/                          ← Global rules (always/conditional loading)
├── skills/                         ← Multi-step skill definitions
└── statusline.py                   ← Custom terminal status bar

~/agents/                           ← Source repo (git-tracked)
├── claude-config/                  ← ↑ Symlink source for ~/.claude/
├── mcp-server/                     ← MCP server for vault + metrics queries
├── obsidian-agent/                 ← Session → Obsidian vault (v2.0)
├── daily-standup/                  ← Vault → standup report (v2 compatible)
├── code-review/                    ← Pre-commit code review
├── pr-changelog/                   ← PR merge → changelog update
├── doc-reader/                     ← TTS for documents
├── youtube-summarizer/             ← Video → transcript → summary
└── docs/                           ← This file

Per-project overrides:
<project>/.claude/
├── agents/                         ← Project-specific agent overrides
├── commands/                       ← Project-specific commands
├── rules/                          ← Project-specific rules
├── memory/                         ← Failure patterns, metrics, postmortems
└── settings.json                   ← Project-level settings
```

**Key design**: Global config is git-deployed via symlinks. Projects can override any agent or rule locally. The learning loop (metrics → patterns → agent updates) accumulates per-project.

---

## Hooks

| Hook | Script | Trigger | What It Does |
|------|--------|---------|--------------|
| **SessionStart** | `sessionstart_restore_state.py` | Every new session | Loads `PERSISTENT_STATE.yaml`, restores active work context (issue, phase, last action), injects critical patterns (~500 tokens). Logs errors to `~/.claude/hooks.log`. |
| **PreCompact** | `precompact_checkpoint.py` | Before context compaction | Tails last 300 lines, extracts issue/phase/artifacts via regex, saves to `PERSISTENT_STATE.yaml`, backs up transcript. Logs errors to `~/.claude/hooks.log`. |

**Data flow**: PreCompact saves state → SessionStart restores it → continuity across sessions.

---

## Slash Commands

### Workflow Commands

| Command | Purpose | Notes |
|---------|---------|-------|
| `/orchestrate [issue] [--with-tests]` | Full MAP → PLAN → PATCH → PROVE workflow | Core workflow engine. Routes TRIVIAL/SIMPLE → 3-agent, COMPLEX → 4-agent. Supports parallel execution. |
| `/pr [number]` | PR creation, review, and merge workflow | Pre-PR checklist, `gh pr create` template, merge strategy, post-merge cleanup |
| `/test-plan [issue or spec]` | Pre-implementation test planning | Runs TEST-PLANNER agent, generates test matrix |

### Spec & Issue Commands

| Command | Purpose | Notes |
|---------|---------|-------|
| `/spec-draft "title"` | Interactive spec creation with codebase discovery | Multi-step guided process with risk flags |
| `/feature <title>` | Create feature issue via `gh issue create` | Executable — classifies scope/stack, adds labels |
| `/feature-from-spec` | Create issue from spec analysis | Used by spec-reviewer agent |
| `/bug <title>` | Create bug report via `gh issue create` | Executable — investigates context, adds labels |

### Code Generation Commands

| Command | Purpose | Notes |
|---------|---------|-------|
| `/scaffold-project [name]` | Generate full FastAPI project skeleton | 30+ files, auth, migrations, tests |
| `/scaffold-module [name]` | Generate single FastAPI module | Model, schema, repo, service, router, deps |

### Learning System Commands

| Command | Purpose | Notes |
|---------|---------|-------|
| `/learn [--since] [--cross-project] [--validate]` | Analyze failures, extract patterns | Cross-project aggregation, pattern A/B validation |
| `/metrics [--week] [--month]` | Display agent performance dashboard | Success rates, trends, agent version correlation |
| `/postmortem-extract` | Convert postmortem files → structured failure records | Feeds into /learn |
| `/agent-update [--agent NAME]` | Apply learned improvements to agent files | Uses Edit tool (not sed), increments agent version |

### External Agent Commands

| Command | Purpose | Notes |
|---------|---------|-------|
| `/obsidian` | Capture session to Obsidian vault | Uses `python3 -m obsidian_agent` with `--dry-run`, `--init`, `--weekly` options |
| `/standup` | Generate daily standup from vault | Supports v2 vault format (STATUS.md + Log/Daily/) |
| `/changelog` | Update changelog from merged PRs | External script, uses gh CLI |
| `/review` | Pre-commit code review | External script, uses Claude CLI |
| `/codex-review` | Second opinion from OpenAI Codex | Requires OPENAI_API_KEY |

---

## Agents (Orchestrate Workflow)

The orchestrate system runs agents in sequence for issue implementation:

```
Issue → MAP/MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PATCH → PROVE
         investigate      test matrix      API spec     implement   verify

* CONTRACT is MANDATORY for fullstack (not optional)
```

| Agent | Phase | Version | Purpose | Target Lines |
|-------|-------|---------|---------|-------------|
| **_base.md** | — | 3.0 | Shared behaviors, canonical schemas, root cause enum | — |
| **map.md** | 1 | 1.0 | Read-only investigation, classify complexity | 150 (max 200) |
| **map-plan.md** | 1+2 | 1.0 | Combined MAP + PLAN for TRIVIAL/SIMPLE issues | 350 (max 450) |
| **plan.md** | 2 | 1.0 | File-by-file implementation plan for COMPLEX | 350 (max 450) |
| **test-planner.md** | 1.5 | 1.0 | Test matrix with edge cases (optional) | 250 (max 350) |
| **contract.md** | 2.5 | 1.0 | Backend↔frontend API contract (MANDATORY fullstack) | 180 (max 250) |
| **patch.md** | 3 | 1.0 | Implementation with minimal diffs | 250 (max 350) |
| **prove.md** | 4 | 1.0 | Verification, evidence capture, outcome recording | 200 (max 300) |
| **spec-reviewer.md** | — | 1.0 | Analyze spec against codebase, generate issues | 300 (max 400) |

**Artifact validation**: Each agent validates predecessor artifacts exist before starting. STOP if missing.

**Agent versioning**: All agents have `version: X.Y` in frontmatter. `/agent-update` increments minor version. Metrics record `agent_versions` for correlation.

**Learning loop**: PROVE records outcomes → `.claude/memory/metrics.jsonl` + `failures.jsonl` → `/learn` extracts patterns → agents read `patterns.md` on startup.

---

## Rules

| Rule | Scope | Loading | Purpose |
|------|-------|---------|---------|
| **core-patterns.md** | Global | Always loaded (~10 lines) | Top 3 failure patterns with one-line prevention |
| **fastapi-layered-pattern.md** | Global | Conditional (`**/backend/**`, `**/api/**`) | Definitive reference: Model → Schema → Repo → Service → Router → Deps |
| **orchestrate-workflow.md** | Global | Conditional (`.agents/**`) | Multi-phase workflow definition, efficiency targets |
| **spec-review-workflow.md** | Global | Conditional (`**/specs/**`, `**/.agents/**`) | Spec finalization gate: finalize → commit → tag → create issues |
| **backend-patterns.md** | Project | Project-specific | FastAPI conventions, SQLAlchemy patterns, JWT auth |
| **testing.md** | Project | Project-specific | pytest patterns, fixtures, async testing |

**Optimization**: `core-patterns.md` is always loaded (~10 lines). Full FastAPI reference (~500 lines) only loads in backend contexts.

---

## MCP Server

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

---

## Skills

| Skill | Purpose |
|-------|---------|
| **orchestrate** | Multi-agent workflow with self-learning (v3.0). SKILL.md + ORCHESTRATE_REFERENCE.md |
| **test-plan** | Pre-implementation test planning. Generates test matrix with priority levels |

---

## Standalone Agents

| Agent | Purpose | Status | Key Tech |
|-------|---------|--------|----------|
| **obsidian-agent** | Capture sessions → Obsidian vault (STATUS + Daily + Dashboard) | Working (v2.0) | Claude CLI, TOML config |
| **daily-standup** | Aggregate vault → standup report | Working (v2 compatible) | Vault parsing, auto-detects v1/v2 |
| **mcp-server** | MCP tools for vault + metrics access | New | MCP SDK, standalone CLI |
| **code-review** | Pre-commit code review | Working | Claude CLI, git hooks |
| **pr-changelog** | PR merge → CHANGELOG.md + vault | Working | gh CLI, git hooks |
| **doc-reader** | TTS for documents | Working | Edge TTS, ffmpeg |
| **youtube-summarizer** | Video → local Whisper → Claude summary | Working | yt-dlp, Whisper, Claude |

---

## Deployment

### Shell Customizations (local-only, not templated)

The `~/.zshrc` iTerm2 tab-naming block (`_set_tab_name` + `chpwd` + `preexec`) is
a local shell customization. It is **not** written by `bootstrap-laptop.sh`,
`machines/personal/post-install.sh`, or any other repo script. Each new machine
must apply it manually from the reference block in `~/.zshrc`.

**Required guard inside `chpwd()`** — Claude Code shell snapshots can serialize
`chpwd()` into `~/.claude/shell-snapshots/snapshot-zsh-*.sh` without capturing
`_set_tab_name` when the snapshot was generated from a session that predated the
tab-naming block being loaded. Without the guard, every Bash tool call that
changes directory emits `chpwd:1: command not found: _set_tab_name`. The guard
must be the first statement in `chpwd()`:

```zsh
chpwd() {
  (( $+functions[_set_tab_name] )) || return 0
  _set_tab_name "$(basename "$PWD" | tr '[:upper:]' '[:lower:]') - zsh"
}
```

The guard is a no-op in interactive iTerm2 sessions (where `_set_tab_name` is
defined) and silently exits in non-interactive/snapshot contexts (where it is
absent). Opening a fresh iTerm2 tab after editing `~/.zshrc` regenerates the
snapshot with both functions present — making the guard effectively a one-time
fix per machine.

---

### New Machine Setup

```bash
# 1. Clone the agents repo
git clone https://github.com/jwj2002/agents.git ~/agents

# 2. Install Claude Code config (symlinks)
cd ~/agents/claude-config && ./install.sh

# 3. Configure obsidian agent
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --init

# 4. Install MCP server
cd ~/agents/mcp-server && python3 -m pip install -e .

# 5. Install standalone agent dependencies (as needed)
python3 -m pip install edge-tts    # doc-reader
python3 -m pip install yt-dlp      # youtube-summarizer
```

### Cross-System State

| Component | Synced via | Notes |
|-----------|-----------|-------|
| Claude config | Git (agents repo) | `install.sh` symlinks |
| Obsidian vault | iCloud (macOS) or manual sync | Single vault, TOML config per machine |
| Project `.claude/` | Git (per-project repo) | Memory, patterns, metrics |
| `PERSISTENT_STATE.yaml` | Not synced (session-local) | Recreated by hooks each session |

---

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
  "agent_versions": {"map-plan": "1.0", "patch": "1.0", "prove": "1.0"},
  "root_cause": null,
  "blocking_agent": null
}
```

### failures.jsonl

```json
{
  "issue": 184,
  "date": "2026-02-06",
  "agent": "PATCH",
  "root_cause": "ENUM_VALUE",
  "details": "Frontend used CO_OWNER instead of CO-OWNER",
  "fix": "Changed string literal to match backend enum VALUE",
  "prevention": "MAP should document enum VALUES explicitly",
  "files": ["frontend/src/components/MemberForm.jsx"]
}
```

### Root Cause Codes

`ENUM_VALUE`, `COMPONENT_API`, `MULTI_MODEL`, `API_MISMATCH`, `ACCESS_CONTROL`, `MISSING_TEST`, `SQLITE_COMPAT`, `STRUCTURE_VIOLATION`, `SCOPE_CREEP`, `VERIFICATION_GAP`, `OTHER`

---

## Known Issues & Improvement Backlog

All 21 items from the initial audit have been resolved:

| # | Issue | Status |
|---|-------|--------|
| 1 | `/obsidian` hardcoded macOS path | ✅ Fixed — uses `python3 -m obsidian_agent` |
| 2 | daily-standup reads old v1 vault format | ✅ Fixed — auto-detects v1/v2, reads STATUS.md + Log/Daily/ |
| 3 | `/agent-update` uses sed | ✅ Fixed — rewritten to use Edit tool + Python fallback |
| 4 | No artifact validation between phases | ✅ Fixed — all agents validate predecessor artifacts |
| 5 | CONTRACT optional for fullstack | ✅ Fixed — MANDATORY, PATCH stops if missing |
| 6 | metrics.jsonl format inconsistent | ✅ Fixed — canonical schema in _base.md |
| 7 | Root cause codes are magic strings | ✅ Fixed — canonical enum in _base.md |
| 8 | `/pr` command skeletal | ✅ Fixed — expanded with checklist, template, merge strategy |
| 9 | Bug/Feature not executable | ✅ Fixed — both now call `gh issue create` |
| 10 | Orchestrate no TOC | ✅ Fixed — TOC with anchor links added |
| 11 | `/learn` single-project only | ✅ Fixed — `--cross-project` flag aggregates across projects |
| 12 | `/metrics` no schema ref | ✅ Fixed — schema reference + validation step added |
| 13 | session-migration.md global | ✅ Fixed — moved to project `.claude/agents/` |
| 14 | statusline.py hardcoded DELLPRO | ✅ Fixed — uses `socket.gethostname()` |
| 15 | Hooks fail silently | ✅ Fixed — error logging to `~/.claude/hooks.log` |
| 16 | No MCP server | ✅ Built — `~/agents/mcp-server/` with 5 tools |
| 17 | No pattern A/B testing | ✅ Fixed — `/learn --validate` compares before/after rates |
| 18 | No agent versioning | ✅ Fixed — `version: 1.0` in all agent frontmatters |
| 19 | No parallel execution | ✅ Fixed — MAP + TEST-PLANNER can run concurrently |
| 20 | Rules always loaded | ✅ Fixed — `paths:` frontmatter for conditional loading + `core-patterns.md` |
| 21 | No canonical schemas | ✅ Fixed — metrics.jsonl + failures.jsonl schemas in _base.md |

---

## Self-Learning System — How It Works

```
                    ┌─────────────┐
                    │ /orchestrate│
                    │   (issue)   │
                    └──────┬──────┘
                           │
            MAP → PLAN → PATCH → PROVE
                                   │
                          Record outcome
                           │
              ┌────────────┴─────────────┐
              │                          │
        metrics.jsonl              failures.jsonl
        (canonical schema,         (canonical schema,
         agent_versions)            root_cause enum)
              │                          │
              └────────────┬─────────────┘
                           │
                      ┌────┴────┐
                      │ /learn  │ (weekly, --cross-project)
                      └────┬────┘
                           │
                    patterns.md
                    (clustered failure
                     patterns + fixes)
                           │
                    ┌──────┴──────┐
                    │/agent-update│ (Edit tool, version++)
                    └──────┬──────┘
                           │
                    Updated agent
                    instructions
                           │
                    ┌──────┴──────┐
                    │  Next run   │ → agents read
                    │  /orchestrate│   patterns.md
                    └─────────────┘    on startup
```

---

## Recommended Priorities (2026-02 sprint)

**Operational discipline** (maximize existing system):
1. Run `/learn` weekly — builds pattern database
2. Run `/learn --validate` monthly — prune ineffective patterns
3. Run `/learn --cross-project` quarterly — cross-pollinate learnings

**Next improvements**:
4. Weekly rollup automation: obsidian-agent `--weekly` → standup-style report → shareable
5. Monthly rollup with hours, deliverables, decisions — contractor invoice support

## Unified Claude + Codex Bootstrap

For current multi-machine setup and maintenance workflows, see:

- `docs/CONFIG-BOOTSTRAP.md`

That guide covers:
- new computer setup (WSL/macOS/Windows)
- one-command dual install (`~/agents/install-all.sh`)
- new project local bootstrap (`~/agents/new-project-agents.sh`)
- update workflow for shared config changes
