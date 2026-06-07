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

### New Project (Claude + Codex)

```bash
~/agents/new-project-agents.sh /path/to/project
```

Then edit:
- `AGENTS.md`
- `CLAUDE.md`
- `.claude/rules/project-rules.md`
- `.claude/context/project-stack.md`

If the repo needs trusted project-level Codex settings, rerun with:

```bash
~/agents/new-project-agents.sh --with-codex-config /path/to/project
```

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
- Project bootstrap: `new-project-agents.sh`

## Configuration Packages

- Claude package: `claude-config/README.md`
- Codex package: `codex-config/README.md`
- Agent capability map: `docs/AGENT-CAPABILITIES.md`
- Skill surfaces: `docs/SKILL-SURFACES.md`
- Full operations guide: `docs/CONFIG-BOOTSTRAP.md`
- Claude system reference: `docs/CLAUDE-SETUP.md`

## Local-Only Files (Not Shared)

- Claude runtime state (`~/.claude/history.jsonl`, `~/.claude/projects/`, etc.)
- Codex runtime/auth state (`~/.codex/auth.json`, `~/.codex/sessions/`, etc.)
- Machine-specific Codex approval rules (`~/.codex/rules/default.rules`)
