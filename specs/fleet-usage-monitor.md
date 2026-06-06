# Fleet Usage Monitor — multi-provider token tracking, normalization & reporting

**Date:** 2026-06-06
**Owner:** scratch (build); the collectors run per-host across the fleet
**Status:** draft v1 (lean spec — `~/agents` velocity rules; aim ≤2 review rounds)

## §0 Goal & non-goals
**Goal.** Track and monitor AI token usage across the fleet, sliceable by **account · computer (host) ·
project · model · task · provider** (Claude *and* ChatGPT/Codex), normalize it into **efficiency
metrics** ($/PR, $/file-changed, $/task-tier, cache-%), and surface it in a **reporting view** (a static
HTML trend report first) so workflow can be understood and optimized — e.g. *"this tier of task does
fine on Sonnet; stop spending Opus on it."*

**Non-goals (v1).** Real-time streaming; OTEL collectors (transcripts/sessions ALREADY carry the data —
see §2, confirmed 2026-06-06); the rigorous quality/validation anchor (that is the separate
`telemetry-validation` spec — this cost/efficiency view ships without proven quality). Benchmark-4 /
cross-dev comparison stays out (k-anon, §6.2 of team-knowledge).

## §1 Dimensions (the query axes)
Every normalized record carries all six so any can be a group-by:
`account · computer · project · model · task · provider`.

## §2 Data sources — already on disk, zero deploy (verified 2026-06-06)
### 2.1 Claude — `~/.claude/projects/<proj>/<session>.jsonl`
Each assistant message has `message.usage.{input_tokens, output_tokens, cache_read_input_tokens,
cache_creation_input_tokens}`, `message.model`, `cwd`, `gitBranch`, `sessionId`, `timestamp`.
→ model ✅ · project (from `cwd`) ✅ · task (`gitBranch`, when session runs in-repo — see §4.3) ✅ ·
tokens ✅ · computer (collector host) ✅ · **account ❌ → §4.1**.
Measured: one Opus session ≈ 954M tokens ≈ **$2,159** (cache-aware); cache saved ≈ **$12,480**.

### 2.2 Codex/ChatGPT — `~/.codex/sessions/**/*.jsonl`
`{type, timestamp, payload}` lines: `session_meta`, `turn_context` (model e.g. `gpt-5.5`, `cwd`),
`token_count` events (19 in a sample session). `~/.codex/auth.json` holds the OpenAI identity.
→ model ✅ · project (`cwd`) ✅ · tokens (`token_count`) ✅ · computer ✅ · **account ⚠️ → §4.1** ·
**task (no branch) → §4.3**.
Measured (server-a, 95 sessions): ≈ 2.40B tokens ≈ **$5,275**.

## §3 Normalized record (both collectors emit the same shape)
```
{provider, account, computer, project, model, task,
 input, output, cache_read, cache_creation, cost_usd,
 ts, session_id, files_changed?, task_tier?}
```
Written per host to `telemetry/<host>/usage.jsonl` (append-only shard — the SAME per-host shard
pattern the failures telemetry already uses). Cross-fleet aggregation = concatenate shards. No secrets
ever enter a shard (auth.json is read for identity only, never the key — reuses the §229 raw-capture ban).

## §4 Closing the two capture gaps (everything else is mined from §2)
### 4.1 Account (the one genuinely-new capture)
- **Claude:** account/org is NOT in the transcript. Capture via a SessionStart hook that records
  `{sessionId, account, org, ts}` to a local sidecar (`~/.claude/telemetry/account-map.jsonl`); the
  collector joins `sessionId → account`. Sessions predating the hook are `account: "unknown"` (honest,
  never guessed).
- **Codex:** read `auth.json` (current identity) and `session_meta` (per-session if present).
### 4.2 Computer (host) — free
The collector runs per-host and stamps its own hostname via `lib/project_resolver.get_host_name()`
(the shard path `telemetry/<host>/` already encodes it). No new capture.
### 4.3 Task attribution
- **Claude:** `gitBranch` when the session's `cwd` IS the target repo → free per-task split. **Caveat
  (observed):** cross-repo work via absolute paths (session `cwd` not the edited repo) collapses
  everything under one branch. Fallbacks: an explicit task tag at task start, else `task: unattributed`.
- **Codex:** `cwd` + timestamp correlation to a Claude task, OR tag at the `codex exec` wrapper (we
  control it). 
- `task_tier` (TRIVIAL/SIMPLE/COMPLEX) derived from `files_changed` bands (§5) or the issue label.

## §5 Normalization — the actual point (raw tokens-by-project is misleading)
A bigger project legitimately costs more, so efficiency is **cost per unit of work**:
- **$/PR**, **$/file-changed**, **$/issue**, **$/task-tier** — `files_changed` joined from git history per
  merge commit (the 2-3-file vs 10-15-file distinction).
- **cache_read %** and **"$ saved by cache"** — the single biggest cost lever (see §2.1); always shown.
- **model mix per project** + the **right-sizing opportunity**: $ that would be saved if mis-tiered
  tasks moved to a cheaper model. The right-sizing recommendation needs cost-by-(model×tier) AND a
  quality proxy (rework rate — Codex rounds / follow-up fixes); cheapest-always is wrong without it.

## §6 Pricing
Extend `claude-config/scripts/otel_sink.py:PRICES` (Claude-only today) with OpenAI/Codex model rates
(`gpt-5.5`, …), cache-aware per provider. Reuse `token_collector.session_cost` strict behavior: an
unknown model is a LOUD error, never a silent zero. Sanity-check Claude rates against real Opus 4.8
billing so the $ is trustworthy.

## §7 Reporting — Tier A (static HTML) first
A roll-up script reads all `usage.jsonl` shards → a **self-contained HTML page** (inline Chart.js, no
server) with:
- cost by project, **normalized $/PR trend** over time;
- model mix per project + right-sizing opportunities;
- **cache efficiency** trend;
- **by-account** and **by-computer** breakdowns;
- cost by **task-tier** (small vs large patches).

The **data layer (shards) is identical** for later view tiers, so the view is swappable:
- **Tier B (later):** local read-only **FastAPI** dashboard with live filters (fits the Vite/FastAPI
  stack) — only if interactive slicing is wanted.

## §8 Build order
1. **Claude collector** — transcript → normalized shard (productionize the 2026-06-06 prototype).
2. **Codex collector** — `~/.codex/sessions/**` → normalized shard.
3. **Pricing** — both providers in `PRICES`.
4. **Account capture** — SessionStart hook + sidecar; collector join.
5. **Aggregator + normalization** — join git `files_changed`; compute $/PR, $/file, $/tier, cache-%.
6. **Static HTML trend report** (Tier A).
7. *(later)* right-sizing analysis (cost×rework by model×tier); FastAPI dashboard (Tier B).

## §9 Open decisions (confirm before/while building)
- Reporting starts at **Tier A static HTML** (confirmed).
- **Account split required** in v1 (confirmed) — drives §4.1.
- **Computer/host required** in v1 (confirmed) — §4.2 (free).
- Cross-repo task attribution: accept `unattributed` for cross-repo abs-path sessions in v1, or add the
  task tag now? (Recommend: accept `unattributed` in v1, add tag if it proves common.)
