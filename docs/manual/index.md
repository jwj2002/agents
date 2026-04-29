# Agentic Engineering Manual

## Point Claude at a GitHub issue. Get a tested pull request back.

You describe the work. Agents investigate, plan, implement, and verify it — then hand you a PR ready for review.

---

<div class="grid cards" markdown>

-   :material-pencil-outline:{ .lg .middle } **Describe what you want**

    ---

    Write a GitHub issue in plain English. Agents handle investigation, planning, implementation, and verification — you review the result.

    [:octicons-arrow-right-24: See the pipeline](workflow/orchestrate.md)

-   :material-chart-line:{ .lg .middle } **92% first-attempt success rate**

    ---

    Every outcome is recorded. A self-learning loop extracts failure patterns and writes prevention rules so the same mistake never happens twice.

    [:octicons-arrow-right-24: How learning works](learning/self-learning-loop.md)

-   :material-shield-check:{ .lg .middle } **Two AI models, one workflow**

    ---

    Claude implements. Codex reviews. Different models catch different blind spots, giving you defense in depth before you ever look at the code.

    [:octicons-arrow-right-24: Codex integration](integrations/codex-plugin.md)

</div>

---

## Choose your path

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **New here?**

    ---

    Go from zero to your first automated PR in 10 minutes.

    [:octicons-arrow-right-24: First 10 Minutes](getting-started/first-10-minutes.md)

-   :material-download:{ .lg .middle } **Setting up a machine?**

    ---

    Clone, symlink, done. Works on macOS, WSL, and Linux.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

-   :material-book-open-variant:{ .lg .middle } **Already running?**

    ---

    Look up any slash command, agent, or configuration option.

    [:octicons-arrow-right-24: Command Reference](workflow/commands.md)

-   :material-chef-hat:{ .lg .middle } **Just want recipes?**

    ---

    Common workflows for daily work — fix a typo, ship a feature, recover from a stuck session.

    [:octicons-arrow-right-24: Cookbook](cookbook.md)

</div>

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/jwj2002/agents.git ~/agents
cd ~/agents/claude-config && ./install.sh

# Open any project and run
cd ~/projects/myapp
claude
/orchestrate 184
```

For a guided walkthrough, see [First 10 Minutes](getting-started/first-10-minutes.md).

---

??? info "System Overview"

    ### Architecture

    ```
    ~/agents/                              Source of truth (git repo)
    ├── claude-config/                     Claude Code configuration
    │   ├── agents/     → ~/.claude/agents/    12 agent definitions
    │   ├── commands/   → ~/.claude/commands/  16 slash commands
    │   ├── hooks/      → ~/.claude/hooks/     11 lifecycle hooks + modules
    │   ├── rules/      → ~/.claude/rules/     12 rules (mix of always-loaded and conditional)
    │   ├── skills/     → ~/.claude/skills/    7 workflow skills
    │   ├── templates/  agent prompt template  8 template entries
    │   └── settings.json → ~/.claude/settings.json
    ├── mcp-server/                        Custom MCP (metrics, vault access)
    ├── obsidian-agent/                    Session → Obsidian vault writer
    └── docs/manual/                       This documentation
    ```

    All configuration is **symlinked** from `~/.claude/` to the repo. Changes propagate instantly. `install.sh` handles setup on any platform.

    ### Pipeline

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

    ### Task Routing

    | Routing Tier | Files | Route To | Example |
    |-------------|-------|----------|---------|
    | **TRIVIAL** | 1 | `/quick` (no pipeline) | Fix typo, update config |
    | **SIMPLE** | 1-3 | Plan Mode (no pipeline) | Add endpoint, wire component |
    | **MODERATE** | 4-5 | `/orchestrate` (SIMPLE pipeline) | New service + tests |
    | **COMPLEX** | 6+ | `/orchestrate` (COMPLEX pipeline) | New module with schema + service + tests |
    | **FULLSTACK** | Any | `/orchestrate` + CONTRACT | Cross-stack feature with enum/API contracts |
    | **PRIOR FAIL** | Any | `/orchestrate` + failure context | Retry with root cause injection |

    `/orchestrate` rejects TRIVIAL classifications and redirects to `/quick`; the TRIVIAL row above is the canonical destination.

    ```
    TRIVIAL ──────────────── /quick (direct fix, no agents)
    SIMPLE ─────────────────  Plan Mode (no agents, no pipeline)
    MODERATE ───┐
    FULLSTACK ──┤            /orchestrate pipelines:
    PRIOR FAIL ─┤
    COMPLEX ────┘              SIMPLE:   MAP-PLAN → [CONTRACT*] → PATCH → PROVE
                               COMPLEX:  MAP → PLAN → [CONTRACT*] → PLAN-CHECK → PATCH → PROVE
    ```

    ### Daily Workflow

    | Time | Action | Command |
    |------|--------|---------|
    | **Morning** | Open project, context auto-restores | `claude` |
    | **Working** | Implement issues via pipeline | `/orchestrate <issue>` |
    | **Parallel** | Run multiple issues in separate tabs | `/orchestrate <issue> --parallel` |
    | **Quick fixes** | Small changes without pipeline | `/quick "description"` |
    | **Done** | Create PR with checklist | `/pr` |
    | **Automatic** | macOS notification when session completes | notify_completion.py |
    | **Automatic** | Sessions captured to Obsidian vault | obsidian-agent (cron) |

    ### Weekly Maintenance

    | Day | Action | Command |
    |-----|--------|---------|
    | **Friday** | Extract patterns from failures | `/learn --apply` |
    | **Friday** | Review performance trends | `/metrics` |
    | **Friday** | Validate pattern effectiveness | `/learn --validate` |
    | **Sunday** | Cross-project pattern sharing | `/learn --cross-project` |
    | **Automatic** | Weekly rollups generated | obsidian-agent (cron) |
