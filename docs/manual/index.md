# Agentic Engineering Manual

A comprehensive guide to building systematic, repeatable AI-assisted development workflows using Claude Code, OpenAI Codex, and Obsidian.

---

## What Is This System?

This is a **multi-agent software engineering workflow** where AI agents autonomously handle investigation, planning, implementation, and verification of GitHub issues — with structured feedback loops that improve performance over time.

```
GitHub Issue → Classify → Branch → Agents → Verify → Record → PR
                                      │
                          ┌───────────┼───────────┐
                          ▼           ▼           ▼
                       MAP-PLAN    PATCH       PROVE
                     (investigate) (implement) (verify)
                          │           │           │
                          ▼           ▼           ▼
                       Artifact    Code        Metrics
                       (.md)      Changes     (.jsonl)
```

It is **not** prompt engineering. It is the discipline of designing agent pipelines, artifact chains, verification gates, failure recording, and learning loops.

## Key Capabilities

<div class="grid cards" markdown>

-   :material-robot:{ .lg .middle } **Multi-Agent Pipeline**

    ---

    MAP-PLAN → CONTRACT → PLAN-CHECK → PATCH → PROVE — each agent has a defined role, inputs, outputs, and verification gates.

    [:octicons-arrow-right-24: Orchestrate Pipeline](workflow/orchestrate.md)

-   :material-source-branch:{ .lg .middle } **Parallel Execution**

    ---

    Run 2-3 issues simultaneously using `--parallel` worktree isolation. macOS notifications alert when sessions complete.

    [:octicons-arrow-right-24: Parallel Mode](workflow/parallel.md)

-   :material-brain:{ .lg .middle } **Self-Learning Loop**

    ---

    Every issue outcome is recorded. `/learn --apply` extracts failure patterns and writes prevention directly into agent files.

    [:octicons-arrow-right-24: Learning Loop](learning/self-learning-loop.md)

-   :material-shield-check:{ .lg .middle } **Cross-Model AI + 7 Plugins**

    ---

    Claude writes code, Codex reviews and co-implements. Plus: security guidance, TypeScript/Python LSP, Playwright e2e testing, enhanced PR review.

    [:octicons-arrow-right-24: Codex Plugin](integrations/codex-plugin.md)

-   :material-notebook:{ .lg .middle } **Obsidian Knowledge Capture**

    ---

    Sessions automatically become daily logs, weekly rollups, and project dashboards in your Obsidian vault.

    [:octicons-arrow-right-24: Obsidian Agent](integrations/obsidian-agent.md)

-   :material-sync:{ .lg .middle } **Portable Configuration**

    ---

    All config in one git repo, deployed via symlinks. `git pull` on any machine updates everything instantly.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

</div>

## System Architecture

```
~/agents/                              Source of truth (git repo)
├── claude-config/                     Claude Code configuration
│   ├── agents/     → ~/.claude/agents/    9 agent definitions
│   ├── commands/   → ~/.claude/commands/  18 slash commands
│   ├── hooks/      → ~/.claude/hooks/     6 lifecycle hooks + modules
│   ├── rules/      → ~/.claude/rules/     4 conditional rules
│   ├── skills/     → ~/.claude/skills/    3 workflow skills
│   ├── templates/  agent prompt template  1 shared prompt template
│   └── settings.json → ~/.claude/settings.json
├── mcp-server/                        Custom MCP (metrics, vault access)
├── obsidian-agent/                    Session → Obsidian vault writer
└── docs/manual/                       This documentation (you are here)
```

All configuration is **symlinked** from `~/.claude/` to the repo. Changes propagate instantly. `install.sh` handles setup on any platform (macOS, WSL, Linux).

## Task Routing

Six routing tiers determine how each task is handled:

| Routing Tier | Files | Route To | Example |
|-------------|-------|----------|---------|
| **TRIVIAL** | 1 | `/quick` (no pipeline) | Fix typo, update config |
| **SIMPLE** | 1-3 | Plan Mode (no pipeline) | Add endpoint, wire component |
| **MODERATE** | 4-5 | `/orchestrate` (SIMPLE pipeline) | New service + tests |
| **COMPLEX** | 6+ | `/orchestrate` (COMPLEX pipeline) | New module with schema + service + tests |
| **FULLSTACK** | Any | `/orchestrate` + CONTRACT | Cross-stack feature with enum/API contracts |
| **PRIOR FAIL** | Any | `/orchestrate` + failure context | Retry with root cause injection |

```
TRIVIAL ──────────────── /quick (direct fix, no agents)
SIMPLE ─────────────────  Plan Mode (no agents, no pipeline)
MODERATE ───┐
FULLSTACK ──┤            /orchestrate pipelines:
PRIOR FAIL ─┤
COMPLEX ────┘              SIMPLE:   MAP-PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE
                           COMPLEX:  MAP → PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE
```

Every issue gets outcome tracking in `metrics.jsonl`. Failures get root cause classification in `failures.jsonl`. The `/learn` command turns this data into prevention patterns.

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/jwj2002/agents.git ~/agents
cd ~/agents/claude-config && ./install.sh

# 2. Open any project
cd ~/projects/myapp

# 3. Start working
claude                           # Launch Claude Code
/orchestrate 184                 # Run full pipeline for issue #184
/orchestrate 184 --parallel      # Run in isolated worktree
/quick "fix the login redirect"  # Quick fix, no pipeline
```

## Daily Workflow

| Time | Action | Command |
|------|--------|---------|
| **Morning** | Open project, context auto-restores | `claude` |
| **Working** | Implement issues via pipeline | `/orchestrate <issue>` |
| **Parallel** | Run multiple issues in separate tabs | `/orchestrate <issue> --parallel` |
| **Quick fixes** | Small changes without pipeline | `/quick "description"` |
| **Done** | Create PR with checklist | `/pr` |
| **Automatic** | macOS notification when session completes | notify_completion.py |
| **Automatic** | Sessions captured to Obsidian vault | obsidian-agent (cron) |

## Weekly Maintenance

| Day | Action | Command |
|-----|--------|---------|
| **Friday** | Extract patterns from failures | `/learn --apply` |
| **Friday** | Review performance trends | `/metrics` |
| **Friday** | Validate pattern effectiveness | `/learn --validate` |
| **Sunday** | Cross-project pattern sharing | `/learn --cross-project` |
| **Automatic** | Weekly rollups generated | obsidian-agent (cron) |

## Navigation Guide

| If you want to... | Go to... |
|-------------------|----------|
| Set up on a new machine | [Installation](getting-started/installation.md) |
| Understand the pipeline | [Orchestrate Pipeline](workflow/orchestrate.md) |
| See all available commands | [Command Reference](workflow/commands.md) |
| Run issues in parallel | [Parallel Execution](workflow/parallel.md) |
| Understand how agents work | [Agent Overview](agents/overview.md) |
| Set up cross-model review | [Codex Plugin](integrations/codex-plugin.md) |
| Configure Obsidian capture | [Obsidian Agent](integrations/obsidian-agent.md) |
| Write effective project instructions | [Writing CLAUDE.md](rules/claude-md.md) |
| Look up a term | [Glossary](reference/glossary.md) |
