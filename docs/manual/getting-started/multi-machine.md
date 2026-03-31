# Multi-Machine Sync

The configuration framework uses symlinks and git to keep Claude Code settings identical across every development machine. Pull once, and every machine updates.

## How Sync Works

```
Machine A (edit config)          Machine B (pull to sync)
------------------------         ------------------------
~/agents/claude-config/          ~/agents/claude-config/
    |  git push                      |  git pull
    v                                v
GitHub repo ------------------> GitHub repo
                                     |
                                ./install.sh
                                     |
                                ~/.claude/ (symlinks updated)
```

Because `~/.claude/` is symlinked to the repo, a `git pull` in `~/agents/` instantly updates all configuration. Run `./install.sh` after pulling only if new dependencies or plugins were added.

## Shared vs Local

### Shared (git-tracked, synced across machines)

| Component | Path | Description |
|-----------|------|-------------|
| Agents | `claude-config/agents/` | MAP, PLAN, PATCH, PROVE definitions |
| Commands | `claude-config/commands/` | All slash commands |
| Hooks | `claude-config/hooks/` | SessionStart, PreCompact, Stop hooks |
| Rules | `claude-config/rules/` | Conditional rule files |
| Skills | `claude-config/skills/` | Multi-step workflow definitions |
| Settings | `claude-config/settings.json` | Hooks, permissions, plugins, MCP |
| Statusline | `claude-config/statusline.py` | Terminal status bar |

### Local (never synced, machine-specific)

| Component | Path | Why Local |
|-----------|------|-----------|
| `settings.local.json` | `~/.claude/settings.local.json` | MCP server paths vary by machine |
| Memory | `~/.claude/memory/` | Per-machine learned patterns |
| Projects | `~/.claude/projects/` | Session data per project |
| History | `~/.claude/history.jsonl` | Conversation history |
| Debug | `~/.claude/debug/` | Debug logs |
| State | `.agents/outputs/claude_checkpoints/` | Session-local, recreated by hooks |

!!! note "Project-level memory lives in the project repo"
    Files under `<project>/.claude/memory/` (metrics, failures, patterns) are committed to each project's own repository, not to the agents repo. They sync with the project, not with the configuration.

## Updating Shared Config

When you edit configuration on one machine:

```bash
cd ~/agents
git checkout -b config/add-new-command
# ... make changes ...
git add -A && git commit -m "feat(commands): add new slash command"
git push
```

After the PR merges, on every other machine:

```bash
cd ~/agents
git pull
~/agents/claude-config/install.sh   # only if deps changed
```

## Platform-Specific Handling

The installer adapts behavior per platform:

| Behavior | macOS | WSL | Linux |
|----------|-------|-----|-------|
| Vault path | iCloud auto-detect | Windows-side + symlink | `~/obsidian/MyVault` |
| Symlink creation | `ln -sf` | `ln -sf` | `ln -sf` |
| pip strategy | uv preferred | System pip + `--user` | uv or pip3 |
| Windows user | N/A | Auto-detected via `cmd.exe` | N/A |

!!! tip "WSL users"
    The vault directory is created on the Windows side (`/mnt/c/Users/<winuser>/obsidian/MyVault`) and symlinked into WSL. This lets Obsidian on Windows read the same vault.

## Multi-Account GitHub Setup

When working across multiple GitHub accounts on the same machine, use `gh auth` to manage account switching.

### Account Mapping

| GitHub Account | Used For | Git Email |
|---------------|----------|-----------|
| `personal-account` | Personal projects | personal@placeholder.com |
| `work-account` | Work projects | work@placeholder.com |

### Required Steps

Before any git or `gh` operation:

```bash
# 1. Check active account
gh auth status

# 2. Switch if needed
gh auth switch -u <correct_account>
```

For work repositories, always set the local git config after cloning:

```bash
git config user.name "Your Name"
git config user.email "work@placeholder.com"
```

!!! warning "Never use global git config for email"
    Always set email per-repo for work projects to avoid committing under the wrong identity.

### Project-to-Account Mapping

Maintain a mapping file (`claude-config/rules/github-accounts.md`) that maps each project path to the correct GitHub account. Agents read this file to verify the correct account is active before push operations.

| Project Path | GitHub Account |
|-------------|---------------|
| `~/projects/app-a` | `personal-account` |
| `~/projects/app-b` | `work-account` |
| `~/agents` | `personal-account` |

### Safety Rules

- Never push to a work repo while logged in as your personal account (or vice versa)
- Always verify with `gh auth status` before `git push` or `gh pr create`
- The `/pr` command checks the active account automatically

!!! warning "Multi-account gotchas"
    - Pushing to the wrong account silently succeeds but creates commits under the wrong identity
    - `git config --global user.email` applies to ALL repos -- always use per-repo config for work projects
    - `gh auth status` shows the active account but does NOT check the git email config -- verify both

## Adding a New Machine

1. Clone the repo: `git clone <repo-url> ~/agents`
2. Run installer: `cd ~/agents/claude-config && ./install.sh`
3. Create `~/.claude/settings.local.json` with machine-specific MCP paths
4. Set up `gh auth` for your GitHub account(s)
5. Verify: run `claude` and confirm all commands are available

!!! tip "Platform-specific notes"
    - **macOS**: The installer auto-detects iCloud for the Obsidian vault path. Ensure iCloud Drive is enabled in System Settings.
    - **WSL**: The vault is created on the Windows side so Obsidian for Windows can read it. The Windows username is auto-detected via `cmd.exe`.
    - **Linux**: The vault defaults to `~/obsidian/MyVault`. Install Obsidian separately if you want vault browsing.
