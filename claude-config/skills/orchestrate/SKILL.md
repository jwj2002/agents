---
name: orchestrate
version: 4.0
description: Multi-agent workflow with self-learning capabilities
---

# Orchestrate Skill (v3.0)

Issue-driven workflow with pattern learning and outcome tracking.

## What's New in v3.0

- **Self-learning**: Agents read patterns.md before each run
- **Outcome tracking**: PROVE records success/failure to memory/
- **Slimmed agents**: 50% smaller, faster context loading
- **Shared behaviors**: All agents inherit from _base.md

## What's New in v5

- **SIMPLE pipeline compressed**: PLAN-CHECK dropped from SIMPLE/MODERATE.
  Default cost is now 3 phases (MAP-PLAN → PATCH → PROVE) instead of 5–6.
  Codex adversarial review (post-PROVE, automatic for MODERATE+) picks up
  what PATCH missed.
- **COMPLEX pipeline unchanged**: full MAP → PLAN → CONTRACT → PLAN-CHECK
  → PATCH → PROVE retained — the rigor pays off on high-risk work.

## Workflow

```
Issue → Classify → Branch → Agents → Verify → Record → PR
```

## Agent Sequence

**TRIVIAL**:
1. MAP-PLAN → `.agents/outputs/map-plan-{issue}-{date}.md`
2. PATCH → `.agents/outputs/patch-{issue}-{date}.md`
3. PROVE-lite → `.agents/outputs/prove-{issue}-{date}.md`

**SIMPLE / MODERATE** (compressed in v5 — PLAN-CHECK dropped):
1. MAP-PLAN → `.agents/outputs/map-plan-{issue}-{date}.md`
2. CONTRACT (only if fullstack) → `.agents/outputs/contract-{issue}-{date}.md`
3. TEST-PLANNER (only if `--with-tests`) → `.agents/outputs/test-plan-{issue}-{date}.md`
4. PATCH → `.agents/outputs/patch-{issue}-{date}.md`
5. PROVE → `.agents/outputs/prove-{issue}-{date}.md`

→ Default cost: 3 phases (MAP-PLAN → PATCH → PROVE). Adds CONTRACT for
fullstack, TEST-PLANNER for explicit test planning. PATCH catches plan
defects fast enough that a separate PLAN-CHECK step rarely earns its cost
on SIMPLE work — Codex review after PROVE picks up what PATCH missed.

**COMPLEX / FULLSTACK** (full pipeline retained — high-risk changes):
1. MAP → `.agents/outputs/map-{issue}-{date}.md`
2. PLAN → `.agents/outputs/plan-{issue}-{date}.md`
3. TEST-PLANNER (if `--with-tests`) → `.agents/outputs/test-plan-{issue}-{date}.md`
4. CONTRACT (MANDATORY if fullstack) → `.agents/outputs/contract-{issue}-{date}.md`
5. PLAN-CHECK → `.agents/outputs/plan-check-{issue}-{date}.md`
6. PATCH
7. PROVE

**Recommended**: Use `--with-tests` for issues involving calculations, formulas, or complex business rules.

**Parallel execution**:
- MAP fan-out: backend/frontend/tests exploration (COMPLEX)
- MAP+TEST-PLANNER (COMPLEX)
- PLAN-CHECK+TEST-PLANNER (with --with-tests)
- Speculative PATCH alongside PLAN-CHECK (TRIVIAL/SIMPLE backend-only)
- Parallel fullstack PATCH: backend+frontend via CONTRACT
- PROVE verification fan-out: lint/test/build (fullstack)

## Worktree Isolation (`--parallel`)

Run multiple orchestrate sessions simultaneously:

```bash
/orchestrate 42 --parallel    # Session 1: worktree at .worktrees/issue-42/
/orchestrate 57 --parallel    # Session 2: worktree at .worktrees/issue-57/
```

Each session gets its own:
- Working directory (`.worktrees/issue-{N}/`)
- Git index (no staging conflicts)
- Artifacts (`.agents/outputs/` inside worktree)
- Feature branch

Post-merge cleanup: `/pr --merge` removes the worktree automatically.

## Session Initialization (Step -1)

**Before spawning any agents**, load context for this issue:

1. Load behavioral evals: `cat ~/.claude/rules/behavioral-evals.md` (if exists)
2. Check for prior failures on this issue:
   ```bash
   grep "\"issue\":${ISSUE}" .claude/memory/failures.jsonl 2>/dev/null
   ```
   - If found: load failure context, identify root cause, brief the MAP/PATCH agent
   - Include in prompt: `## Prior Failure\nRoot cause: X. Prevention: Y.`
3. Check for existing artifacts: `ls .agents/outputs/*-${ISSUE}-*.md 2>/dev/null`
   - If found: determine which phase to resume from (skip completed phases)
4. Check recent branch activity: `git log --oneline -5`
5. Report to user:
   ```
   Issue #N: [prior attempts: X | first attempt]
   [Last failure: ROOT_CAUSE | No prior failures]
   [Resuming from PHASE | Starting fresh]
   ```

---

## Learning Loop

After each issue:
1. PROVE records outcome to `.claude/memory/metrics.jsonl`
2. If BLOCKED, records failure to `.claude/memory/failures.jsonl`
3. Weekly `/learn` extracts patterns
4. Agents read `patterns.md` on next run

## Key Files

- `.claude/agents/_base.md` — Shared agent behaviors
- `.claude/memory/patterns.md` — Learned patterns
- `.claude/memory/failures.jsonl` — Failure log
- `.claude/memory/metrics.jsonl` — Success metrics

## Usage

```bash
/orchestrate 184
/orchestrate 184 --with-tests    # Include TEST-PLANNER phase
/orchestrate 184 --parallel      # Run in isolated worktree
/orchestrate 184 --parallel --resume  # Resume in existing worktree
```

See `.claude/commands/orchestrate.md` for full details.
