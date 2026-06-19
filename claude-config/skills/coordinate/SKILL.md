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
  them. Disjoint units run in parallel.
- **≤ 3 active projects** across all coordinate runs.
- Classify each in-flight unit as **ISOLATED** (no file overlap with other
  in-flight units) or **OVERLAPPING** — this sets its merge policy (Step 3/5).
- Report the WIP plan + single-owner assignments + each unit's isolated/overlapping
  classification in one line before dispatch.

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
> implement → PROVE → adversarial review → ship-or-stop (per merge policy below).
> SETUP (worktree): `git fetch origin && git checkout -b <branch> origin/main`.
> GROUND FIRST (read, cite path:line): the issue/spec + the code you'll touch.
> SCOPE: <the unit's acceptance criteria>. SINGLE-OWNER: <file(s) assigned to or
> kept away from this unit>.
> PROVE: test on the LOCAL/test DB only (NEVER prod); apply the quality contract
> (ruff, LR-001, real tests, completion gate). Save test/lint output to a
> validation log for the ship gate.
> REVIEW: Codex adversarial review — `unset CODEX_COMPANION_SESSION_ID
> CLAUDE_PLUGIN_DATA` then `codex exec --skip-git-repo-check --sandbox read-only
> "$(cat /tmp/r-<unit>.txt)" </dev/null > /tmp/r-<unit>-out.log 2>&1`. Risk-class
> (auth/crypto/migrations/money/secrets/contracts) → MANDATORY. REVISE → fix
> within scope (≤2 bounded attempts, else report) → re-review.
> **MERGE POLICY (set by the coordinator):**
> - **ISOLATED** → SELF-SHIP once PROVE PASS + review PROCEED, via the canonical
>   ship script: `~/agents/bin/agent-git ship --issue <N> --summary "<s>"
>   --test-evidence "<e>" --validation-log <log>` (preflight + ship gates +
>   squash-merge + post-merge verify + prune). Do NOT use raw `gh pr merge` if the
>   ship wrapper exists.
> - **OVERLAPPING** → STOP at merge-ready: commit (conventional, `Closes #N`),
>   push, open PR, do NOT merge (the coordinator integrates).
> Either way: NEVER apply migrations to prod.
> RETURN ≤1.5K tokens: PROVE result, review verdict (source/RISK/decision), the
> EXACT files changed (for overlap-check), branch + PR URL (+ merge SHA if you
> self-shipped), prod-untouched confirmation. Verified-vs-assumed; surface blockers loudly.

### Step 4 — Collect verdicts (stay at coordination)
Record each verdict as the agent returns (you're notified). Do NOT implement or
fix anything yourself. A unit whose own bounded attempts couldn't clear a REVISE
is a **new round** — re-dispatch a *fresh* agent for it; never conduct the fix inline.

### Step 5 — Integrate (merge ownership follows the *view* required)
**Who merges:**
- **ISOLATED unit** → the orchestrator agent **self-shipped** (it has both gates +
  the full view of its own change). You only **verify it landed** on main.
- **OVERLAPPING units** → agents stopped at merge-ready; **you integrate** (only
  you see both units): overlap-check the returned file lists, order the merges
  (substrate / migrations before consumers).

**How you merge (clean vs conflicted):**
- **Clean, non-conflicting** → the coordinator merges the EXISTING PR
  **server-side**: `gh pr merge <N> --squash --delete-branch` (`--admin` if CI is
  billing-blocked and the agent's gates are already green). Server-side is correct
  here because it touches **no local tree** — so it can't disturb a running
  parallel agent or trip on a dirty/anomalous main tree. **Do NOT use
  `agent-git ship` for the coordinator merge** — it requires a *clean* local tree
  and operates on the *current branch*, so it is the AGENT's **self-ship** tool
  (Step 3, ISOLATED case: the agent is in its own clean worktree), not the
  coordinator's existing-PR merge. After merge: `~/agents/bin/agent-git cleanup
  --branch <b>` to prune.
- **Needs conflict resolution / non-trivial rebase** (= editing code) → DELEGATE
  to a fresh agent. You DECIDE the order and that a conflict exists; an agent
  RESOLVES it. Resolving a conflict inline in a long, decaying session is the trap.
- After ANY merge (self-shipped, performed, or delegated): verify it landed on
  main, close the issue, tick any umbrella tracker, prune the worktree
  (`~/agents/bin/agent-git cleanup --branch <b>`), pull the next queued unit if a
  WIP slot freed.

### Step 6 — Report
One compact status: merged / merge-ready / blocked per unit, with SHAs + any
follow-ups filed. Never a file dump.

## Hard rules (what this skill enforces)
- You are the COORDINATOR — you do not implement or conduct. Tempted to edit code
  or run a pipeline phase (including resolving a merge conflict)? Spawn an agent.
- Every spawned agent: **fresh, worktree-isolated, bounded** (stop-condition +
  test oracle). ISOLATED units self-ship; OVERLAPPING units stop at merge-ready.
- Merges go through the canonical ship script (`agent-git ship` / `cleanup`),
  not raw `gh pr merge`, wherever the repo provides it.
- WIP ≤2 units/project, ≤3 projects, single-owner per resource, integrate
  sequentially. Never two concurrent merges into overlapping files.
