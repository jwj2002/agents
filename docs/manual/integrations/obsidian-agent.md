# Obsidian Agent

The Obsidian Agent captures Claude Code sessions as project state in your Obsidian vault. It overwrites current status, appends daily logs, and generates weekly and monthly rollups -- transforming ephemeral coding sessions into a persistent knowledge base.

## What It Does

```
Claude Code session (.jsonl)
       |
       v
obsidian-agent (extracts state via Claude Haiku)
       |
       +-- Projects/{name}/STATUS.md     (overwritten each run)
       +-- Projects/{name}/Log/Daily/    (appended)
       +-- DASHBOARD.md                  (cross-project overview)
```

The agent finds the most recent session log, parses the conversation, sends it to Claude Haiku for structured extraction, and writes the results to your vault.

## Vault Structure

```
MyVault/
+-- DASHBOARD.md                    # Cross-project overview (overwritten)
+-- Projects/
    +-- {project-name}/
        +-- STATUS.md               # Current state (overwritten each session)
        +-- Log/
            +-- Daily/
            |   +-- 2026-03-26.md   # Append-only daily log
            +-- Weekly/
            |   +-- 2026-W13.md     # Generated on demand
            +-- Monthly/
                +-- 2026-03.md      # Generated on demand
```

| File | Update Mode | Purpose |
|------|-------------|---------|
| `DASHBOARD.md` | Overwritten | All projects at a glance |
| `STATUS.md` | Overwritten | Current project state |
| `Daily/*.md` | Appended | Chronological activity log |
| `Weekly/*.md` | Generated | Weekly rollup summary |
| `Monthly/*.md` | Generated | Monthly rollup summary |

## What Gets Extracted

The agent sends the conversation to Claude Haiku, which extracts structured state:

| Field | Description |
|-------|-------------|
| `status` | Current project status (e.g., "Active", "Blocked") |
| `phase` | Current development phase |
| `completed_groups` | Groups of completed items with headings |
| `issues` | GitHub issues with number, title, effort, and status |
| `commits` | Recent git commits (injected from git log, not LLM) |
| `decisions` | Architectural decisions made during the session |
| `blockers` | Current blockers preventing progress |
| `next_steps` | Planned next actions |
| `knowledge` | Items tagged with `[CAPTURE]` during the session |

!!! example "STATUS.md excerpt"
    ```markdown
    # mymoney-dev

    **Status**: Active
    **Phase**: Implementation - Phase 2

    ## Completed
    - [x] Database schema migration (#601)
    - [x] Account service layer (#602)

    ## In Progress
    - [ ] Member invitation flow (#605) -- PATCH in progress

    ## Blockers
    - None

    ## Next Steps
    - Complete member invitation frontend
    - Add role-based access tests
    ```

!!! tip "Tagging Knowledge"
    Tag items with `[CAPTURE]` during a Claude Code session to have them extracted into the daily log under a Knowledge section:
    ```
    [CAPTURE] Agents should be stored in ~/agents/ for cross-project use.
    ```

## CLI Commands

### Session Processing

```bash
# Default: update current project (STATUS + Daily + DASHBOARD)
python -m obsidian_agent

# Specific project path
python -m obsidian_agent --project /path/to/project

# Specific session ID
python -m obsidian_agent --session abc123-def456

# Update all recently active projects
python -m obsidian_agent --all-projects

# Only process sessions modified since last run (for timers)
python -m obsidian_agent --all-projects --since-last-run

# Preview extraction without writing to vault
python -m obsidian_agent --dry-run
```

### Rollup Generation

```bash
# Daily cross-project rollup
python -m obsidian_agent --daily-rollup
python -m obsidian_agent --daily-rollup 2026-03-25

# Weekly rollup (current week or specific)
python -m obsidian_agent --weekly
python -m obsidian_agent --weekly 2026-W13

# Monthly rollup
python -m obsidian_agent --monthly
python -m obsidian_agent --monthly 2026-03
```

### Setup

```bash
# Create config interactively
python -m obsidian_agent --init
```

## Automation

### macOS (launchd)

```bash
python -m obsidian_agent --install-launchd
```

Installs two launchd agents:

- **Watcher**: Runs every 60 seconds, processes new sessions (`--all-projects --since-last-run`)
- **Rollup**: Runs nightly at 11 PM, generates daily rollups. Weekly rollups on Sunday, monthly on the last day of the month.

Logs are written to `~/Library/Logs/obsidian-agent/`.

### Linux (systemd)

```bash
python -m obsidian_agent --install-systemd
```

Installs a systemd user timer that runs every 60 seconds, processing all projects with `--since-last-run`.

### Cross-Platform (cron)

```bash
python -m obsidian_agent --install-cron
```

Installs three cron entries:

| Schedule | Command |
|----------|---------|
| Nightly 11:00 PM | `--daily-rollup` |
| Sunday 11:30 PM | `--weekly --all-projects` |
| Last day of month 11:30 PM | `--monthly --all-projects` |

## Configuration

Config lives at `~/.config/obsidian-agent/config.toml`. Run `--init` to create it interactively.

```toml
[vault]
path = "~/obsidian/MyVault"
projects_folder = "Projects"

[claude]
projects_path = "~/.claude/projects"

[extraction]
model = "haiku"
max_conversation_chars = 50000
```

| Section | Key | Description |
|---------|-----|-------------|
| `vault.path` | Obsidian vault root | Supports `~` expansion |
| `vault.projects_folder` | Folder name for project subdirectories | Default: `Projects` |
| `claude.projects_path` | Where Claude stores session data | Default: `~/.claude/projects` |
| `extraction.model` | Claude model for extraction | Default: `haiku` |
| `extraction.max_conversation_chars` | Max conversation size to send | Default: `50000` |

**Precedence**: TOML config > environment variables (`OBSIDIAN_VAULT_PATH`, `CLAUDE_PROJECTS_PATH`) > platform defaults.

## Effort Investment

| Activity | Time | Frequency |
|----------|------|-----------|
| Capture (during coding) | 0 min | Automatic |
| Daily review | 2 min | Daily |
| Weekly rollup review | 5 min | Weekly |
| Monthly summary review | 10 min | Monthly |

The agent runs automatically via launchd/systemd/cron. Session capture requires zero manual effort. The only time investment is reviewing the generated summaries.

!!! tip "Automation setup"
    Start with `--install-launchd` on macOS (or `--install-systemd` on Linux). The watcher runs every 60 seconds and the rollup runs nightly -- you will never need to run the agent manually after initial setup. Check `~/Library/Logs/obsidian-agent/` if sessions are not appearing in your vault.

## Dependencies

- Python 3.11+ (uses stdlib `tomllib`)
- Claude CLI (`claude` command in PATH)
- No pip packages required
