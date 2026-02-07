# Obsidian Vault Update

Update the Obsidian vault with information from this coding session.

## Usage

```
/obsidian          → Update current project only
/obsidian --all    → Update all recent projects
/obsidian --dry-run → Preview without writing
/obsidian --weekly → Generate weekly rollup
/obsidian --init   → First-time setup
```

## Instructions

Parse the ARGUMENTS string to determine which flags were passed.

IMPORTANT: The agent uses `os.getcwd()` to find the current project, but since we
must `cd` into the agent directory to run it, always pass `--project` with the
current working directory to ensure the correct project is updated.

If ARGUMENTS contains `--all`:
```bash
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --all-projects
```

If ARGUMENTS contains `--dry-run`:
```bash
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --project "$CWD" --dry-run
```

If ARGUMENTS contains `--weekly`:
```bash
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --project "$CWD" --weekly
```

If ARGUMENTS contains `--init`:
```bash
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --init
```

Otherwise (no arguments, default):
```bash
cd ~/agents/obsidian-agent && python3 -m obsidian_agent --project "$CWD"
```

Replace `$CWD` with the actual current working directory path (the project you are
working in, NOT the obsidian-agent directory). Use the working directory shown in
the environment context (e.g., `/home/jjob/projects/VE-RAG-System`).

The agent extracts and logs:
- Next steps and action items
- Completed tasks
- Decisions made
- Blockers encountered
- GitHub references (issues, PRs)

After running, report what was extracted and saved to the vault.

If the command fails, check:
1. Config exists: `~/.config/obsidian-agent/config.toml`
2. If not, run `--init` first
3. Vault path is correct in config
