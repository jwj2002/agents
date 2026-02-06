# Obsidian Vault Update

Update the Obsidian vault with information from this coding session.

## Instructions

Run the obsidian vault update agent to extract and log:
- Next steps and action items
- Completed tasks
- Decisions made
- Blockers encountered
- GitHub references (issues, PRs)
- Files touched

Execute this command:

```bash
cd ~/agents/obsidian-agent && python3 -m obsidian_agent
```

### Options

```bash
# Preview without writing to vault
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --dry-run

# First-time setup (creates config.toml)
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --init

# Process all projects
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --all-projects

# Generate weekly rollup
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --weekly
```

After running, report what was extracted and saved to the vault.

If the command fails, check:
1. Config exists: `~/.config/obsidian-agent/config.toml`
2. If not, run `--init` first
3. Vault path is correct in config
