# Obsidian Vault Update Agent

Automatically captures and logs information from Claude Code sessions to your Obsidian vault.

## What It Does

After a coding session, this agent parses the conversation and extracts:

| Category | What It Captures |
|----------|------------------|
| **Next Steps** | Tasks identified but not yet done |
| **Completed** | Work finished during the session |
| **Decisions** | Technical choices and reasoning |
| **Blockers** | Things preventing progress |
| **GitHub Refs** | Issues, PRs, commits mentioned |
| **Files Touched** | Files read, created, or modified |
| **Session Summary** | Brief overview of what happened |
| **Knowledge** | Items tagged with `[CAPTURE]` |

## Capturing Knowledge

To capture concepts, diagrams, or reference material during a session, use the `[CAPTURE]` tag:

```
[CAPTURE] Agents should be stored in ~/agents/ for cross-project use.

[CAPTURE] Agent data flow:
Session → obsidian-agent → Vault → daily-standup → Report
```

Captured items are saved to `knowledge.md` and the session log.

## Vault Structure

```
MyVault/
└── Projects/
    └── {repo-name}/
        ├── next-steps.md      # Running list of pending tasks
        ├── completed.md       # Finished items by date
        ├── decisions.md       # Technical decisions log
        ├── blockers.md        # Current impediments
        ├── github-refs.md     # Issue/PR references
        ├── knowledge.md       # [CAPTURE] tagged concepts
        └── sessions/
            └── 2024-01-31.md  # Full session details
```

## Usage

### From Terminal

```bash
# Update vault from current directory's project
obsidian-update

# Update vault for a specific project
obsidian-update --project /path/to/project

# Preview what would be extracted (no changes made)
obsidian-update --dry-run

# Update a specific session by ID
obsidian-update --session abc123-def456
```

### From Claude Code

```
/obsidian
```

### Automatic (Pre-Compact Hook)

The agent runs automatically before Claude Code compacts conversation context, ensuring session information is captured before summarization.

## Installation

### 1. Dependencies

- Python 3.10+
- Claude CLI (`claude` command available in PATH)

### 2. Shell Alias (Optional)

Add to `~/.zshrc` or `~/.bashrc`:

```bash
alias obsidian-update="python3 ~/agents/obsidian-agent/update_vault.py"
```

### 3. Claude Code Hook (Optional)

Add to `~/.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/agents/obsidian-agent/update_vault.py"
          }
        ]
      }
    ]
  }
}
```

### 4. Slash Command (Optional)

Create `~/.claude/commands/obsidian.md` with instructions to run the update script.

## Configuration

Edit `config.py` to customize paths:

```python
# Obsidian vault location
VAULT_PATH = Path("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault")

# Claude Code projects directory
CLAUDE_PROJECTS_PATH = Path("~/.claude/projects")
```

## How It Works

1. **Finds session log** - Locates the `.jsonl` conversation file in `~/.claude/projects/`
2. **Parses messages** - Extracts user and assistant messages, tool calls
3. **Calls Claude (haiku)** - Sends conversation to Claude for structured extraction
4. **Updates vault** - Writes to consolidated files and session log

## Files

| File | Purpose |
|------|---------|
| `config.py` | Path configuration |
| `parser.py` | Reads and parses Claude Code conversation logs |
| `extractor.py` | Uses Claude to extract structured information |
| `vault_writer.py` | Writes extracted data to Obsidian vault |
| `update_vault.py` | Main entry point / CLI |

## Troubleshooting

### "No Claude project folder found"

The agent looks for conversation logs based on your current directory. Make sure you're in a directory where you've used Claude Code, or specify `--project`.

### Empty extraction results

- Check `/tmp/obsidian-agent.log` for errors
- Try `--dry-run` to see what would be extracted
- Ensure the Claude CLI is working: `claude -p "hello" --output-format json`

### Vault not updating

- Verify vault path in `config.py` matches your Obsidian vault location
- Check that the vault directory is accessible (iCloud sync may cause delays)
