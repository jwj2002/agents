# Installation

This guide walks through setting up the Claude Code configuration framework on a new machine.

## Prerequisites

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| **Git** | 2.30+ | Version control, worktree support |
| **Python 3** | 3.10+ | Hooks, MCP server, statusline |
| **Node.js** | 18+ | MCP transports, frontend tooling |
| **GitHub CLI** (`gh`) | 2.0+ | Issue and PR automation |
| **Claude Code** | Latest | The CLI itself |

Optional but recommended:

| Tool | Purpose |
|------|---------|
| **uv** | Fast Python package management (preferred over pip) |
| **Bun** | Fast JS runtime for MCP servers |

## Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/agents.git ~/agents
```

This creates the central configuration repository at `~/agents/`.

## Step 2: Run the Installer

```bash
cd ~/agents/claude-config && ./install.sh
```

!!! success "Expected output"
    The installer prints progress for each phase: `[1/4] Symlinks... [2/4] Dependencies... [2.5/4] Plugins... [3/4] First-time setup... [4/4] Verification...` with a final summary of all checks passed.

The installer runs four phases automatically.

### Phase 1: Symlinks

Creates symlinks from `~/.claude/` to the repo so Claude Code reads your version-controlled configuration directly.

| Source (in repo) | Target (Claude reads) |
|------------------|-----------------------|
| `claude-config/settings.json` | `~/.claude/settings.json` |
| `claude-config/hooks/` | `~/.claude/hooks/` |
| `claude-config/commands/` | `~/.claude/commands/` |
| `claude-config/agents/` | `~/.claude/agents/` |
| `claude-config/rules/` | `~/.claude/rules/` |
| `claude-config/skills/` | `~/.claude/skills/` |
| `claude-config/statusline.py` | `~/.claude/statusline.py` |

!!! note "settings.local.json is never symlinked"
    Machine-specific settings (`settings.local.json`) stay local. This file holds MCP server paths that vary by machine and is not tracked in git.

### Phase 2: Dependencies

The installer detects your Python package manager in priority order: active venv, `uv pip`, `pip3`, `pip`.

**MCP server** -- installed into a dedicated virtual environment:

```bash
# Created automatically by install.sh
~/agents/mcp-server/.venv/bin/pip install -e ~/agents/mcp-server
```

**PyYAML** -- required by session hooks for state persistence:

```bash
# install.sh checks if yaml is importable first
python3 -c "import yaml" || pip install PyYAML
```

### Phase 2.5: Plugins

If the `claude` CLI is available, the installer adds the OpenAI Codex marketplace and installs all 7 required plugins:

| Plugin | Source | Purpose |
|--------|--------|---------|
| `codex` | `openai-codex` | Cross-model review and task delegation via GPT |
| `security-guidance` | `claude-plugins-official` | Security review, vulnerability detection, compliance checks |
| `typescript-lsp` | `claude-plugins-official` | Real-time TypeScript/React type errors, auto-imports |
| `pyright-lsp` | `claude-plugins-official` | Python type checking for FastAPI backend |
| `pr-review-toolkit` | `claude-plugins-official` | Enhanced PR review capabilities |
| `playwright` | `claude-plugins-official` | End-to-end browser testing |
| `frontend-design` | `claude-plugins-official` | Production-grade UI generation |

```bash
# Marketplace setup
claude plugin marketplace add openai/codex-plugin-cc

# All plugins installed in a loop
claude plugin install codex@openai-codex
claude plugin install security-guidance@claude-plugins-official
claude plugin install typescript-lsp@claude-plugins-official
claude plugin install pyright-lsp@claude-plugins-official
claude plugin install pr-review-toolkit@claude-plugins-official
claude plugin install playwright@claude-plugins-official
claude plugin install frontend-design@claude-plugins-official
```

!!! note "Prerequisites"
    - **Codex plugin** requires `npm install -g @openai/codex` and a ChatGPT subscription or OpenAI API key
    - **LSP plugins** (typescript-lsp, pyright-lsp) require their respective language servers installed locally
    - All other plugins work out of the box

### Phase 3: First-time Setup

Creates the Obsidian vault directory and agent configuration:

- **macOS**: Uses iCloud path (`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault`)
- **WSL**: Creates Windows-side directory with symlink
- **Linux**: Uses `~/obsidian/MyVault`

Generates `~/.config/obsidian-agent/config.toml` with vault path and extraction settings.

### Phase 4: Verification

The installer verifies all components:

- All 7 symlinks resolve correctly
- MCP server runs from its dedicated venv
- PyYAML is importable by `python3`
- `python3` command is available (hooks depend on it)

## Platform Detection

The installer auto-detects your platform:

```
+---------------------------------------------+
|  uname == Darwin?                           |
|    YES --> macOS (iCloud vault path)        |
|    NO  --> /proc/version contains microsoft?|
|              YES --> WSL (Windows-side vault)|
|              NO  --> Linux (local vault)     |
+---------------------------------------------+
```

On WSL, the installer resolves the Windows username via `cmd.exe` to locate the correct vault path under `/mnt/c/Users/`.

## Verification

After installation, confirm everything works:

```bash
# Check symlinks
ls -la ~/.claude/settings.json
ls -la ~/.claude/commands
ls -la ~/.claude/agents

# Check MCP server
cd ~/agents/mcp-server && .venv/bin/python server.py --help

# Check PyYAML
python3 -c "import yaml; print('OK')"

# Launch Claude Code
claude
```

!!! success "Expected output"
    - All three `ls -la` commands show symlinks pointing to `~/agents/claude-config/...`
    - PyYAML prints `OK`
    - `claude` launches and typing `/` lists all slash commands (orchestrate, quick, pr, learn, metrics, etc.)

You should see all slash commands available (type `/` to list them).

## Updating

After pulling config changes from git:

```bash
cd ~/agents && git pull
cd claude-config && ./install.sh
```

The installer is idempotent -- it skips existing correct symlinks and only updates what changed. Existing non-symlink files are backed up to `~/.claude/config-backup-{timestamp}/` before replacement.

!!! warning "Always re-run install.sh after pulling"
    New commands, agents, or hooks may have been added. The symlinks themselves persist, but dependency versions or new plugin requirements might need updating.

## Troubleshooting

!!! tip "Quick diagnostic"
    Run `./install.sh` again -- it is idempotent and will report exactly which components are healthy and which need attention.

| Problem | Solution |
|---------|----------|
| `python3 not found` | Install Python 3.10+ or create alias: `alias python3=python` |
| `pip not found` | Install pip: `python3 -m ensurepip` or `apt install python3-pip` |
| MCP server fails | Check venv: `~/agents/mcp-server/.venv/bin/python -c "import mcp"` |
| PyYAML install fails (PEP 668) | The installer tries `--user --break-system-packages` automatically. If still failing: `apt install python3-yaml` |
| Broken symlinks after git pull | Re-run `./install.sh` to repair |
