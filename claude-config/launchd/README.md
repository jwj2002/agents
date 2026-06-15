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

> **Win C (resolved, #350)**: the perpetually-dirty working tree caused by
> `telemetry/<host>/*.jsonl` shards is fixed — shards are gitignored + local-only
> (REC 0.1's OTEL hub is deferred indefinitely, so telemetry stays off the code
> repo). This script does not stash, commit, or push shards.

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

---

## Memory-health jobs (`com.claude-memory-trend` + `com.claude-memory-audit`)

The two halves of the memory-recall measurement loop (close the loop on the
write-heavy / read-light store — see `docs/memory-review.md`). Both are local
(the metrics read the local transcript store + `~/.claude/projects/*/memory/`,
which a cloud routine can't see). Neither runs at load.

### `com.claude-memory-trend.plist` — **weekly** (Mondays 09:00)

Runs the deterministic
[`../scripts/memory_audit_metrics.py`](../scripts/memory_audit_metrics.py)
(no LLM): counts memory writes, fact-body reads, and `memory recall`
invocations over the trailing 7 days, plus total/cold facts, and appends one
dated row to **`~/.claude/memory-trend.jsonl`** (local; never in the repo).
This is the cheap signal for *is the write:read ratio falling*.

### `com.claude-memory-audit.plist` — **monthly** (1st @ 10:00)

Runs the full qualitative audit headlessly: `claude --print` on
[`../../docs/memory-audit.md`](../../docs/memory-audit.md), writing a dated
graded report to **`~/.claude/memory-reports/memory-report-<host>-<date>.{md,html}`**.
(The same `claude --print` headless mechanism the poller uses for `/learn`.)

### Deploy / reload

```bash
for p in com.claude-memory-trend com.claude-memory-audit; do
  cp "claude-config/launchd/$p.plist" ~/Library/LaunchAgents/
  launchctl unload "$HOME/Library/LaunchAgents/$p.plist" 2>/dev/null || true
  launchctl load   "$HOME/Library/LaunchAgents/$p.plist"
done
```

### Observe

```bash
launchctl list | grep claude-memory                 # loaded?
cat ~/.claude/memory-trend.jsonl                     # the weekly trend (ratio over time)
tail -f ~/Library/Logs/claude-learn/memory-trend.log # weekly run log
ls ~/.claude/memory-reports/                         # monthly graded reports
```

Run once on demand:

```bash
python3 ~/agents/claude-config/scripts/memory_audit_metrics.py --days 7   # weekly metrics row
claude --print "$(cat ~/agents/docs/memory-audit.md)"                      # full audit (writes a report)
```

---

## Cost-telemetry weekly report (`com.cost-telemetry-report-weekly`)

**Weekly** (Mondays 09:05, aligned with the memory jobs). Builds the cost report
locally (`~/.claude/cost-reports/cost-report-<host>-<week>.{html,md}`) via
`scripts/cost_report_weekly.py`, then **emails it per this machine's config**.

Email is **per-machine** — set the account to send from + recipient on each
computer (the repo is shared, so this config is machine-local, never committed):

```bash
python3 ~/agents/claude-config/scripts/usage_email.py --configure      # guided: type + sender + recipient
python3 ~/agents/claude-config/scripts/usage_email.py --check-config    # show resolved transport + creds
python3 ~/agents/claude-config/scripts/usage_email.py --test-send       # send a one-off test now
```

Config lives at `~/.claude/cost-telemetry/email.json` (chmod 600; template:
`claude-config/cost-telemetry-email.example.json`). Account types:

| type | sends as | creds (default) |
|---|---|---|
| `gmail` | the token's Google account (e.g. `jasonwadejob@gmail.com`) | `~/agents/google/token.json` |
| `m365` | the creds' `sender_upn` (e.g. `jjob@vital-enterprises.com`) | `~/.claude/m365/agent.json` |
| `none` | — (no email; **local report still written**) | — |

If email is `none`/disabled/unconfigured, the weekly job still writes the local
report and exits 0 — it never blocks.

### Deploy / reload

```bash
p=com.cost-telemetry-report-weekly
cp "claude-config/launchd/$p.plist" ~/Library/LaunchAgents/
launchctl unload "$HOME/Library/LaunchAgents/$p.plist" 2>/dev/null || true
launchctl load   "$HOME/Library/LaunchAgents/$p.plist"
```

### Observe

```bash
launchctl list | grep cost-telemetry-report
tail -f ~/Library/Logs/claude-learn/cost-report.log
ls ~/.claude/cost-reports/                     # the local report archive
python3 ~/agents/claude-config/scripts/cost_report_weekly.py   # run once on demand
```

---

## Coding-memory ingest (`com.coding-memory-ingest`)

**Daily** (`StartInterval 86400`, `RunAtLoad` false). Keeps the personal
coding-memory store on jns fresh without a manual `bin/coding-memory ingest`.
Logic lives in
[`../scripts/coding-memory-ingest.sh`](../scripts/coding-memory-ingest.sh) so it
is editable without redeploying the plist.

Each run executes `bin/coding-memory ingest` with the **default personal sources
only** (`agents`, `buddy`) — no `--source` override, so strict residency holds
(work memory uses a separate, never-bridged store). Embedding happens on jns; the
laptop only parses + dispatches over SSH (key auth — no credentials in the plist).
On error (e.g. jns unreachable) it logs and exits non-zero; launchd retries on the
next interval — no tight loop.

### Deploy / reload

```bash
p=com.coding-memory-ingest
cp "claude-config/launchd/$p.plist" ~/Library/LaunchAgents/
launchctl unload "$HOME/Library/LaunchAgents/$p.plist" 2>/dev/null || true
launchctl load   "$HOME/Library/LaunchAgents/$p.plist"
```

### Observe

```bash
launchctl list | grep coding-memory-ingest
tail -f ~/.claude/logs/coding-memory-ingest.log
bash ~/agents/claude-config/scripts/coding-memory-ingest.sh   # run once on demand
~/agents/bin/coding-memory stats                              # rows per namespace
```
