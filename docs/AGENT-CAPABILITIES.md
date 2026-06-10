# Agent Capabilities

This repo is the shared configuration and operations source for Claude Code and
OpenAI Codex. Claude and Codex are both first-class maintainers, but they use
different runtime surfaces.

## Shared Capabilities

- Project instructions: `AGENTS.md`
- Repo-local reusable workflows: `.agents/skills/`
- Project bootstrap: `new-project-agents.sh`
- Shared project artifacts: `.agents/outputs/`
- CLI-backed workflows: `action`, `project`, `decision`, `pulse`,
  `email-digest`, and related Python CLIs
- Parity drift report: `bin/agent-parity check`
- Validation scripts and CI in `.github/workflows/validate.yml`

Shared rules belong in `AGENTS.md` or shared skills. Do not duplicate shared
behavior into separate Claude and Codex files unless the runtimes require a
tool-specific adapter.

## Claude-Only Capabilities

- Global Claude install: `claude-config/install.sh`
- Global Claude guidance: `claude-config/CLAUDE.md`
- Claude commands: `claude-config/commands/`
- Claude subagents: `claude-config/agents/`
- Claude hooks and statusline: `claude-config/hooks/`,
  `claude-config/statusline.py`
- Claude settings: `claude-config/settings.json`
- Claude-specific project adapter: `CLAUDE.md` and `.claude/`

The current `/orchestrate` command is Claude-only. It depends on Claude slash
commands, Claude `Task(...)` subagent dispatch, `.claude/agents`, and Claude
state hooks.

## Codex-Only Capabilities

- Global Codex install: `codex-config/install.sh`
- Global Codex guidance: `codex-config/AGENTS.md` -> `~/.codex/AGENTS.md`
- Codex config template: `codex-config/config.toml.example`
- Codex lifecycle hooks: `codex-config/hooks.json` and `codex-config/hooks/`
- Codex command policy: `codex-config/rules/*.rules`
- Codex-native skills: `codex-config/skills/`
- Optional project Codex config: `.codex/config.toml`

Codex `.rules` files are Starlark command-policy files. They are not
instruction files. Prose guidance belongs in `AGENTS.md`.

Codex hooks currently cover the high-value cross-agent performance and
discipline adapters:

- `SessionStart`: bounded memory context from the shared memory store, with
  verify-against-code discipline.
- `PreCompact`: compact YAML checkpoint under
  `.agents/outputs/codex_checkpoints/PERSISTENT_STATE.yaml`.
- `PostToolUse`: context headroom warnings.
- `Stop`: unfinished-work warnings and lightweight derived telemetry.

They do not attempt to mirror Claude transcript-only hooks that depend on
Claude-specific payloads.

## Skill Support

See `docs/SKILL-SURFACES.md`.

`codex-config/install.sh` links shared skills into both:

- `~/.codex/skills/<name>` for current local compatibility
- `~/.agents/skills/<name>` for documented Codex user skill discovery

The portability gate is:

```bash
claude-config/scripts/check-skill-portability.sh path/to/SKILL.md
```

## Project Bootstrap

Default:

```bash
~/agents/new-project-agents.sh /path/to/project
```

Creates:

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/settings.json`
- `.claude/rules/project-rules.md`
- `.claude/context/project-stack.md`
- `.claude/memory/runbooks.md`
- `.agents/skills/.gitkeep`

Optional trusted Codex project config:

```bash
~/agents/new-project-agents.sh --with-codex-config /path/to/project
```

Adds:

- `.codex/config.toml`

## Local-Only Runtime State

Do not commit or edit these as shared config:

- `~/.claude/history.jsonl`
- `~/.claude/projects/`
- `~/.claude/debug/`
- `~/.claude.json`
- `~/.codex/auth.json`
- `~/.codex/history.jsonl`
- `~/.codex/sessions/`
- `~/.codex/tmp/`
- `~/.codex/rules/default.rules`
- `~/.codex/skills/.system/`

## Validation

Core local checks:

```bash
bash -n install-all.sh
bash -n claude-config/install.sh
bash -n codex-config/install.sh
bash -n new-project-agents.sh
bash -n claude-config/new-project-claude.sh
python3 -c "import json; json.load(open('claude-config/settings.json'))"
python3 -m json.tool codex-config/hooks.json >/dev/null
SETTINGS_PATH=$PWD/claude-config/settings.json python3 claude-config/scripts/validate-hooks.py
codex execpolicy check --pretty --rules codex-config/rules/shared.rules -- git status
bin/agent-parity check
```

Installer smoke:

```bash
tmp="$(mktemp -d)"
HOME="$tmp" ./codex-config/install.sh
find "$tmp/.codex" "$tmp/.agents/skills" -maxdepth 3 -type l | sort
```

Bootstrap smoke:

```bash
tmp="$(mktemp -d)"
./new-project-agents.sh "$tmp"
./new-project-agents.sh "$tmp"
./new-project-agents.sh --with-codex-config "$(mktemp -d)"
```

Python tests require `pytest`; if it is unavailable, report that explicitly
instead of claiming test coverage.

## Known Gaps

- `/orchestrate` is still Claude-only.
- Codex can maintain this repo directly, but there is no Codex-native
  orchestrate equivalent yet.
- Codex hooks cover memory, checkpointing, context, completion, and telemetry.
  They are not a full port of every Claude transcript-specific hook.
- CI installs Codex CLI only for unauthenticated policy parsing. It does not
  validate authenticated Codex sessions, app connectors, or cloud tasks.
