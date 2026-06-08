# Cost Telemetry v0 — the deliberately boring, actionable build (rev 0.3)

**Date:** 2026-06-08 · **Author:** scratch (Claude) · **Status:** DRAFT (rev 0.3, post Codex rounds 1–3)
**Builds on:** `fleet-usage-monitor.md` + `knowledgemesh/specs/telemetry-validation.md`. Supersedes deleted `telemetry-completion-plan.md`.
**⏱ Timebox: 1–2 engineering days. The LOCAL report landing is the v0 gate; anything that threatens that (email, files_changed) is cut, not grown.**

## Goal
One operational pipeline: **where tokens and money go** — per account / project / model / task — for **both
Claude and Codex** CLI usage (subscription *and* API-key/metered), plus the existing **right-sizing
recommendations**. Cost is projected at published API rates (`price_basis`); real $ for metered sessions,
projected for subscription. Banks the perishable pre-API-billing baseline now.
**"Actionable" = can surface a concrete *routing* change** ("route these N trivial/simple tasks off Opus → $X").

## Non-goals (do NOT build): waste metric · defect tracer / panel · target-promotion gate / companions · multi-host · OTEL · tool/MCP inventory. Recommendations carry a plain `diagnostic` badge — no gate machinery.

## Architecture
```
~/.claude/projects/*.jsonl ┐ usage_collect.py (launchd 6h; Stop hook only *requests*; PID-lock; incremental)
~/.codex/sessions/**/*.jsonl┴► non-throwing extract → normalize → telemetry/<host>/usage.jsonl  (+ usage-quarantine.jsonl)
                              freshness check (SessionStart + --check) → durable log + warning line
                              aggregate → report (HTML+MD)  →  [fast-follow] email
```
Source = transcript-mining (no OTEL). Persist raw tokens (re-priceable) + `cost_usd`.

---

## Deliverables

### D1 — `claude-config/scripts/usage_collect.py`
- **Reuse the collectors' PARSING helpers, but implement a NON-THROWING per-transcript extraction loop.**
  (The existing `extract_records` calls `C.session_cost(strict=…)` *inline while building each record*
  — `usage_collector_claude.py:449`, `usage_collector_codex.py:193` — so an unknown model raises before
  any rows return. v0 must not call that strict path during extraction.) Instead, per record:
  **preflight `token_collector.is_known_model(model)`**; if known → price + write to `usage.jsonl`; if
  unknown → write the row (tokens, model, no cost) to `telemetry/<host>/usage-quarantine.jsonl`, never
  calling strict cost. Result: known rows always land; unknown models never brick the run.
- **DO NOT fork the attribution state machine.** The gitBranch/SSH/command-mining/conflict-clearing/
  compaction/account-join logic in `extract_records` is hard-won; a parallel loop would silently drift.
  Either (preferred) refactor a shared `build_record(entry, …)` helper (no pricing) that BOTH the existing
  strict collector and `usage_collect` call, OR ship a **golden-parity test**: on known-model fixtures,
  `usage_collect` output must equal the existing collector's output except for the added normalized fields.
  This parity test is a required acceptance fixture — it's the guard against quietly breaking attribution.
- **PID-based, stale-aware lock** `~/.claude/telemetry/cost-telemetry.lock` (write PID): if PID alive →
  exit `0` "already running"; if PID dead or lock older than `LOCK_STALE_MIN` (default 30m) → warn,
  replace, record the recovery in `--check` + log. (A dead holder must never become a permanent off-switch.)
- **Incremental via state file** `~/.claude/telemetry/cost-telemetry.state`: process transcripts with
  mtime in `(source_watermark, run_start)`. **`source_watermark` advances to the run-start high-water mark
  once every eligible transcript is parsed into EITHER `usage.jsonl` OR quarantine** — a transcript is "done"
  when parsed, regardless of pricing outcome. **`usage_collect --reprocess-quarantine` owns retrying
  quarantined rows** after the price table is updated; the source watermark is NOT held back for them.
  `--full` forces a rescan. State also records **`last_success`** (consumed by the D6 freshness check).
- **Normalize once, here** to the D3 schema (so no downstream code guesses `None`/`""`/`"unattributed"`).
- **Exit-code table (stable):** `0` ok / no new rows · `1` partial success (≥1 quarantined) · `2` source
  unreadable · `3` stale-lock recovered-or-recovery-failed · `4` report/email failure. launchd, `--check`,
  email, and tests depend on these.
- **AC fixtures:** double/concurrent run → no dup rows (lock+dedup); unknown model → known rows written,
  bad rows quarantined, exit `1`, model named; dead-PID lock → recovered + recorded; `--reprocess-quarantine`
  prices previously-quarantined rows after PRICES update.

### D2 — Schedule + install
- `claude-config/launchd/com.cost-telemetry-collect.plist` (6h) sets **absolute python** +
  `PYTHONPATH=…/claude-config/scripts`; `install.sh` registers it (script reachable at `~/.claude/...` via
  the existing symlink scheme). Linux `cron` documented. Log → `~/.claude/logs/cost-telemetry.log`.
- **Stop hook only *requests*** — touches `~/.claude/telemetry/.collect-requested` (a <5ms marker; the
  collector consumes+clears it next run). launchd does the full scan → ~0 session-exit latency.
- `--check`: last run, shard freshness, row count, quarantined-model list, lock state.

### D3 — `usage.jsonl` record (normalized in D1)
```json
{"provider":"claude|codex","account":"<normalized id|unknown>","billing_type":"metered|subscription|unknown",
 "price_basis":"published_api_rate","price_table_version":"<PRICE_TABLE_VERSION>",
 "inference_host":"…","work_host":"…","project":"<repo|null>","task":"issue:N|<branch>|null",
 "model":"…","files_changed":N_or_null,"files_changed_source":"pr_git|session_shard|project_metrics|none",
 "input":N,"output":N,"cache_read":N,"cache_creation":N,"cost_usd":0.0_or_null,
 "session_id":"…","ts":"…Z","dedup_key":"…"}
```
- **No `billing_mode`** — real-vs-projected derived per-record from `billing_type`. **No `task_tier`** —
  tier derived downstream from `files_changed` (`usage_recommend._tier_of`).
- **`price_table_version`:** add an explicit **`PRICE_TABLE_VERSION` constant beside `otel_sink.PRICES`**
  (bump on any rate change); stamped on every row so cost is auditable/repriceable.
- `cost_usd` is `null` for quarantined (unknown-model) rows; `project`/`task` may be `null` (rendered
  "unattributed" only at the report layer).

### D7e — `files_changed` enrichment (own tested module; **half-day cap**; honesty over coverage)
- `files_changed_enrich.py`, precedence + recorded `files_changed_source`:
  (1) **`pr_git`** — PR/commit git stat (authoritative);
  (2) **`project_metrics`** — orchestrate `metrics.jsonl` by issue;
  (3) **`session_shard`** — `telemetry/<host>/sessions.jsonl` files_touched **only as last-resort AND only
  if the session has a single task** (a multi-task session would overstate per-message complexity). Dedupe
  paths, repo-files only, exclude telemetry/temp.
  (4) **`none`** → `files_changed=null`.
- **Recommendations must say "tier approximate"** unless `files_changed_source ∈ {pr_git}`. If this module
  exceeds half a day, ship v0 with `files_changed=null` everywhere and still produce model/account/project cost.

### D4 — Report (REQUIRED new report code, not just wiring)
`usage_report` today renders one total line (`usage_report.py:272`). v0 must ADD:
1. **Billing headline SPLIT** — `metered (real $)`, `subscription (projected $)`, `unknown` — three lines,
   **never a single summed total.**
2. **By model**, and **by model × tier** (tier marked approximate unless `pr_git`).
3. **By project / task** with **unattributed $ shown explicitly**.
4. **Cache %.**
5. **Attribution coverage** (% of cost with real project AND task).
6. **Quarantine summary** (count + models needing pricing).
7. **Right-sizing recommendations** with a `diagnostic` badge.
HTML + short Markdown. **AC:** mixed-billing fixture renders three separate buckets, never summed;
all-unattributed fixture renders (coverage 0) without crashing; quarantine line appears when non-empty.

### D6 — Freshness watchdog (this IS the watchdog; ~15 lines)
`cost_telemetry_freshness.py`, run from SessionStart hook + `--check`: `usage.jsonl` mtime >
`FRESHNESS_SLA_DAYS` (3) → durable line in `~/.claude/logs/cost-telemetry.log` **and** one visible
warning line. Do not wire the elaborate `watchdog.py`. **AC:** stale fixture → warning; fresh → silent;
missing shard → warning.

### D7 — Attribution coverage + metered-tag hardening (make-or-break)
- Report prints attribution coverage + unattributed $ (in D4).
- **Metered detection as a tested helper** with exact precedence (and aware that **hook env ≠ launchd env**):
  `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` present in the capture context → **`metered`** (env key beats a
  missing/ignored OAuth); valid subscription `oauthAccount` / Codex `account_id` and no key → `subscription`;
  malformed/absent `~/.claude.json` → `unknown`. **AC fixtures:** env-key→metered; sub-OAuth-no-key→subscription;
  malformed json→unknown.

### D5 — Email delivery (**FAST-FOLLOW — explicitly cut-able**)
Weekly email of the MD summary + HTML via `~/agents/m365/send_mail.py`. **Build only if D1–D4 finish inside
the timebox; the LOCAL report landing is the v0 gate, email must not consume the last reliable build hours.**
If built: idempotent (no double-send per week, tracked in state), send-failure logs + exit `4`, never blocks
collection. ⚠ Graph creds under launchd are not ambient — point at the token cache / env explicitly.

## Reconciliation (transcript-coverage, not OTEL)
Per run emit `{transcripts_seen, records_emitted, rows_quarantined, unknown_models:[…],
rows_skipped_malformed, dup_keys_skipped, attributed_cost, unattributed_cost}`; alarm if
`rows_skipped_malformed/records_emitted` exceeds a small threshold. Quarantine ≠ malformed (it's a fixable
pricing gap, replayed via `--reprocess-quarantine`).

## Known limitations (state in report): Codex attribution session-level · historical billing_type mostly unknown (sidecar began 2026-06-07) · single host jns-mac (never present as fleet) · programmatic (non-CLI) API not captured · session-shard tier is approximate.

## Build-time decisions (these are the agreed defaults; lock each in a TEST, don't expand the prose)
These are the round-4 edge decisions. They're settled here so the build doesn't re-litigate them, but
the *enforcement* is a test, not more spec:
- **Quarantine row** = `{provider, source_path, source_mtime, dedup_key, model, tokens…, attribution…,
  reason, first_seen, last_seen, attempt_count, price_table_version_seen}`. On `--reprocess-quarantine`:
  write to `usage.jsonl` only if `dedup_key` absent there, then mark the quarantine row resolved (no row
  lives in both).
- **Watermark** advances to the run-start high-water mark once every eligible transcript is parsed into
  *either* `usage.jsonl` or quarantine; `--reprocess-quarantine` owns retries (don't hold the source
  watermark back for quarantine). Stable scan boundary: process mtime `<` run-start only.
- **Freshness (D6)** keys off **collector state `last_success`** (+ pending-request age), with shard mtime
  as supporting evidence — never shard mtime alone (a successful no-new-rows run must not false-alarm).
- **Coverage** = three bucketed metrics (metered / subscription / unknown attribution coverage). Quarantine
  is reported as **token volume + model names**, never folded into cost coverage.
- **Exit codes**: stale-lock recovered + collection ok → `0` (warning in log/state); active lock → `0`;
  stale-lock recovery failed → `3`. One bad transcript → `sources_unreadable++` + partial success, not a
  whole-run `2`; `2` only if the source tree itself is unreadable. **Malformed threshold = >2%.**
- **Run stats**: `{sources_seen, sources_processed, sources_unreadable, rows_malformed, rows_known_written,
  rows_quarantined, dup_keys_skipped}`.
- **`account` canonical** = Claude `account_uuid` → Codex `account_id` → email → `unknown`; email kept out
  of the default report.
- **Stop-hook request**: the collector consumes and clears `.collect-requested`; `--check` reports pending-request age.
- **Recommendation group** is "authoritative" only if **all** contributing records are `files_changed_source=pr_git`; otherwise "tier approximate" + source counts.

## Hard kill criteria
1. First report (local is enough) doesn't drive one concrete routing/config change in 2 weeks → **stop**.
2. Attribution coverage stays low, unfixable in a day or two → fix attribution only, expand nothing.
3. "API billing coming" justifies the `billing_type`/`price_basis` fields ONLY — never new subsystems.

## Definition of done (named thresholds)
1. `usage.jsonl` emits live (incremental + PID-lock); quarantine replayable; freshness check runs; LOCAL report renders.
2. Project attribution ≥ 70% of cost; task ≥ 50%; unattributed $ reported.
3. Unknown-`billing_type` share < 10% going forward (API-key → metered).
4. Unknown models **quarantined + surfaced**; pipeline keeps emitting known rows (never bricks); exit-code table honored.
5. Report: metered-$ vs projected-$ vs unknown (separate, never summed), by model, by model×tier (marked approximate unless pr_git), project/task, cache %, coverage, quarantine summary, recommendations (diagnostic).
6. Freshness SLA 3 days → durable log + visible warning. Stale lock auto-recovers, never a permanent off-switch.
