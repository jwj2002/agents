---
name: ops
description: "Hardened pipeline for OPS/infra/data work — the missing /orchestrate-equivalent for non-code tasks (DB backup/restore, migrations, systemd/deploy, data slicing, secret ops). Forces a deterministic done-oracle to exist BEFORE execution, wraps every blocking call in `timeout`, verifies the postcondition, and routes irreversible work to supervised-only. Use whenever you'd spawn an agent (or run commands) against live infra. Loads fresh at invocation (decay-proof) and is enforced by the ops_spawn_guard PreToolUse hook."
---

# /ops — Bounded, Verified Ops Execution

**Why this exists.** `/orchestrate` is hardened because every code task reduces
to one universal oracle: the test suite (green = done). **Ops work has no
universal oracle** — each task has a *bespoke* postcondition — so raw Agent/Task
spawns on ops/data work hang: open-ended task + no definition-of-done + no
stop-after-N on live infra. This skill supplies the missing structure: it cannot
*invent* the oracle (it's bespoke), so it **forces you to declare one** and
refuses to execute without it. Companion enforcement: the `ops_spawn_guard`
PreToolUse hook blocks any ops-flavored spawn lacking the `OPS-BOUNDED:` contract
this skill emits. Provenance: buddy `feedback-ad-hoc-agent-hangs.md` (ops agents
hung 3× in one session under rules-only guidance — "loaded ≠ followed").

Policy: `rules/agent-delegation-contract.md` (ops flavor), `rules/orchestration-concurrency.md`.

## Usage
```
/ops "back up the jns buddy db and verify the dump"
/ops "deploy the frontend build to jns and confirm the site serves"
/ops "slice locomo10.json to a 1-conversation canary fixture"
```
For a read-only status check, this is overkill — just run it. Use `/ops` for any
task that **writes to or operates live infra**, or any data-wrangling an agent
could loop on without a stop condition.

## Deterministic workflow

### Step 1 — Classify risk (sets the route)
| Class | Examples | Route |
|-------|----------|-------|
| **READ-ONLY** | status, audit, `SELECT`, `is-active`, log read | autonomous, light oracle |
| **REVERSIBLE** | backup, deploy, restart, data-slice, additive migration | autonomous-bounded (Steps 2–6) |
| **IRREVERSIBLE** | prod `DROP`/`TRUNCATE`/`DELETE`, restore-OVER-prod, secret rotation, destructive migration | **SUPERVISED ONLY** — STOP, do not autonomously spawn |

IRREVERSIBLE → present the plan + oracle to the human and run it **step-by-step
with them present**. Never fire it through a background agent. (Matches the
`autonomous-run` stop-gate + delegation-contract "confirm before hard-to-reverse".)

### Step 2 — PREFLIGHT (fail fast; most hangs are missing prereqs)
Before any execution, assert — and STOP with a clear report if any fails:
- Target reachable (`ssh <host> true`, DB `SELECT 1`, endpoint `curl -sf`).
- Every input/fixture present (the canary hang was a missing/ malformed input).
- Required tools installed on the target (`command -v pg_dump`, etc.).
- For writes: confirm you are pointed at the **intended** resource (echo the DSN
  host / systemd unit / target path) — never discover it mid-run.

### Step 3 — DECLARE THE ORACLE (the gate — no oracle, no run)
Write the **deterministic postcondition** that means "done." It must be a
command-checkable boolean, not a vibe. If you cannot write one, that is the
signal to **supervise, not automate** — fall back to Step 1 IRREVERSIBLE handling.
Examples:
- Backup → `pg_restore --list dump | grep -c TABLE` == source table count **AND** `stat -c%s dump` > floor.
- Restore-to-scratch → scratch schema hash == prod schema hash; row counts within tolerance. **NEVER restore over prod.**
- Deploy → `systemctl is-active <unit>` == `active` **AND** `curl -sf <health>` == 200 **AND** artifact mtime > deploy-start.
- Data slice → output validates against the **handed-in** schema **AND** `count(sessions)` == expected.
- Migration → `dbmate status` shows applied **AND** a `SELECT` on the new object succeeds.

### Step 4 — EXECUTE (bounded; delegate REVERSIBLE, supervise IRREVERSIBLE)
For READ-ONLY / REVERSIBLE, dispatch the **`ops` typed agent** (carries the
prod-write quality contract: single-owner, soft-delete-not-destructive,
verify-after-write). The dispatch prompt MUST:
- Wrap **every** blocking call in `timeout <N>` (ssh, psql, pg_dump, curl,
  long evals) — the #1 hang fix.
- Carry an **iteration cap + STOP-condition** ("if X fails in 2 tries, STOP and
  report"); never an open loop.
- Hand the agent the **exact target spec/shape** — never make it *discover* a
  data shape or schema.
- Include the bounded-execution contract line (this is what satisfies the
  `ops_spawn_guard` hook):
  ```
  OPS-BOUNDED: timeout=<N>s oracle="<the Step 3 postcondition>"
  ```

**Dispatch (REVERSIBLE):**
```
subagent_type: ops
run_in_background: true            # background by default; stay available
prompt: <PREFLIGHT results + exact commands (each timeout-wrapped) +
         the Step 3 oracle + iteration cap + OPS-BOUNDED line>
```
IRREVERSIBLE → do NOT dispatch; walk the human through it one step at a time.

### Step 5 — VERIFY (run the oracle; this is the terminal condition)
Re-read/re-query the resource and evaluate the Step 3 oracle deterministically.
PASS = done. FAIL = report what diverged + the evidence; do **not** silently
retry past the iteration cap. Verification is the stop — not "the agent said it
finished."

### Step 6 — REPORT
Compact verdict: class, oracle, PASS/FAIL + the evidence (command output), and
prod-state confirmation. Never a log dump.

## Liveness tripwire (standing, all `/ops` dispatches)
Watch the background agent's output-file mtime. Stale (no progress past the
declared timeout window) + no matching process → **kill it and finish
deterministically** (its committed work survives). A hung ops agent is the exact
failure this skill prevents — don't wait it out.

## Hard rules (what this skill enforces)
- **No oracle, no run.** Step 3 is a gate, not a formality.
- **Every blocking call wrapped in `timeout`.** Open loops on live infra hang.
- **Hand the shape, never discover it.** Exact target spec into the prompt.
- **IRREVERSIBLE = supervised only.** Never background a destructive op.
- **Soft-delete / additive over destructive** (delegation-contract ops flavor);
  `is_active=false`/archive over `DELETE`/`DROP`.
- **Verify after writing**, single-owner per resource, sequential writes.
- The `OPS-BOUNDED:` line is mandatory on every ops dispatch — the
  `ops_spawn_guard` hook blocks the spawn without it.
