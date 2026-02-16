# Codex Configuration

Portable Codex configuration that can be installed on any machine. Uses symlinks from `~/.codex` to this repo for shared rules and user skills while preserving local auth/history/sessions and machine-specific approval rules.

## Installation

```bash
# 1) Clone repo
git clone https://github.com/jwj2002/agents.git ~/agents

# 2) Install Codex config
~/agents/codex-config/install.sh
```

## What It Links

```text
~/.codex/rules/shared.rules      -> ~/agents/codex-config/rules/shared.rules
~/.codex/skills/user             -> ~/agents/codex-config/skills/
```

## What Stays Local

- `~/.codex/auth.json`
- `~/.codex/history.jsonl`
- `~/.codex/sessions/`
- `~/.codex/tmp/`
- `~/.codex/rules/default.rules` (machine-specific approval decisions)
- `~/.codex/skills/.system/` (system skills)

## Shared Technical Spec Review Skill

This package includes `technical-spec-review` in `skills/technical-spec-review/SKILL.md`.
Use it when you want build-readiness review and one-pass implementation risk analysis.
