# Claude + Codex Configuration Bootstrap

Use this process to keep Claude and Codex aligned across WSL laptop, macOS, and Windows desktop.

## Repository Layout

```text
~/agents/
├── claude-config/         # Shared Claude configuration
├── codex-config/          # Shared Codex configuration
├── install-all.sh         # Unified installer (Claude + Codex)
└── docs/CONFIG-BOOTSTRAP.md
```

## New Computer Setup

1. Clone repo:

```bash
git clone https://github.com/jwj2002/agents.git ~/agents
```

2. Install both configs:

```bash
~/agents/install-all.sh
```

3. Verify links:

```bash
ls -la ~/.claude
ls -la ~/.codex/rules ~/.codex/skills
```

Notes:
- Codex system skills stay local at `~/.codex/skills/.system/`.
- Machine-specific Codex approvals stay local at `~/.codex/rules/default.rules`.
- Prefer WSL on Windows desktop for parity with Linux/mac shell workflows.

## New Project Setup (Local .claude)

Inside the new project repo:

```bash
~/agents/claude-config/new-project-claude.sh /path/to/project
```

Then edit:
- `CLAUDE.md`
- `.claude/rules/project-rules.md`
- `.claude/context/project-stack.md`

Commit project-local files to the project repository.

## Updating Shared Config

On the machine where you edit config:

```bash
cd ~/agents
git checkout -b config/<change>
# edit files
git add .
git commit -m "Update shared Claude/Codex config"
git push
```

After merge, on every other machine:

```bash
cd ~/agents
git pull
~/agents/install-all.sh
```

## What Is Shared vs Local

Shared in git:
- `claude-config/*`
- `codex-config/*`
- `install-all.sh`

Local only (not shared):
- `~/.claude/history.jsonl`, `~/.claude/projects/`, `~/.claude/debug/`
- `~/.codex/auth.json`, `~/.codex/history.jsonl`, `~/.codex/sessions/`, `~/.codex/tmp/`
- `~/.codex/rules/default.rules`

## Per-Tool Installers

Install/update Claude only:

```bash
~/agents/claude-config/install.sh
```

Install/update Codex only:

```bash
~/agents/codex-config/install.sh
```
