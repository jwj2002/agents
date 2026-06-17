# Skill Surfaces

This repo uses skills as reusable workflows for Claude Code and Codex. A skill
is shared only when its `SKILL.md` does not assume a tool-specific harness.

## Locations

| Scope | Location | Purpose |
|---|---|---|
| Claude global | `~/.claude/skills` -> `~/agents/claude-config/skills` | Claude-installed user skills |
| Codex compatibility | `~/.codex/skills/<name>` | Existing local Codex skill discovery used by this repo |
| Codex documented user | `~/.agents/skills/<name>` | Current documented Codex user skill location |
| Repo-local shared | `.agents/skills/<name>` | Project-specific skills committed with a repo |

`codex-config/install.sh` links shared skills into both Codex user locations.
This is intentional: `~/.codex/skills` preserves current local behavior, while
`~/.agents/skills` follows the documented Codex discovery path.

## Classification

| Skill source | Classification | Rule |
|---|---|---|
| `codex-config/skills/dev-prompt-architect` | Codex-native, Claude-paired | Codex packaging for the development prompt Q&A workflow |
| `codex-config/skills/technical-spec-review` | Codex-native, shared-capable | Authored for Codex, usable where the task matches |
| `claude-config/skills/action` | Shared | Thin CLI wrapper; passes portability lint |
| `claude-config/skills/dashboard` | Shared | Thin CLI wrapper; passes portability lint |
| `claude-config/skills/decision` | Shared | Thin CLI wrapper; passes portability lint |
| `claude-config/skills/deep-review` | Shared | Instruction-only review workflow; passes portability lint |
| `claude-config/skills/dev-prompt-architect` | Claude-native, Codex-paired | Claude packaging for the same development prompt Q&A workflow |
| `claude-config/skills/email-digest` | Shared | Thin workflow wrapper; passes portability lint |
| `claude-config/skills/pdf` | Shared | Tool workflow; passes portability lint |
| `claude-config/skills/project` | Shared | Thin CLI wrapper; passes portability lint |
| `claude-config/skills/review-session` | Shared | Thin CLI wrapper; passes portability lint |
| `claude-config/skills/transcribe-meeting` | Shared | CLI workflow; passes portability lint |

Any future Claude skill that references Claude-only constructs must remain
Claude-only and fail portability lint instead of being linked into Codex.

## Portability Gate

Run:

```bash
claude-config/scripts/check-skill-portability.sh path/to/SKILL.md
```

The gate rejects unambiguous Claude-only harness constructs such as
`allowed-tools`, `Task tool`, `Agent tool`, MCP tool IDs, or plan-mode-only
operations.

## Authoring Rules

- Put shared reusable workflows in skills only when they are useful beyond one
  repository.
- Put project-specific instructions in `AGENTS.md`.
- Put project-specific reusable workflows in `.agents/skills/`.
- Put Claude-only command behavior under `.claude/` or `claude-config/`.
- Put Codex-only config, hooks, and policy under `.codex/` or `codex-config/`.
