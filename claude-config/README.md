# Claude Code Configuration

Portable Claude Code configuration that can be installed on any machine.

## What's Included

| Item | Purpose |
|------|---------|
| `settings.local.json` | Hooks configuration, permissions |
| `hooks/` | PreCompact checkpoint, SessionStart restore |
| `commands/` | Slash commands (/orchestrate, /obsidian, etc.) |
| `agents/` | Agent instructions (map-plan, patch, prove, etc.) |

## Installation

```bash
# Clone the repo (if not already)
git clone https://github.com/jwj2002/agents.git ~/agents

# Run install script
~/agents/claude-config/install.sh
```

This creates symlinks from `~/.claude/` to this repo, so changes sync automatically.

## What's NOT Included

These stay local and are not tracked:

- `projects/` - Session logs (large, machine-specific)
- `history.jsonl` - Command history
- `cache/`, `debug/`, `todos/` - Temp/state data
- `.claude.json` - Auth tokens

## Hooks

| Hook | Trigger | Purpose |
|------|---------|---------|
| `precompact_checkpoint.py` | Before context compaction | Saves state, auto-cleans old checkpoints |
| `sessionstart_restore_state.py` | Session start | Restores context from checkpoints |

## Commands

| Command | Purpose |
|---------|---------|
| `/orchestrate <issue>` | Full workflow: MAP-PLAN → PATCH → PROVE |
| `/obsidian` | Update Obsidian vault with session info |
| `/changelog` | Update changelog from merged PRs |
| `/standup` | Generate daily standup report |
| `/review` | Code review staged changes |

## Updating

Since files are symlinked, just edit in place and commit:

```bash
cd ~/agents
git add claude-config/
git commit -m "Update claude config"
git push
```

On other machines, just `git pull` to get updates.
