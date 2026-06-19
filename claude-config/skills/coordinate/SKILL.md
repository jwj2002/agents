---
name: coordinate
description: "Coordinator / meta-supervisor for multi-unit work — delegate EACH unit (issue or task) to a fresh worktree-isolated orchestrator agent, enforce WIP/single-owner, and stay at the integration layer. Use whenever you'd otherwise be tempted to run a pipeline or write code inline: 2+ issues in parallel, or any single non-trivial unit you should delegate rather than conduct. Loads fresh at invocation (decay-proof) and structurally forces the delegation."
---

# /coordinate — Delegate, Don't Conduct

**Role: COORDINATOR (meta-supervisor). You never implement code or conduct a
pipeline yourself — you spawn agents and integrate their results.** This skill is
deliberately structural: it loads fresh the moment you invoke it, so the
delegation decision is made at peak salience and *forced by the steps below* —
not left to a long session's decaying judgment (the exact failure this prevents).

This is the layer **above** `/orchestrate`: `/orchestrate <issue>` conducts ONE
issue and casts the invoker as the conductor (the trap). `/coordinate` spawns a
fresh orchestrator agent **per unit** and keeps you at the integration layer.
Topology: **you (meta-supervisor) → per-unit orchestrator agents → workers.**

Policy (the *why*): `rules/orchestration-concurrency.md`, `rules/agent-delegation-contract.md`.

## Usage
```
/coordinate 2133 2134               # two GitHub issues, in parallel
/coordinate 2133                    # one issue — still delegated, not conducted
/coordinate "task A" "task B"       # ad-hoc units
```
Skip for TRIVIAL one-liners (use `/quick`). Use whenever you'd otherwise conduct inline.

## Deterministic workflow

### Step 1 — Parse units + assert role
List the units from the args. State in one line: *"Coordinator mode: N units —
delegating each to a fresh orchestrator agent; staying at the integration layer."*
If at any point you're about to edit code or run a pipeline phase yourself, STOP
and spawn an agent — that is the whole point.

### Step 2 — Pre-flight (the coordinator's only real judgment): WIP + single-owner
- **WIP ≤ 2 units in flight per project.** More than 2 → dispatch the first 2,
  QUEUE the rest, pull when one finishes.
- **Single-owner per mutable resource.** For each pair of units, check for
  overlapping files / DB write targets / branches (read the issue bodies; `grep`
  the likely paths). If two would write the SAME file → assign it to ONE owner,
  tell the other to import/avoid it. If they share a DB write target → SERIALIZE
  them (not parallel). Disjoint units run in parallel.
- **≤ 3 active projects** across all coordinate runs.
- Report the WIP plan + any single-owner assignments in one line before dispatch.

### Step 3 — Dispatch one fresh orchestrator agent per in-flight unit
Spawn via the Agent tool (≤2 concurrently):
```
subagent_type: general-purpose          # or orchestrate-* for a single code issue
isolation: "worktree"                    # MANDATORY — parallel agents must not share a tree
model: "opus"                            # COMPLEX / risk-class; omit for simple
run_in_background: true
prompt: <orchestrator template below, filled for this unit>
```

**Orchestrator agent prompt template (fill per unit):**
> You are the per-unit orchestrator for **<UNIT>** — own it end-to-end: ground →
> implement → PROVE → adversarial review → STOP at merge-ready. Do NOT merge (the
> coordinator sequences merges).
> SETUP (worktree): `git fetch origin && git checkout -b <branch> origin/main`.
> GROUND FIRST (read, cite path:line): the issue/spec + the code you'll touch.
> SCOPE: <the unit's acceptance criteria>. SINGLE-OWNER: <file(s) assigned to or
> kept away from this unit>.
> PROVE: test on the LOCAL/test DB only (NEVER prod); apply the quality contract
> (ruff, LR-001, real tests, completion gate).
> REVIEW: Codex adversarial review — `unset CODEX_COMPANION_SESSION_ID
> CLAUDE_PLUGIN_DATA` then `codex exec --skip-git-repo-check --sandbox read-only
> "$(cat /tmp/r-<unit>.txt)" </dev/null > /tmp/r-<unit>-out.log 2>&1`. Risk-class
> (auth/crypto/migrations/money/secrets/contracts) → MANDATORY. REVISE → fix
> within scope (≤2 bounded attempts, else report) → re-review.
> STOP at merge-ready: commit (conventional, `Closes #N`), push, open PR. Do NOT
> merge; do NOT apply migrations to prod.
> RETURN ≤1.5K tokens: PROVE result, review verdict (source/RISK/decision), the
> EXACT files changed (for overlap-check), branch + PR URL, prod-untouched
> confirmation. Verified-vs-assumed; surface blockers loudly.

### Step 4 — Collect verdicts (stay at coordination)
Record each verdict as the agent returns (you're notified). Do NOT implement or
fix anything yourself. A unit whose own bounded attempts couldn't clear a REVISE
is a **new round** — re-dispatch a *fresh* agent for it; never conduct the fix inline.

### Step 5 — Integrate (the coordinator's job)
- **Overlap-check** the returned file lists. Two PRs touching one file → merge one,
  rebase the other.
- Merge in dependency order (substrate/migrations before consumers):
  `gh pr merge <N> --squash --delete-branch` (`--admin` if CI is billing-blocked
  and local evidence is green).
- Post-merge: verify each landed on main, close issues, tick any umbrella tracker,
  prune worktrees, pull the next queued unit if a WIP slot freed.

### Step 6 — Report
One compact status: merged / merge-ready / blocked per unit, with SHAs + any
follow-ups filed. Never a file dump.

## Hard rules (what this skill enforces)
- You are the COORDINATOR — you do not implement or conduct. Tempted to edit code
  or run a pipeline phase? Spawn an agent.
- Every spawned agent: **fresh, worktree-isolated, bounded** (stop-condition +
  test oracle), **stops at merge-ready**.
- WIP ≤2 units/project, ≤3 projects, single-owner per resource, integrate sequentially.
- Never two concurrent merges into overlapping files.
