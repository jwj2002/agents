# Cost-Telemetry v0 — Activation Runbook

**Purpose.** Turn the cost-telemetry pipeline from **dormant** (runs only when you type
`python3 usage_collect.py`) to **live** (auto-runs on a schedule + on session events + weekly email),
in the safe order Codex's activation-safety review recommended (#339). Execute this **together, one
step at a time**, running each step's *Verify* before moving on.

**Current state (before this runbook).** Nothing auto-fires. The only live hook today is
`usage_account_capture.py` (SessionStart, from #310). The number-correctness (#337) and activation-
safety (#339) fixes are merged. Manual collection is clean, honest, and safe.

**Host.** This Mac (`jns-mac`). Paths assume `~/agents` (source) symlinked into `~/.claude`.

## ⚠ Reversibility — read before starting
Every step is reversible **except one**:
- **Step 8 (first email) is a one-way door** — a sent message can't be un-sent (it lands in Sent Items
  and may be server-indexed even if deleted). It is last, gated, and hard-coded to
  `jjob@vital-enterprises.com`.
- **Data steps (3, 4) are reversible only by deleting files** (`~/.claude/telemetry/<host>/usage.jsonl`,
  `cost-telemetry.state`, etc.) — that restores state, but the observation already happened.
- **Config/code steps (4 launchd, 5–6 hooks, 7 wiring) revert perfectly** — `launchctl unload`, remove
  the hook line from `settings.json`, or `git revert`.

Each step below lists its exact **Rollback**.

---

## Step 0 — Pre-flight (no live change)
```bash
cd ~/agents && git fetch origin && git checkout main && git pull --ff-only origin main
./claude-config/install.sh                       # refresh symlinks (idempotent)
(cd claude-config && python3 -m pytest tests/ -q) # expect: all green
ls -l ~/.claude/hooks/cost_collect_request.py     # symlink resolves (Stop hook target)
test -f ~/agents/claude-config/scripts/cost_telemetry_freshness.py && echo "freshness present"
```
**Verify:** tests green; both files resolve. **Rollback:** n/a (read-only).

---

## Step 1 — (already done) hard gates fixed
#337 (numbers) + #339 (secret-log, lock, hook exit-0, capture hardening, email recipient guard) are
merged. Nothing to do. **Verify:** `git log --oneline -5` shows `6d2ed38` (#339) and `b71ab13` (#337).

---

## Step 2 — Manual smoke into a TEMP dir (no live change)
```bash
SMOKE=$(mktemp -d /tmp/cost-telemetry-activate.XXXXXX)
PYTHONPATH=~/agents/claude-config/scripts python3 \
  ~/agents/claude-config/scripts/usage_collect.py --full --base-dir "$SMOKE"
wc -l "$SMOKE/usage.jsonl"; ls "$SMOKE"
```
**Verify:** exit 0/1, `usage.jsonl` has rows, no `usage-quarantine.jsonl` (or only known-after-#309).
**Rollback:** `rm -rf "$SMOKE"` (temp only — never touches live).

---

## Step 3 — One manual REAL run → creates live state
This writes to the **live** telemetry dir for the first time (the launchd job needs `cost-telemetry.state`
to exist before Step 6's freshness check is meaningful).
```bash
PYTHONPATH=~/agents/claude-config/scripts python3 \
  ~/agents/claude-config/scripts/usage_collect.py --full
ls -l ~/.claude/telemetry/jns-mac/usage.jsonl
cat ~/.claude/telemetry/cost-telemetry.state   # confirm last_success is set
```
**Verify:** `usage.jsonl` exists; `cost-telemetry.state` has a recent `last_success`.
**Rollback (delete files):** `rm ~/.claude/telemetry/jns-mac/usage.jsonl ~/.claude/telemetry/cost-telemetry.state`
**Reversible:** by deletion only (data was observed).

---

## Step 4 — Enable the launchd collector (every 6h)
```bash
bash ~/agents/claude-config/scripts/install_cost_telemetry.sh load
launchctl list | grep cost-telemetry            # confirm loaded
```
**Verify:** the job appears in `launchctl list`. Wait/observe one cycle (or trigger manually) and check
`~/.claude/logs/cost-telemetry.log` for a clean run; confirm the plist injects **no** API key.
**Rollback (clean):** `bash ~/agents/claude-config/scripts/install_cost_telemetry.sh unload`
**Reversible:** yes (unload removes the job; runs that already happened wrote deletable data).

---

## Step 5 — SKIP (superseded by the timer + transcript-mtime)
**Decided 2026-06-08: do not wire the Stop hook.** It was conceived as a "session ended" marker, but the
Claude Code `Stop` hook fires at the end of **every turn** (not at session end), and nothing consumes
the marker — the launchd collector (Step 4) runs on its own 6h timer and mines transcript JSONLs by
**mtime**, which already captures **resumed** sessions (transcript keeps appending) and **multi-day**
sessions (a still-open transcript keeps a fresh mtime → its running cost is collected every cycle, not
only when it ends). So the timer + transcript is strictly more reliable than any hook here.

If lower-than-6h latency is ever wanted, wire a **`SessionEnd`** hook (the correct "ended" event) to
`launchctl kickstart` the job — **not** the per-turn `Stop` hook. `cost_collect_request.py` is left in
the repo, dormant, with a docstring documenting this.

---

## Step 6 — Enable the SessionStart freshness watchdog (`--hook`, always exits 0)
Edit `~/.claude/settings.json` → `hooks.SessionStart[*].hooks` array, **append**:
```json
{ "type": "command", "command": "python3 /Users/jasonjob/agents/claude-config/scripts/cost_telemetry_freshness.py --hook" }
```
(absolute path — there is no `~/.claude/scripts` symlink). Only enable **after** Step 3 created
`cost-telemetry.state`, so it doesn't warn on every start.
**Verify:** start a session; it begins normally (the `--hook` flag guarantees exit 0 even if stale —
verify with `python3 .../cost_telemetry_freshness.py --hook; echo $?` → `0`).
**Rollback:** delete that one array entry.
**Reversible:** yes (config-only; `--hook` can never fail a session start).

---

## Step 7 — Wire billing capture (DEFERRED CODE — do together)
**This is a code change**, not a config flip, and it changes what the **already-live** capture hook
writes. I will: write the patch (`resolve_billing_type(os.environ, ~/.claude.json)` into
`usage_account_capture.build_entry`, so an env API key → `metered` instead of inheriting a stale OAuth
`subscription`), add a test (API-key-while-OAuth-max → `metered`), open a PR for your approval, merge,
then `./claude-config/install.sh` (the hook is symlinked → live immediately).
**Verify:** start a session with `ANTHROPIC_API_KEY` set; confirm the new `account-map.jsonl` line shows
`billing_type: "metered"` (not `subscription`). Start one without it → `subscription`.
**Rollback:** `git revert` the PR + `install.sh` (the live hook reverts with the symlink).
**Reversible:** yes (code revert).

---

## Step 8 — First real email (ONE-WAY DOOR — last, gated)
**This is a code change + the only irreversible step.** I will first add the state-persisting wrapper
Codex asked for (loads/saves collector state for once-per-ISO-week idempotency, hard-codes recipient to
`jjob@vital-enterprises.com`, refuses override, sends only the generated report after a size/sensitivity
check), open a PR, merge. Then we trigger **one** real send and confirm.
```bash
# (exact trigger command finalized when the wrapper lands; runs send_weekly via ~/agents/m365/send_mail.py)
```
**Verify:** exactly one email arrives at `jjob@vital-enterprises.com`; re-running the same week sends
nothing (idempotent); a send failure returns exit 4 and does **not** block collection.
**Rollback:** disable the weekly trigger / `git revert` the wrapper. **The sent email itself cannot be
un-sent** — this is why it's last and gated. Confirm explicitly before triggering.

---

## Done-state
- launchd collector running every 6h, writing `~/.claude/telemetry/jns-mac/usage.jsonl`.
- Stop + SessionStart hooks live (both fail-safe; never block a session).
- Live sessions tagged with correct `billing_type` at capture time.
- Weekly report email to `jjob@vital-enterprises.com`, idempotent.
- Full rollback for everything except already-sent email: unload launchd, strip the two hook entries
  from `settings.json`, `git revert` Steps 7–8, optionally `rm` the telemetry shards.

## Abort at any point
Stop after any step; the pipeline is usable manually regardless of how far activation got. To fully
return to "dormant": `install_cost_telemetry.sh unload`, remove the Step 5/6 entries from
`settings.json`, and (if Steps 7–8 merged) `git revert` them.
