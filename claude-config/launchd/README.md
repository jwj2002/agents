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

> **Win C (deferred)**: fixing the perpetually-dirty working tree caused by
> `telemetry/<host>/*.jsonl` shards is tracked under issue #220 / REC 0.1 and
> will be resolved in lockstep with that coordination effort. This script does
> not stash or commit shards.

### Why the script is separate

Keeping the logic in `learn-gate-poller.sh` rather than inline in the plist
means it is readable, syntax-checkable (`bash -n`), and editable without
re-deploying the plist. Editing only the script requires no `launchctl` reload.

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
