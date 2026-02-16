# Agents Configuration Repository

Unified configuration source for Claude Code and Codex across multiple machines.

## Quick Start

```bash
# Clone
git clone https://github.com/jwj2002/agents.git ~/agents

# Install both Claude + Codex config
~/agents/install-all.sh
```

## Common Workflows

### New Computer

```bash
git clone https://github.com/jwj2002/agents.git ~/agents
~/agents/install-all.sh
```

Reference: `docs/CONFIG-BOOTSTRAP.md`

### New Project (local `.claude`)

```bash
~/agents/claude-config/new-project-claude.sh /path/to/project
```

Then edit:
- `CLAUDE.md`
- `.claude/rules/project-rules.md`
- `.claude/context/project-stack.md`

### Update Existing Machines

```bash
cd ~/agents
git pull
~/agents/install-all.sh
```

## Installers

- Unified installer: `install-all.sh`
- Claude only: `claude-config/install.sh`
- Codex only: `codex-config/install.sh`

## Configuration Packages

- Claude package: `claude-config/README.md`
- Codex package: `codex-config/README.md`
- Full operations guide: `docs/CONFIG-BOOTSTRAP.md`
- Claude system reference: `docs/CLAUDE-SETUP.md`

## Local-Only Files (Not Shared)

- Claude runtime state (`~/.claude/history.jsonl`, `~/.claude/projects/`, etc.)
- Codex runtime/auth state (`~/.codex/auth.json`, `~/.codex/sessions/`, etc.)
- Machine-specific Codex approval rules (`~/.codex/rules/default.rules`)
