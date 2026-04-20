---
title: Phase 0 — Usage Report (90-day window)
created: 2026-04-19
window: 90 days
sample: 2278 transcript files in ~/.claude/projects/
purpose: Original intent was to inform Phase 3 cuts. Methodology turned out to be unreliable — see "Methodology gap" below.
status: Phase 3 cuts DEFERRED. Findings on Codex and hooks remain valid.
---

# Phase 0 — Usage Report

## Methodology gap (added after first pass)

The first pass counted artifact usage by single-pattern signal:
- Sub-agents → only `subagent_type` field matches
- Skills → only Skill tool calls
- Commands → only `<command-name>` tags

This **undercounted real usage** because:
- Orchestrate dispatches MAP/PLAN/PATCH/PROVE as `Task(description='MAP for issue N', ...)` against the `general-purpose` agent, with the agent `.md` file embedded as the prompt body. None of those count as `subagent_type` matches.
- Skills can also be referenced inline (script paths read, agent prompts include skill content).
- Commands have similar embedding patterns.

**Decision:** defer Phase 3 (artifact pruning) entirely. Add a structured usage logger to the orchestrate skill in a future pass to get reliable signal.

The findings below on **Codex** and **hooks** remain valid — those have unambiguous invocation patterns.

Mined `~/.claude/projects/**/*.jsonl` for the last 90 days.

## Slash commands (`<command-name>` invocations)

| Command | Count | Disposition |
|---|---|---|
| /dashboard | 5 | **Keep** — anchor of new daily workflow |
| /pdf | 3 | Keep — niche but useful |
| /review-session | 1 | Keep — weekly ritual |
| /orchestrate | 1 | Keep — invoked via Skill more often (see below) |
| /buddy | 1 | Project-specific, ignore |

**Custom commands with zero hits in 90d:** `/bug`, `/feature`, `/feature-from-spec`, `/frontend-design`, `/learn`, `/metrics`, `/pr`, `/quick`, `/scaffold-module`, `/scaffold-project`, `/seed`, `/spec-draft`, `/spec-review`, `/test-plan`

→ These are mostly invoked through the Skill tool instead (see next section).

## Skill tool invocations

| Skill | Count | Disposition |
|---|---|---|
| orchestrate | 68 | **Keep** — primary workflow engine |
| spec-review | 22 | **Keep** — actively used |
| spec-draft | 18 | **Keep** — actively used |
| learn | 4 | Keep — low volume but valuable |
| frontend-design | 2 | Archive candidate |
| deep-review | 2 | Archive candidate |
| update-config | 1 | Keep — system management |
| dashboard | 1 | **Keep** — about to become daily anchor |

**Skills with zero invocations in 90d:** capture, inbox, pdf, project, review-session, test-plan
- `pdf` is invoked as `/pdf` not as a Skill (3 hits as command). Keep.
- `capture`, `inbox`, `project`, `review-session` are about to become daily workflow → **keep, do not cut**.
- `test-plan` — archive candidate.

## Sub-agent (Agent tool) invocations

| Sub-agent | Count | Disposition |
|---|---|---|
| general-purpose | 94 | **Keep** (built-in) |
| code-reviewer | 3 | **Keep** — invoked by orchestrate |
| claude-code-guide | 3 | Keep (built-in) |

**Custom sub-agents with ZERO invocations in 90d:**
- `map`
- `plan`
- `patch`
- `prove`
- `contract`
- `discuss`
- `plan-checker`
- `spec-reviewer`
- `test-planner`
- `map-plan`

→ These are referenced from inside the orchestrate skill prompts, but the Agent tool itself never received `subagent_type="map"` etc. Either:
- They're inlined into orchestrate prompts (the skill calls them as personas, not as separate Agent invocations) — in which case the `.md` files are documentation, not actively dispatched agents
- Or the orchestrate skill needs to start using them as actual sub-agents

**Action:** archive 9 of 10 custom sub-agent files; keep `code-reviewer.md` (the only one that matches actual Agent invocations). If the orchestrate skill internally references the others as documentation, leave a `_archived/` reference path.

## Hooks

| Hook | Count | Disposition |
|---|---|---|
| verify_completion.py | 4,286 | **Keep** — high value |
| notify_completion.py | 3,117 | **Keep** — high value |
| state_manager.py | 470 | **Keep** |
| precompact_checkpoint.py | 443 | **Keep** |
| sessionstart_restore_state.py | 194 | **Keep** — daily workflow anchor |
| worktree_manager.py | 145 | **Keep** |
| context_monitor.py | 80 | **Keep** |
| session_end_context_update.py | 50 | **Keep** |
| load_learning_rules.py | 41 | **Keep** |

**All 9 hooks fire. None cut.** The earlier "9→4" target was wrong — the data shows every hook is active.

## Codex delegation

| Codex skill | Count |
|---|---|
| codex:rescue | 642 |
| codex:setup | 270 |
| codex:adversarial-review | 270 |
| codex:review | 197 |

**Total: 1,379 Codex invocations in 90 days.** Codex is a force multiplier — keep all of it as-is.

## Behavioral evals (E01–E15)

1,603 mentions of eval IDs across transcripts. Need a deeper pass to count *fired* (PROVE invocation) vs *referenced* (in prompts/rules). For now, **keep all evals** — the catalog is small (15) and the cost is just file size.

## Tool usage (top 12)

| Tool | Count |
|---|---|
| Read | 23,050 |
| Bash | 19,053 |
| Edit | 7,057 |
| Grep | 6,563 |
| Glob | 3,737 |
| Write | 3,108 |
| WebSearch | 1,078 |
| TaskUpdate | 955 |
| WebFetch | 486 |
| TaskCreate | 477 |
| Agent | 415 |
| Skill | 121 |

---

## Validated findings (kept)

- **Codex usage is enormous** — 1,379 invocations in 90 days. Don't touch the codex plugin.
- **All 9 hooks fire heavily.** Original "9→4" target was wrong. Leave hooks alone.
- **Behavioral evals (15) are cheap to keep.** Revisit when PROVE-fire data is available.

## Findings retracted

- Sub-agent counts (`subagent_type`-only) understated real usage
- Slash command counts (`<command-name>`-only) understated real usage
- Skill counts are partially reliable but unused-looking skills (capture/inbox/project/review-session) are about to be activated by the new daily workflow anyway

## Future work (out of current scope)

When pruning revisits, the right approach is **add a usage logger to orchestrate** (write a one-line JSONL entry per agent dispatch) so future cut decisions have ground truth. Until then, do not prune by guess.

---

## Pre-consolidation baseline (for rollback reference)

- `~/agents` HEAD before Phase 1: `fec005d` ("fix: only surface commits newer than last focus update (#74)")
- `~/projects/flotilla` HEAD before Phase 1: `e786eac` ("feat: ProjectView Context section — focus, next steps, blockers (#199)")

If Phase 1+ goes wrong, restore both repos to the SHAs above.
