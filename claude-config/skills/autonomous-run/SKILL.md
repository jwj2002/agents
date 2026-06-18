---
name: autonomous-run
description: Run a SCOPED queue of GitHub issues end-to-end unattended — a multi-issue meta-loop that composes /orchestrate + ship-by-default + a complexity-gated adversarial review, with checkpoint, single-owner, stop-gate, and Telegram-heartbeat discipline baked in. Use only on an explicit, user-opted-in issue list; never "do everything."
---

# autonomous-run

This is the **meta-loop that runs a queue** of issues unattended. It does not
re-implement the per-issue work — it *composes* the existing tools:

- `/orchestrate` does ONE issue (MAP → PLAN → PATCH → PROVE).
- `/ship` ships ONE diff (commit → PR → review → merge → verify → prune).
- `adversarial-review-gated` is the non-blocking review gate (Codex-first,
  internal fallback).

`autonomous-run` wraps a loop around those for a **bounded list of issues**,
adding the discipline a human-unattended run needs: checkpointing across
compaction, a single-owner-per-resource guard, explicit stop gates, and a
Telegram status heartbeat. If you only have one issue, use `/orchestrate` +
`/ship` directly — this skill earns its keep only across a multi-issue queue.

The per-run plan files under
`~/.claude/projects/<project>/memory/autonomous-run-*.md` are *instances* of
this protocol (a specific queue, on a specific day). This skill is the reusable
protocol they all follow.

## 1. When to use — opt-in, scoped only

- Use ONLY when the user has explicitly opted in to an autonomous run AND
  handed you a **SCOPED queue** — a concrete issue list (`#1958 #1951 #1953 …`)
  or a named umbrella whose children are enumerated.
- **Never run "do everything" / "fix all the things."** An unbounded scope has
  no stop condition and no review budget. If the scope is vague, stop and ask
  for the issue list before starting.
- This is high-stakes (it merges to `main` without a human at the keyboard).
  Treat ambiguity as a stop, not a guess.

## 2. The loop (per issue)

For each issue in the queue, in order:

1. **Branch fresh** from `origin/main` (`git fetch origin && git checkout -b
   {type}/issue-{N}-{slug} origin/main`). One branch = one PR = one issue.
2. **Implement via `/orchestrate`** (it self-routes SIMPLE vs COMPLEX). Let it
   run PROVE; do not declare done on "files present" — the change must be wired
   through its entrypoint and exercised with evidence. Any per-issue work you
   delegate *outside* `/orchestrate` (an ad-hoc coding spawn) goes to the
   **`impl`** agent type, which carries the implementation flavor of
   `rules/agent-delegation-contract.md` (derived from
   `rules/code-quality-standards.md`) — so the same quality bar reaches ad-hoc
   spawns, not just the orchestrate workers.
3. **Complexity-gated review.** Before merge, classify the diff by
   `~/.claude/rules/implementation-routing.md` tier:
   - TRIVIAL / SIMPLE, no risk class → no mandatory review (spot-check only).
   - MODERATE+ **or** any risk class (auth, payments, migrations, data-loss,
     secrets, contracts) → run the **`adversarial-review-gated`** skill
     (Codex-first, internal fallback). It NEVER blocks the run on Codex
     availability and always writes a verdict. `REVISE` → fix then re-gate;
     `PROCEED` → continue.
4. **Ship by default** — per `~/agents/claude-config/rules/git-workflow.md`:
   commit → push → PR (`Closes #N`) → merge (squash) → sync `main` →
   post-merge verify → prune branch → close/update the issue. CI-red,
   REQUEST_CHANGES, and conflicts are "fix then ship," not stop gates.
5. **On failure** (3 failed attempts on one issue, or a blocker outside this
   issue's scope): **do not halt the whole run.** Investigate enough to write a
   crisp cause, **file a follow-up issue**, ping the blocker (see §6), and
   **continue to the next queue item.** One stuck issue must not strand the rest.

## 3. Checkpoint discipline (survive compaction)

A long run will cross a context-compaction boundary. Make it survivable:

- **Checkpoint to memory at every issue completion** — update the run's
  `autonomous-run-*.md` memory (or run-state file) with: shipped PRs, the next
  un-shipped issue, and any load-bearing facts discovered (CI quirks, deferred
  follow-ups). This is the resume anchor.
- **70% context-gate.** Read `used_pct` from
  `~/.claude/ctx_state/<session_id>.json` (the model can't introspect its own
  context %). When it exceeds **~70%**: (1) write the continue-memory FIRST,
  (2) `/compact` (or hand off), (3) resume from the checkpoint — SessionStart
  restores the run state. Send the checkpoint heartbeat (§6) as you do this.
- The chat is ephemeral; memory is the durable carry. Never let the only record
  of "where the run is" live in the conversation buffer.

## 4. Stop conditions + kill-switch

Ship-by-default has hard limits. **Stop and ping (§6), do NOT merge,** when:

- The user says "hold" / "PR only" / "I'll merge this one" / "stop."
- A **documented stop gate** in the issue or run plan fires (explicit human
  sign-off, release coordination).
- The op is **irreversible / destructive in prod** — e.g. a destructive
  Supabase migration, data-loss, secret rotation. (Additive/safe migrations
  ship.)
- A **budget or scope cap** is hit (issue count, token/cost ceiling, or
  wall-clock the user set).
- **3 failed attempts** on one issue → stop *that issue* (file follow-up,
  continue the run per §2.5); repeated systemic failure → stop the *run*.

**Abort path:** on a stop-the-run signal, finish-or-revert the in-flight issue
to a clean state (never leave `main` red), write the checkpoint, ping the
final-status heartbeat, and stop. Do not start the next issue.

## 5. GATE — single owner per resource

**Never double-dispatch two agents at the same target resource** — the same
DB / schema, the same repo branch, or the same host/service. Concurrent writers
to one resource cause churn and lost work (two agents on the same jns canary
caused exactly this). Rules:

- One issue = one branch = one owning agent. Parallel issues get **separate
  worktrees** and must not touch the same files (serialize same-file work).
- Before dispatching a worker against a shared resource (prod DB, a host, a
  service), confirm no other agent in the run currently owns it.
- Memory/SQL writes through the harness are SEQUENTIAL — one
  `propose_memory_write` per turn; never fan out parallel writes.

## 6. Telegram comms heartbeat

Send **concise one-line** status pings to **Telegram** (Jason's active
monitoring channel) — **NOT email.** Terse by default; the user replies
"details #X" to expand. Sign as the agent ("Claude Code"), not "Mavis."
(See `feedback-status-channel-telegram-not-gmail`.)

Trigger points and exact shapes:

| Trigger | Message |
|---|---|
| Run start | `▶️ Autonomous run: N issues [...]. Ship-by-default, review-gate on MODERATE+.` |
| Each ship | `✅ #X merged — <title>.` |
| Blocker / failure | `⚠️ #X — <reason>; <action>.` |
| Decision needed | `❓ #X needs your call: <one-line question>.` |
| Checkpoint / compact | `💾 70% ctx — checkpointed, compacting, resuming.` |
| Complete / stop | `🏁 Done: N shipped, M blocked. Summary in memory.` |

Send via the Telegram MCP plugin (`telegram@claude-plugins-official`), or curl
`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage -d
chat_id=<TELEGRAM_ALLOWED_CHAT_IDS>` with the token from the project `.env`.
Gmail is fallback ONLY if Telegram is genuinely unreachable mid-session — flag
that explicitly and switch back on next restart. Verify `enabledPlugins` in
`~/agents/claude-config/settings.json` before falling back.

## 7. Comms → memory (propose, never auto-commit)

Monitor the Telegram exchange both ways, and treat the two directions
differently:

- **Outbound pings are run telemetry** — fire-and-forget status, not memory.
- **The user's replies are candidate memory** — a reply may carry a decision, a
  correction, a new fact, or feedback that should persist. Do NOT silently act
  on or write it. Route every such reply through **propose → confirm**: surface
  what you'd record, and write only on explicit confirmation.
- Telegram is a noisy channel; auto-committing from it would repeat the failure
  where a bogus `relationship_to_user` fact nearly got written. Same precision
  discipline applies: verify before persist.
- This is one input channel into the broader conversation-capture /
  project-knowledge event-log substrate — keep the propose-then-confirm contract
  consistent with how that substrate ingests other channels.

## Notes

- Operating model behind this skill: `~/projects/buddy/config/identity/BASE.md`
  (background-by-default, one-at-a-time, 70% context-gate, ship-by-default).
- Delegation quality contract: typed agents (`impl`/`research`/`ops`) carry the
  matching flavor of `rules/agent-delegation-contract.md`, which derives from
  `rules/code-quality-standards.md`. Prefer the typed agent over a bare
  `general-purpose` spawn so the standard is auto-applied.
- The review gate is `adversarial-review-gated` — do not call
  `/codex:adversarial-review` directly in an unattended run (it has no fallback
  and will stall the gate if Codex is down).
- Per-run instances live as `autonomous-run-<date>-*.md` memories; this skill is
  the protocol they instantiate. Update the instance, not this file, with
  run-specific queue/state.
