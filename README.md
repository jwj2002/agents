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
- Claude + Codex collaboration model: `docs/CLAUDE-CODEX-COLLABORATION.md`
- Agent capability map: `docs/AGENT-CAPABILITIES.md`
- Skill surfaces: `docs/SKILL-SURFACES.md`
- Full operations guide: `docs/CONFIG-BOOTSTRAP.md`
- Claude system reference: `docs/CLAUDE-SETUP.md`

## Sibling Tools in This Repo

Active: `obsidian-agent/` (session → vault writer), `pulse/` + `email-digest/`
(+ `google/`/`m365/` transports), `action/` / `decision/` / `project/` CLIs
(deployed via `bin/`), `knowledge/`, `lib/`, `machines/`,
`codex-config/`.

Dormant (keep until a decision forces it): `code-review/`, `ui-testing/`,
`project-template/`, `mcp-server/` (vault-metrics — retired from
auto-registration #425, 4 calls/45d; surfaces are pure CLIs since Path B;
re-register with `claude mcp add --scope user vault-metrics -- <venv-python> mcp-server/server.py`).

Archived 2026-06-10 (#408): `orchestrate-workflow/` → `_archived/orchestrate-workflow-legacy/` (superseded by claude-config orchestrate).

Removed 2026-06-09 (#368, recoverable at commit `9b236c3` and earlier):
`youtube-summarizer/`, `doc-reader/`, `daily-standup/` (superseded by
`/pulse digest`), `pr-changelog/` — none were referenced by any live config,
bin script, skill, or launchd job. `site/` (mkdocs build output) is deleted
locally and untracked; rebuild on demand with `mkdocs build`.

## Local-Only Files (Not Shared)

- Claude runtime state (`~/.claude/history.jsonl`, `~/.claude/projects/`, etc.)
- Codex runtime/auth state (`~/.codex/auth.json`, `~/.codex/sessions/`, etc.)
- Machine-specific Codex approval rules (`~/.codex/rules/default.rules`)
