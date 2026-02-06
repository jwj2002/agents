# Obsidian Second Brain Agent

Captures Claude Code sessions as **project state** in your Obsidian vault. Overwrite current status, append daily logs, generate weekly/monthly rollups for contractor reporting.

## What Changed in v2

| v1 (old) | v2 (new) |
|----------|----------|
| 6 append-only files per project | **STATUS.md** (overwritten) + **Daily log** (appended) |
| Trusted sessions-index.json | **Filesystem mtime only** — no stale index bugs |
| Hardcoded macOS paths | **TOML config** (`~/.config/obsidian-agent/config.toml`) |
| Extracted file lists | Extracts **status, phase, deliverables** |
| No rollups | **Weekly + Monthly** rollup generation |
| No cross-project view | **DASHBOARD.md** — all projects at a glance |

## Vault Structure

```
MyVault/
├── DASHBOARD.md                    # Cross-project overview (overwritten)
└── Projects/
    └── {project-name}/
        ├── STATUS.md               # Current state (overwritten each session)
        └── Log/
            ├── Daily/
            │   └── 2026-02-06.md   # Append-only daily log
            ├── Weekly/
            │   └── 2026-W06.md     # Generated on demand
            └── Monthly/
                └── 2026-02.md      # Generated on demand
```

## Quick Start

```bash
# 1. Install (clone or copy)
git clone <repo-url> ~/agents/obsidian-agent

# 2. Create config
python -m obsidian_agent --init

# 3. Run from any project directory
cd ~/projects/my-project
python -m obsidian_agent

# 4. Preview without writing
python -m obsidian_agent --dry-run
```

## CLI Reference

```bash
# Default: update current project (STATUS + Daily + DASHBOARD)
python -m obsidian_agent

# Specific project path
python -m obsidian_agent --project /path/to/project

# Specific session ID
python -m obsidian_agent --session abc123-def456

# Update all recently active projects
python -m obsidian_agent --all-projects

# Generate weekly rollup (current week)
python -m obsidian_agent --weekly

# Generate weekly rollup (specific week)
python -m obsidian_agent --weekly 2026-W06

# Generate monthly rollup
python -m obsidian_agent --monthly
python -m obsidian_agent --monthly 2026-02

# Preview extraction (no vault writes)
python -m obsidian_agent --dry-run

# Create/update config interactively
python -m obsidian_agent --init

# Backward-compatible entry point (still works)
python update_vault.py --dry-run
```

## Configuration

Config lives at `~/.config/obsidian-agent/config.toml`. Run `--init` to create it, or copy `config.example.toml`.

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

**Precedence**: TOML config > environment variables > platform defaults.

Environment variables: `OBSIDIAN_VAULT_PATH`, `CLAUDE_PROJECTS_PATH`.

## Capturing Knowledge

Tag items with `[CAPTURE]` during a Claude Code session:

```
[CAPTURE] Agents should be stored in ~/agents/ for cross-project use.

[CAPTURE] Agent data flow:
Session → obsidian-agent → Vault → daily-standup → Report
```

Captured items appear in the daily log under **Knowledge**.

## Cross-System Deployment

```bash
# Machine A (macOS)
python -m obsidian_agent --init
# → vault path: ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault

# Machine B (Linux/WSL)
python -m obsidian_agent --init
# → vault path: ~/obsidian/MyVault
```

## Dependencies

- Python 3.11+ (uses stdlib `tomllib`)
- Claude CLI (`claude` command in PATH)
- No pip packages required

## Shell Alias

```bash
# Add to ~/.bashrc or ~/.zshrc
alias brain="python3 -m obsidian_agent --dry-run"
alias brain-update="python3 -m obsidian_agent"
alias brain-weekly="python3 -m obsidian_agent --weekly"
```

## How It Works

1. **Finds session** — locates most recent `.jsonl` by filesystem mtime
2. **Parses messages** — extracts user/assistant messages and tool calls
3. **Extracts state** — sends conversation to Claude (haiku) for structured extraction
4. **Writes vault** — overwrites STATUS.md, appends to daily log, rebuilds DASHBOARD.md

## Files

```
obsidian-agent/
├── obsidian_agent/          # Package
│   ├── __init__.py          # Version
│   ├── __main__.py          # CLI entry point
│   ├── config.py            # TOML config loader
│   ├── session_finder.py    # Session discovery (mtime-based)
│   ├── parser.py            # JSONL conversation parser
│   ├── extractor.py         # Claude-powered state extraction
│   ├── templates.py         # Markdown templates
│   └── vault_writer.py      # Vault file writer
├── config.example.toml      # Example config
├── update_vault.py          # Backward-compat shim
└── README.md
```
