---
title: Agent Bridge — Telegram routing for autonomous Claude agents
status: DRAFT — pending codex adversarial review
created: 2026-05-22
author: Jason Job
related:
  - specs/path-b-migration.md
  - specs/cross-device-state.md
phase: 1 of 3 (Mavis-as-CoS — see §2)
---

# Agent Bridge — v1 Spec

> **Status (2026-05-22)**: DRAFT. All Q1–Q10 architectural decisions resolved in
> conversation 2026-05-19/22. Spec assembled from those decisions for Codex
> adversarial review before implementation issues are filed.

## TL;DR

A routing primitive that connects N autonomous Claude Code sessions to the user
via Telegram. Each session writes status to a per-agent outbox file; user
replies are written to a per-agent inbox file by a long-running bridge bot
process. The bridge is a generic routing layer — agnostic of *who's* using it
(/auto-implement, future Mavis-as-CoS, future per-client deployments).

```
   ┌─────────────────────────────────────────────────────────┐
   │  @MavisBot (one Telegram bot identity, shared token)    │
   └──────────┬──────────────────────────┬───────────────────┘
              │ Telegram I/O             │ Telegram I/O
              ↓                          ↓
   ┌──────────────────────┐    ┌────────────────────────────┐
   │  Buddy's telegram    │    │  Bridge bot (launchd)      │
   │  bot.py (existing)   │    │  ~/agents/notify/bridge_   │
   │  Meeting persona     │    │  bot.py                    │
   │  Lives in buddy      │    │  Routing primitive only    │
   └──────────────────────┘    └─────┬──────────────────────┘
                                     │  reads outbox / writes inbox
                                     ↓
              ┌──────────────────────┴──────────────────────┐
              │  ~/.claude/agent-bridge/                    │
              │    <agent-id>/inbox.jsonl   (bridge writes) │
              │    <agent-id>/outbox.jsonl  (agent writes)  │
              │    <agent-id>/.lock         (PID lock)      │
              │    <agent-id>/agent-state.json              │
              │    <agent-id>/attachments/                  │
              │  bridge.log                                 │
              │  bridge-state.json                          │
              └──────────────┬──────────────────────────────┘
                             │ notify.send / poll / wait_for_answer / listen
              ┌──────────────┴──────────────┐
              │                              │
   ┌──────────────────┐            ┌────────────────────┐
   │ /auto-implement  │            │ Future: Mavis-CoS  │
   │ skill (initial   │            │ (Phase 2+)         │
   │ consumer)        │            │                    │
   └──────────────────┘            └────────────────────┘
```

---

## §1 Workflow context

### The pain this solves

Solo developer + N AI agents has the same coordination overhead as a manager
with N reports: while AI is working, the human has idle time that's hard to
spend productively. Multiple parallel autonomous Claude sessions amplify this —
without async oversight, the user must sit at the terminal watching each
session, or accept that work proceeds blindly until session end.

The bridge gives each autonomous session a way to:

- Push status updates to the user proactively ("issue #42 done, moving to #43")
- Surface escalations with attached context (test logs, failing diffs)
- Receive instructions or unblocks asynchronously
- Operate while the user is away from the laptop

### Three-phase vision

This spec scopes Phase 1 only. Subsequent phases are explicitly out of scope
but named here so the bridge isn't accidentally designed in a way that blocks
them.

| | Phase | Role | This spec |
|---|---|---|---|
| 1 | **Message router** (this spec) | Bridge passes messages between agents and Telegram. Vault enrichment on outbound. On-demand queries on inbound. Mavis-the-persona is the messenger only. | ✅ in scope |
| 2 | **Synthesizer** (deferred) | Mavis-the-software (in Buddy) reads agent inbox/outbox files + bridge log + vault, generates summaries, cross-project rollups. Surfaces, doesn't decide. | ❌ deferred to its own spec |
| 3 | **Dispatcher** (deferred further) | Mavis takes new ideas spoken/typed, drafts issues, queues work, picks agents. Still confirms before high-stakes actions. | ❌ deferred indefinitely |

The bridge ships Phase 1's plumbing. Phase 2 builds on top by reading the
bridge's files. Phase 3 builds on Phase 2. The bridge is foundation work for a
longer-term Chief-of-Staff vision but does not commit to it.

### Personal context only

Hard line per spec §6.5 client-isolation principles from Path B:

- **In scope**: agents whose project frontmatter has `client: personal`
- **Out of scope**: client-work agents (Vital, future Tillamook). Those need
  their own bridge deployment on client-approved infrastructure with separate
  credentials, never touching `~/vaults/JNS-Personal-Vault/` or this bridge.

The bridge enforces this with a runtime check (see §9).

---

## §2 Design principles

### 2.1 Channel-agnostic content; presentation adapts

All on-demand queries (STATUS, BLOCKERS, RECENT, OPEN) and outbound messages
return **structured response objects**. Channel adapters render those objects
for their target surface — markdown + emojis + attachments for Telegram, plain
prose for voice (future), ANSI tables for terminal (future).

**Adapters MUST NOT contain query-specific logic.** Adapters MAY trim/elide
for length but MUST NOT filter content out of the response object.

This principle extends to future Mavis-CoS phases. Synthesis (Phase 2) and
dispatch (Phase 3) work follows the same content/render split.

### 2.2 Loose coupling via files

Bridge ↔ agent communication is **file-only**: no Python imports, no HTTP, no
shared in-process state. Each side reads and writes JSONL files; the
filesystem is the contract.

This is the same loose-coupling pattern Path B established (agents-repo CLIs
work against any vault; vaults are filesystem entities). It enables Mavis-buddy
to optionally read bridge files in Phase 2 without depending on the bridge's
Python code.

### 2.3 Bridge ≠ Mavis

The bridge is a routing primitive. Mavis-the-persona is the user-facing
identity. They share a Telegram bot token but are different processes with
different responsibilities. The bridge does not know about Mavis as a
software entity in v1.

### 2.4 Control layer over prompt engineering

Following the control-layer pattern (Towards Data Science 2026-05): naive
"trust the message" integrations fail in production. The bridge enforces
contracts via explicit components (InputGuard, ResponseValidator,
CircuitBreaker, RetryEngine, FallbackRouter, AuditLogger). See §8.

### 2.5 One bridge, many consumers

The bridge is agnostic of who's calling it. /auto-implement is the initial
consumer. Future consumers: Mavis-CoS (Phase 2), bare-bones notifiers, future
per-client CoS deployments. No consumer-specific logic in bridge code.

---

## §3 Architectural decisions (Q1–Q10, all resolved)

### Q1: Bot identity

**Decision**: Reuse Mavis (Buddy's existing Telegram bot) on jns-mac. Bridge
reads the same `TELEGRAM_BOT_TOKEN` Buddy uses, but via its own config file
(`~/.claude/telegram.env`) pointing to the same value. The two processes
share the bot identity at the Telegram layer but are independent at the
process layer.

**Implication for Vital-CoS (future)**: separate bot identity, separate token,
deployed on Vital-approved infrastructure. Bridge code is reused; configuration
is per-deployment.

### Q2: Bot persona name

**Decision**: Skipped — Mavis is the persona on jns-mac.

### Q3: Where bridge runs in v1

**Decision**: jns-mac, managed by launchd. v2 (deferred) would move the bridge
to jns-server when the work-laptop story ships and HTTPS-reachable bridge is
needed.

### Q4: Command set + file attachment handling

**Decision**: Minimal command set with file attachments as a first-class
orthogonal capability.

**Inbound commands → routed to agent inbox**:

| Command | Effect |
|---|---|
| `STOP` | Agent halts at next breakpoint, writes session summary, exits |
| `PAUSE` | Agent waits for `RESUME` (does not count against wall-clock budget) |
| `RESUME` | Wake the paused agent |
| `STATUS` (in agent's topic) | Agent emits current state next breakpoint |
| `ANSWER <text>` | Provide answer to an escalation question the agent is blocked on |

**On-demand queries → bridge handles directly (reads vault, no agent involvement)**:

| Command | Effect |
|---|---|
| `STATUS <project>` | Bridge reads vault note + sidecar, emits current project state |
| `BLOCKERS` | All blockers across subscribed personal projects |
| `RECENT <project>` | Last N commits from sidecar |
| `OPEN <project>` | Open issues + actions for project |

**File attachments**: Any command (or empty command + freeform text) may carry
a file attachment. Both directions. Empty-command + attached file = freeform
context delivery. See §5.

### Q5: Bridge-down failure mode

**Decision**: Hybrid soft-fail. Agent writes outbox normally; bridge catches
up on restart. Agent checks `bridge-state.json` heartbeat on each
`notify.send()` call; if stale > 5 min, logs a warning in its progress log
and surfaces "bridge appears offline; N messages queued" at session end.

### Q6: On-demand queries

**Decision**: Folded into Q4 — STATUS/BLOCKERS/RECENT/OPEN included in v1.

### Q7: Attachment retention

**Decision**: 30 days, prune on bridge startup + once daily. Configurable via
`AGENT_BRIDGE_ATTACHMENT_RETENTION_DAYS` env var. Storage at
`~/.claude/agent-bridge/<agent-id>/attachments/<msg-id>-<safe-filename>`. Mode
0600 on files; mode 0700 on dirs.

### Q8: Listen mode

**Decision**: `notify.listen(timeout_s)` included in v1. Single Bash `tail -F`
with timeout, one tool call per listening window. Enables a finished
/auto-implement session to stay alive and pick up new work via Telegram
without restarting.

### Q9: Multi-session safety

**Decision**: Lock file with PID check + stale recovery.

- Lock path: `~/.claude/agent-bridge/<agent-id>/.lock`
- Lock contents: JSON with `pid`, `session_started`, `host`, `skill_name`
- Acquire on session start; refuse to start if a live PID holds it
- Stale-PID recovery via `kill(pid, 0)` POSIX probe; overwrite stale lock + log
- Release on clean exit; finally-block guarantees

**Convention**: each Claude session uses a distinct `agent-id`. If you want two
parallel skills on the same project, give them different IDs (e.g.,
`agents-build` vs. `agents-review`).

### Q10: Logging

**Decision**: Single `bridge.log` at `~/.claude/agent-bridge/bridge.log`,
structured JSON via structlog, daily rotation via
`TimedRotatingFileHandler(when='midnight', backupCount=14)`. Configurable level
via `AGENT_BRIDGE_LOG_LEVEL`, retention via `AGENT_BRIDGE_LOG_RETENTION_DAYS`.

Per-agent message history lives in the existing inbox/outbox JSONL files —
no separate centralized message audit (avoids duplication).

---

## §4 File protocol

### 4.1 Per-agent directory layout

```
~/.claude/agent-bridge/
  <agent-id>/
    inbox.jsonl              # bridge appends, agent reads
    outbox.jsonl             # agent appends, bridge reads
    .lock                    # PID lock (see §9 in Q9)
    agent-state.json         # agent's own offset tracking + processed msg IDs
    attachments/             # mode 0700
      <msg-id>-<filename>    # mode 0600
  bridge.log                 # bridge ops events
  bridge-state.json          # bridge offsets + heartbeat ts
  registry.yaml              # agent-id ↔ Telegram topic mapping
```

### 4.2 Outbox line schema (agent → bridge)

```jsonl
{
  "id":          "01HX...",                  // ULID, agent-generated
  "ts":          "2026-05-22T16:42:00Z",     // UTC ISO-8601, second precision
  "type":        "status" | "escalate" | "error" | "summary",
  "level":       "info" | "warn" | "error",  // optional, default "info"
  "text":        "Issue #42 done, PR opened",
  "attach":      "/path/to/file" | null,
  "wait_for_answer": false | true,           // optional, escalate only
  "metadata":    { ... }                     // optional, opaque to bridge
}
```

### 4.3 Inbox line schema (bridge → agent)

```jsonl
{
  "id":          "msg-82",                   // Telegram update_id-derived
  "ts":          "2026-05-22T17:09:30Z",
  "command":     "STOP" | "PAUSE" | "RESUME" | "STATUS" | "ANSWER" | "",
  "text":        "skip pytest-43 fixture",   // caption or freeform; "" if pure command
  "attach":      "/path/to/file" | null,
  "from_chat":   "<chat-id>",                // Telegram chat ID for audit
  "from_topic":  "<topic-id>"                // Telegram topic ID
}
```

### 4.4 Agent state schema (`agent-state.json`)

```json
{
  "inbox_offset": 1234,
  "processed_msg_ids": ["msg-82", "msg-83"],
  "session_id": "01HX...",
  "last_listen_at": "2026-05-22T17:30:00Z"
}
```

### 4.5 Bridge state schema (`bridge-state.json`)

```json
{
  "heartbeat_at": "2026-05-22T17:30:05Z",   // updated every 30s
  "outbox_offsets": {
    "agents-build": 4567,
    "buddy-build": 2310
  },
  "last_telegram_update_id": 12345,
  "telegram_circuit_state": "CLOSED",
  "telegram_circuit_open_since": null
}
```

### 4.6 Registry (`registry.yaml`)

User-edited; bridge reads:

```yaml
agents-build:
  topic_id: 12
  description: "Agents repo /auto-implement runs"
  vault: JNS-Personal-Vault       # for enrichment + isolation check
buddy-build:
  topic_id: 14
  description: "Buddy /auto-implement runs"
  vault: JNS-Personal-Vault
```

Vault field is REQUIRED. Bridge refuses to start an agent whose registered
vault has `client != "personal"` (enforces §1 isolation).

### 4.7 FailureMode enum (shared with /auto-implement spec)

Common failure taxonomy used in inbox/outbox `type: "error"` lines:

```python
class FailureMode(Enum):
    # InputGuard (inbound)
    INVALID_ATTACHMENT_TYPE
    MESSAGE_TOO_LARGE
    UNKNOWN_COMMAND
    INJECTION_DETECTED
    UNAUTHORIZED_CHAT_ID

    # ResponseValidator
    MALFORMED_OUTBOX_LINE
    ATTACHMENT_NOT_FOUND
    ATTACHMENT_TOO_LARGE

    # Network / Telegram
    TELEGRAM_TIMEOUT
    TELEGRAM_RATE_LIMIT
    TELEGRAM_5XX
    CIRCUIT_OPEN

    # Filesystem
    INBOX_WRITE_FAILED
    OUTBOX_READ_FAILED

    # Isolation
    VAULT_CLIENT_MISMATCH
    VAULT_NOT_IN_REGISTRY
```

---

## §5 Bridge bot design

### 5.1 Process lifecycle

- **Startup** (launchd-managed):
  1. Read config from `~/.claude/telegram.env`
  2. Load registry from `~/.claude/agent-bridge/registry.yaml`
  3. Validate each registered vault has `client: personal` per
     `~/.claude/vault-clients.yaml` (refuse to start otherwise)
  4. Read `bridge-state.json` (resume from last offsets)
  5. Prune attachments older than retention
  6. Initialize logger + CircuitBreaker
  7. Enter main loop

- **Main loop** (single async event loop):
  - **Outbox poller** (every 1s): for each registered agent, read new lines past
    last offset; send to Telegram via §5.3 outbound pipeline; update offset
  - **Telegram long-poller** (timeout=30s): receive Telegram updates; route to
    inbox via §5.4 inbound pipeline
  - **Heartbeat writer** (every 30s): update `bridge-state.json` heartbeat
  - **Retention prune** (daily at startup-time-of-day): delete attachments past
    retention; rotate logs as needed

- **Shutdown** (SIGTERM from launchd):
  1. Stop accepting new outbox work
  2. Flush pending outbound sends
  3. Persist final state
  4. Exit cleanly

### 5.2 Restart behavior

State is fully recoverable from `bridge-state.json` + `registry.yaml` + the
per-agent outbox files. Bridge picks up from last-confirmed offsets. Outbound
messages persisted in outbox files but not yet sent are re-sent on restart;
duplicate-send is avoided via Telegram API's deterministic `sendMessage`
(re-sending the same text doesn't dedupe but the agent and bridge state
align after restart, so no work is lost — only re-sent once).

### 5.3 Outbound pipeline (agent outbox → Telegram)

```
Bridge reads new outbox line
    ↓
[ResponseValidator] (§8)
  - Schema check (required keys present)
  - Text length OK
  - Attachment exists + within size cap + allowed type
    ↓
[CircuitBreaker.check_telegram]
  - If OPEN: queue locally, log, increment "queued during outage" counter
    ↓
[RetryEngine] with jittered exponential backoff (tenacity)
  - Telegram 429 → backoff per Retry-After
  - Telegram timeout / 5xx → up to 3 retries
    ↓
Telegram sendMessage / sendDocument
    ↓
[CircuitBreaker.record_success_or_failure]
    ↓
[AuditLogger] → bridge.log
    ↓
Update outbox offset in bridge-state.json
```

### 5.4 Inbound pipeline (Telegram → agent inbox)

```
Telegram getUpdates returns update
    ↓
[InputGuard] (§8)
  - Chat ID in TELEGRAM_ALLOWED_CHAT_IDS whitelist
  - Message size ≤ 50KB text or attachment ≤ 50MB
  - Attachment type in allowlist
  - Command (if present) in known set
  - No injection pattern in text
    ↓
Topic ID → agent-id (via registry.yaml)
    ↓
If agent-id not in registry → log + drop, do not write inbox
    ↓
If attachment: download to attachments/, sanitize filename
    ↓
[ResponseValidator]
  - Required fields populated
  - Attachment path safe
    ↓
Append to <agent-id>/inbox.jsonl
    ↓
[AuditLogger]
    ↓
Update last_telegram_update_id in bridge-state.json
```

### 5.5 Vault enrichment (read-only)

When processing an outbox line, bridge optionally enriches with vault state:

- Reads `<vault>/Projects/<agent-id's-project>.md` frontmatter
- Reads `<vault>/Projects/_pulse/<project>--<host>.md` sidecar
- Adds an enrichment block to the Telegram message:

```
🟢 agents [active · ship Path B]
Issue #42 done
_21c/24h · 12 open · sidecar 35m ago_
```

Enrichment is **opt-out** via outbox line's `enrich: false` flag (raw text
preferred for some cases). Enrichment refuses if vault's `client != "personal"`
(redundant with startup check; defense in depth).

### 5.6 Sidecar staleness handling

When enrichment data is from a sidecar > 24h old, prefix with ⚠:

```
🟢 agents [active · ship Path B]
Issue #42 done
⚠ sidecar 36h old · 21c/24h · 12 open
```

> 72h old: drop enrichment entirely (data is too stale to be useful).

---

## §6 notify skill contract

The `notify` Python module exposed to Claude Code skills. All functions accept
an `agent_id` for routing.

### 6.1 Public API

```python
notify.send(agent_id, text, *, level="info", attach=None,
            type="status", wait_for_answer=False, enrich=True)
    → MessageId

notify.poll(agent_id, *, since_offset=None)
    → list[InboxMessage]
    # Reads new lines past last-known offset; updates agent-state.json

notify.wait_for_answer(agent_id, prompt_text, *, timeout_s=600,
                        attach=None)
    → InboxMessage | None
    # Sends prompt; long-polls inbox; returns first ANSWER command or None on timeout

notify.listen(agent_id, *, timeout_s=600,
              accept=["EPIC", "ISSUES", "STOP"])
    → InboxMessage | None
    # Long-polls inbox; returns first matching command or None on timeout
    # Used by finished sessions staying alive for new work

notify.acquire_lock(agent_id, *, skill_name)
    → LockResult
    # Stale-PID-aware lock acquisition (§Q9)

notify.release_lock(agent_id)
    → None
    # Called in skill's finally block

notify.query(query_name, *, project=None)
    → QueryResponse
    # Local helper (does NOT round-trip Telegram). Used by skills that want
    # to render the same data the on-demand-query feature exposes.
    # query_name ∈ {"status", "blockers", "recent", "open"}
```

### 6.2 Data types

```python
@dataclass
class InboxMessage:
    id: str
    ts: datetime
    command: str
    text: str
    attach: Path | None
    from_chat: str
    from_topic: str

@dataclass
class MessageId:
    outbox_line_id: str
    telegram_message_id: int | None  # None if queued (bridge offline)

@dataclass
class QueryResponse:
    # Channel-agnostic content per §2.1
    project: str
    status: str
    focus: str
    last_commit: CommitRef
    commits_24h: int
    commits_7d: int
    open_issues: int | None
    open_actions: int
    blockers: list[str]
    next_steps: list[str]
    sidecar_age_minutes: int
```

### 6.3 Convention: agent-id naming

Format: `<repo>-<skill>` e.g., `agents-build`, `buddy-build`, `agents-review`,
`agents-listen` (for finished-sessions-staying-alive pattern).

Skills MUST acquire a lock on their `agent_id` before any `notify.*` call that
modifies state. `notify.query()` and `notify.poll()` are read-only and lock-free.

---

## §7 Vault enrichment + on-demand queries

### 7.1 Enrichment fields (in QueryResponse and outbox enrichment block)

From `<vault>/Projects/<project>.md` frontmatter:
- `project`, `host`, `client`, `kind`, `status`, `focus`, `status_updated`
- `blockers`, `next_steps`

From `<vault>/Projects/_pulse/<project>--<host>.md` sidecar:
- `pulled_at`, `last_commit_subject`, `last_commit_sha`
- `commits_24h`, `commits_7d`
- `open_issues`, `open_actions`
- `dirty`, `ahead_origin`, `behind_origin`

Derived:
- `sidecar_age_minutes` = now - pulled_at
- `focus_stale` = days since status_updated > 5

### 7.2 On-demand query commands (user types in Telegram)

| Command | Telegram input | What bridge does | Response shape |
|---|---|---|---|
| `STATUS <project>` | DM or any topic | Reads vault + sidecar for that project | Single-project QueryResponse rendered for Telegram |
| `BLOCKERS` | DM or any topic | Reads vault frontmatter for every personal-context subscribed project; collects non-empty `blockers` lists | One line per project with non-empty blockers |
| `RECENT <project>` | DM or any topic | Reads sidecar's last_commit + (when available) extended history from local git | Last 5 commits with timestamps |
| `OPEN <project>` | DM or any topic | Reads sidecar's open_issues + open_actions counts + ACTIONS.md headers | Numbered list of open items |

### 7.3 Renderer (Telegram-specific)

```
🟢 agents [active · ship Path B]
21 commits in last 24h · 12 open issues · 1 open action
Last: feat(lib): host_resolver — read repo state for pulse sidecars (#161)
Sidecar refreshed 35m ago.
```

Same data → terminal renderer (future) → ANSI table. Same data → voice (future)
→ TTS prose. Different shapes, same content.

---

## §8 Control layer (per Towards Data Science 2026-05 pattern)

### 8.1 Components

| Component | Purpose | Used where |
|---|---|---|
| **InputGuard** | Validate inbound Telegram before write-to-inbox | §5.4 inbound pipeline, first stage |
| **ResponseValidator** | Validate outbox line shape before send; validate inbound message structure | §5.3 + §5.4 |
| **CircuitBreaker** | Three-state FSM (CLOSED/OPEN/HALF_OPEN) for Telegram API | §5.3 outbound, gates send |
| **RetryEngine** | Jittered exponential backoff with failure-mode-keyed mutation hints | §5.3 outbound |
| **FallbackRouter** | Graceful degradation: bridge-down → queue locally + heartbeat-stale flag | §5.3 outbound + Q5 hybrid soft-fail |
| **AuditLogger** | Append every event to bridge.log | All pipelines |

### 8.2 InputGuard checks (inbound)

In order, fail-fast:

1. **Chat ID whitelist**: `from_chat in TELEGRAM_ALLOWED_CHAT_IDS` — reject silently otherwise (security: don't leak that bot is alive)
2. **Topic registered**: `topic_id in registry.yaml` — log + drop otherwise
3. **Size limits**: text ≤ 50KB; attachment ≤ 50MB
4. **Attachment type allowlist**: `.md, .txt, .log, .json, .yaml, .yml, .pdf, .png, .jpg, .jpeg, .csv` only. Refuse `.sh, .py, .exe, .deb, .dmg, .pkg, .app, .zip` — emit error reply in topic, do NOT write inbox
5. **Filename safety**: strip path separators, null bytes, `..`; restrict to `[A-Za-z0-9._-]+`; max 100 chars
6. **Command pattern**: if message starts with a known command verb (`STOP|PAUSE|RESUME|STATUS|ANSWER|BLOCKERS|RECENT|OPEN|EPIC|ISSUES`), parse; otherwise treat as `command=""` freeform
7. **Injection pattern detection** (basic): refuse messages with `ignore previous instructions`, `system:`, `<|im_start|>`, or other known prompt-injection markers — emit error reply, do NOT write inbox

### 8.3 CircuitBreaker for Telegram API

States:

```
CLOSED  --[5 consecutive Telegram failures]--> OPEN
OPEN    --[60s elapsed]--> HALF_OPEN
HALF_OPEN --[next send succeeds]--> CLOSED
HALF_OPEN --[next send fails]--> OPEN
```

While OPEN:
- All outbox processing pauses
- Outbox files accumulate normally (agents don't know)
- Bridge logs each skipped send
- `bridge-state.json.telegram_circuit_state` reflects OPEN; agent's
  `notify.send` heartbeat check sees this and warns at next session
  breakpoint per Q5 hybrid soft-fail

### 8.4 RetryEngine mutation hints

Failure-mode-keyed hints applied when retrying:

| FailureMode | Retry behavior |
|---|---|
| TELEGRAM_TIMEOUT | Exponential backoff (1s, 2s, 4s); 3 retries max |
| TELEGRAM_RATE_LIMIT | Backoff per Retry-After header; up to 30s |
| TELEGRAM_5XX | Exponential backoff; 3 retries max |
| INJECTION_DETECTED | **No retry** — hard refuse (security) |
| INVALID_ATTACHMENT_TYPE | **No retry** — emit error reply, drop |
| ATTACHMENT_TOO_LARGE | **No retry** — suppress attachment, send text + note |

### 8.5 FallbackRouter

When retries exhaust:
- **Telegram unreachable**: line stays in outbox; bridge logs;
  `telegram_circuit_state=OPEN`; next agent breakpoint sees stale heartbeat
- **Attachment too large**: send text portion + `"[attachment suppressed: 80MB > 50MB cap; see /tmp/agent-bridge-attempted/<id>]"`
- **Outbox malformed**: log + write error inbox line `type=error,
  failure_mode=MALFORMED_OUTBOX_LINE` so agent knows; advance offset to skip

### 8.6 AuditLogger format

bridge.log lines (one JSON per line):

```json
{"ts":"2026-05-22T17:00:00.123Z","level":"info","event":"outbound_sent",
 "agent_id":"agents-build","msg_id":"01HX...","telegram_msg_id":12345,
 "latency_ms":287}
{"ts":"2026-05-22T17:00:30.000Z","level":"warn","event":"circuit_opened",
 "consecutive_failures":5,"last_failure":"TELEGRAM_TIMEOUT"}
{"ts":"2026-05-22T17:00:42.500Z","level":"error","event":"inbound_rejected",
 "from_chat":"...","reason":"UNAUTHORIZED_CHAT_ID"}
```

---

## §9 Security model

### 9.1 Secrets

- `TELEGRAM_BOT_TOKEN` in `~/.claude/telegram.env`, mode 0600
- File NOT committed (in `.gitignore`)
- Bridge process reads at startup; never logged

### 9.2 Auth boundaries

- **Inbound**: chat-ID whitelist enforced in InputGuard (§8.2)
- **Outbound**: bridge owns the bot token; no other process needs it
- **Filesystem**: per-agent dirs mode 0700; per-agent files mode 0600;
  attachments mode 0600

### 9.3 Client isolation enforcement

Multiple defenses in depth:

1. **Registry startup check**: each agent's `vault:` field cross-checked against
   `~/.claude/vault-clients.yaml`; refuse to start if vault's client ≠ personal
2. **Enrichment runtime check**: vault.frontmatter.client must be "personal"
   before enrichment data is added to outbound message
3. **Static check** (planned for v1.1): a `pulse audit`-style command verifies
   no non-personal vault is registered

### 9.4 Injection-resistance

The bridge itself is not an LLM, so direct prompt-injection isn't its primary
threat — but inbound text reaches downstream Claude sessions. InputGuard §8.2
#7 catches the most common patterns; deeper resistance is the responsibility
of the consumer skill (e.g., /auto-implement's own constraint headers).

### 9.5 Attachment quarantine

Files survive sanitization but agents must explicitly opt-in to using them:
inbox lines reference attachments by path; agent code chooses whether to
`Read` them. Bridge does NOT auto-execute files; allowlist excludes `.sh,
.py, .exe, .deb, .dmg`. Agents should treat all attachments as untrusted
input.

---

## §10 Out of scope (explicit)

| Item | Reason |
|---|---|
| Phase 2 synthesis (daily standups, rollups) | Deferred — see §1; requires v1 burn-in for signal |
| Phase 3 dispatch (Mavis decides + queues work) | Deferred indefinitely; bigger risk surface |
| Multi-machine bridge | v2 territory; jns-server deployment when work-laptop ships |
| Client-work bridges (Vital-CoS, Tillamook-CoS) | Separate deployments per client isolation principle; not in this spec |
| Session-to-session messaging | Bridge is human↔agent; if agents need to talk, they use file inboxes directly |
| Buddy code changes | None required for v1. Bridge is sibling process |
| Voice integration | Mavis's existing voice runs in Buddy; not bridge concern |
| Web/dashboard UI | Telegram is the v1 UI |
| Routines (Claude Code remote agents) | `/remote-control` is a different surface; complement, not replacement |
| `notify.broadcast` (one-to-many) | Skills loop over agent_ids if needed; no native broadcast primitive |

---

## §11 Risks + mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Telegram outage | Medium | CircuitBreaker + soft-fail queue (§8.3, Q5); messages re-sent on recovery |
| Bridge process crash | Medium | launchd auto-restart; state persisted; lock stale recovery (Q9) |
| Concurrent agent sessions race | Low | Lock file with PID check (Q9); convention of distinct agent-ids |
| Malicious inbound (file or injection) | Medium-High | InputGuard allowlist + chat-ID whitelist + injection patterns + attachment quarantine |
| Client work routed through personal bridge | High | §9.3 multiple defense layers; registry refuses to start |
| Stale vault data in enrichment | Low | Sidecar-age display ⚠ > 24h; drop > 72h |
| Disk fill (attachments accumulate) | Low | 30-day retention prune (Q7); configurable |
| Token cost from polling | Low | Long-poll patterns (`notify.listen`) cost ~1 tool call per window |
| Sidecar enrichment leaks across vaults | Low | Vault selection by agent's registered vault only; check at every enrichment call |
| Bridge log fills disk | Low | 14-day rotation (Q10) |
| Spec ambiguity in failure-mode handling | Medium | Codex adversarial review before implementation |

---

## §12 Acceptance criteria

### v1 ships when

- [ ] Bridge bot runs as launchd service on jns-mac; survives manual stop/start
- [ ] `~/agents/notify/` Python module with API per §6
- [ ] Agent can `notify.send(...)` and message arrives in Telegram within 5s
- [ ] Telegram message in topic arrives in agent inbox file within 5s
- [ ] File attachments work both directions; .sh refused; 50MB cap enforced
- [ ] `STATUS <project>` query returns correct vault + sidecar data
- [ ] `BLOCKERS` query enumerates correctly across subscribed projects
- [ ] Lock file refuses concurrent same-agent-id; recovers from stale lock
- [ ] CircuitBreaker opens after 5 consecutive failures; HALF_OPEN probes recovery
- [ ] Bridge logs structured JSON; rotates daily; keeps 14 days
- [ ] Attachments prune at 30 days
- [ ] Bridge refuses to start if any registered vault has `client != "personal"`
- [ ] Injection patterns in inbound text trigger refusal + error reply
- [ ] InputGuard rejects unauthorized chat IDs silently
- [ ] `notify.listen()` blocks on tail-F with timeout; returns first matched command

### Smoke tests on jns-mac

- [ ] Round-trip: agent sends → arrives on phone; reply on phone → reaches agent's inbox
- [ ] File round-trip: agent attaches PR markdown → renders in Telegram; reply with screenshot → file in agent's attachments/
- [ ] STOP from Telegram halts an `/auto-implement` run at next breakpoint
- [ ] STATUS query against a real subscribed project returns accurate data
- [ ] BLOCKERS query enumerates all current blockers across subscribed projects
- [ ] Kill bridge mid-run, restart; agent's queued outbox flushes
- [ ] Concurrent attempt to start same agent-id is refused with clear error
- [ ] Send a non-allowlisted file type → refused with explanatory error reply

---

## §13 Sign-off

| Date | Reviewer | Status |
|---|---|---|
| 2026-05-22 | Jason Job | drafted (this version) |
| TBD | Codex adversarial review | pending |
| TBD | Jason Job (post-review) | pending |

Once signed off, implementation issues will be filed against this spec
(analogous to Path B's #161–#170 pattern).
