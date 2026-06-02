# launchd agents

## `com.claude-learn-gate-poller.plist`

A macOS launchd job that runs the telemetry → learn maintenance loop every
**12 hours** (`StartInterval 43200`). It does not run at load (`RunAtLoad`
false); the first run is one interval after it is bootstrapped.

The job is a thin wrapper — all logic lives in
[`../scripts/learn-gate-poller.sh`](../scripts/learn-gate-poller.sh) so it can
be read, `bash -n`-checked, and edited **without re-deploying the plist**.

### What each run does

1. **Sync** — `git pull --ff-only` to pick up other machines' telemetry shards.
2. **Gate + learn** — runs `telemetry_gate.py`; if the gate trips, applies
   cross-project patterns via `claude --print "/learn --apply --cross-project
   --validate"`.
3. **Commit + push this machine's telemetry shard** — so the working tree
   returns to **clean**.

### Why step 3 (the structural fix)

Telemetry shards (`telemetry/<host>/*.jsonl`) are tracked **by design** for
cross-machine aggregation, but every session appends to them, so the repo tree
is almost always dirty. A perpetually-dirty tree is what tempted autonomous
runs to `git stash` for a clean `pull --ff-only` and then never restore —
silently burying real WIP (four orphaned stashes, cleaned up 2026-06-02).

Committing the shard here keeps the tree clean **and** shares the data, removing
the temptation to stash. Safeguards in the script:

- commits **only** `telemetry/` paths, **only** on `main` (the sanctioned
  exception to "never commit directly to main" — machine data, never code);
- pushes with a **rebase-retry** so a concurrent push doesn't strand the commit;
- every step is **non-fatal** — a network/credential failure is logged and the
  next run retries; it can never wedge the loop.

Companion behavioural rule: `rules/git-workflow.md` → "Working tree hygiene in
`~/agents`".

### Requirements

- `git push` needs credentials available to the launchd context. `bash -lc` is a
  login shell, so the `osxkeychain` git credential helper (or `gh` auth) is
  normally available. If pushes log `telemetry push failed`, check that the
  helper is configured for the user that owns the LaunchAgent.

### Deploy / reload

The plist is **not** auto-installed by `install.sh`; deploy it manually. After
editing **the plist** (not the script), redeploy and reload once:

```bash
cp claude-config/launchd/com.claude-learn-gate-poller.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.claude-learn-gate-poller.plist 2>/dev/null || true
launchctl load   ~/Library/LaunchAgents/com.claude-learn-gate-poller.plist
```

Editing **only the script** (`learn-gate-poller.sh`) needs no reload — the
plist execs it fresh each interval.

### Observe

```bash
launchctl list | grep claude-learn-gate          # is it loaded?
tail -f ~/Library/Logs/claude-learn/poller.log    # run-by-run log
```

To run once on demand (does not wait for the interval):

```bash
bash ~/agents/claude-config/scripts/learn-gate-poller.sh
```
