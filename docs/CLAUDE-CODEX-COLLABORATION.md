# Claude + Codex Collaboration Model

This repo is used by **two** coding agents — Anthropic **Claude Code** and OpenAI
**Codex** — plus the human owner. These principles keep both agents first-class.
The guiding rule: **do not make Claude worse to make Codex better, or Codex worse
to preserve Claude conventions.** Shared abstractions should improve both.

## 1. `AGENTS.md` is shared project policy

`AGENTS.md` is the canonical, agent-neutral instruction file for a project.
`CLAUDE.md` and Codex config (`.codex/config.toml`, Codex skills) are **adapters**
around it, not competing sources of truth.

- Put shared behavior in `AGENTS.md`.
- `CLAUDE.md` carries the minimum load-bearing context Claude must always see
  (so Claude is never starved if the harness does not auto-load `AGENTS.md`)
  plus Claude-only notes — it does **not** duplicate `AGENTS.md` wholesale.
- Codex config carries Codex-only adapters (command policy, skill links).

## 2. Shared behavior is CLI-first

For behavior both agents need, implement it once in **repo-native CLI/script
code** (shell or Python), then wrap it with a thin Claude command or Codex skill.
This minimizes prompt-instruction drift and token cost, and gives deterministic,
testable output. Example: the `agent-git` helpers — both agents call the same
binary instead of each re-deriving the git process from prose.

## 3. Per-agent capabilities are allowed — but must be documented

A capability that only one agent can use today is fine. Document it as such (see
`docs/AGENT-CAPABILITIES.md`) so the asymmetry is intentional and visible, not a
silent gap. Example: `/orchestrate` is Claude-only (depends on `.claude/agents/`
subagent dispatch).

## 4. New agent workflows declare their surface

When adding an agent workflow, document:

- whether **Claude** can use it,
- whether **Codex** can use it,
- a **parity note** if one side cannot use it yet (and what it would take).

## 5. Changing shared instructions means verifying both surfaces

When you modify shared policy, check it still holds on **both** sides:

- **Claude:** `CLAUDE.md`, `.claude/rules/`, slash commands (if relevant).
- **Codex:** `AGENTS.md`, `.codex/config.toml`, Codex skills/agents (if relevant).

## 6. Prefer deterministic CLI output for high-frequency workflows

For anything run often, a short deterministic CLI is better than a long prompt
instruction: lower token cost, less drift, and it can be unit-tested. Reserve
prose instructions for judgment-heavy, low-frequency guidance.

## 7. Shared abstractions must improve both agents

Never regress one agent to help the other. If a change helps Codex but weakens
Claude's guaranteed context (or vice versa), redesign it so both benefit — e.g.
keep `AGENTS.md` canonical *and* keep `CLAUDE.md` self-sufficient for the minimum
Claude must see.

## Skill portability contract

Claude and Codex read the same `SKILL.md` format, so portable skills are
**symlinked** (not copied) into both runtimes for zero drift. The gate is
`claude-config/scripts/check-skill-portability.sh`:

- exit `0` — portable; linked into Codex.
- exit `1` — Claude-only (references a Claude-only harness construct); **skipped**
  for Codex, not an error.
- exit `2` — invalid/usage error; a real failure.

Both the installer (`codex-config/install.sh`) and CI
(`.github/workflows/validate.yml`) honor this contract.
