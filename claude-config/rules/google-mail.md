---
description: "Central Google identity (Gmail / Calendar / Tasks / Contacts) for all agents — personal machines"
paths: ["**/google/**", "**/email-digest/**"]
---

# Google Workspace — one authorization for every agent (personal machines)

> Loads on demand — read when a task involves sending mail, or touching Google
> Calendar / Tasks / Contacts. The everyday orientation line lives in `CLAUDE.md`.

Personal machines have a **single Google OAuth authorization** shared by every
agent, under `~/agents/google/`. One re-auth, send/read from anywhere, no
per-tool credential sprawl. This is the canonical path — **do NOT hand-roll an
ad-hoc send script or a separate token.**

## Per-machine gate

The capability is configured **only where `~/agents/google/token.json` exists**
(git-ignored, per-user). Its absence is the signal the capability isn't set up
on this machine — work machines do not have it. Mirrors the M365 gate
(`~/.claude/m365/agent.json`). See [[m365-graph]] for the work-mail path.

## Authorized scopes (one superset token covers all agents)

`gmail.send`, `gmail.modify`, `calendar`, `tasks`, `contacts.readonly`.
Validated live 2026-06-26 on this laptop: Gmail (account
`jasonwadejob@gmail.com`), Calendar (read/write), Google Tasks all OK.

## Helpers

| What | Where |
|---|---|
| Shared loader (auto-refreshing creds) | `~/agents/google/auth.py` → `load_credentials()` |
| Re-authorize ("reauth google") | `~/agents/.venv/bin/python ~/agents/google/reauth.py` |
| **Send mail** (CLI) | `~/agents/google/send_mail.py` |
| **Calendar read/write** (CLI) | `~/agents/google/gcal.py` (`calendars`/`agenda`/`add`/`quickadd`/`delete`) |
| **Gmail read/search** (CLI) | `~/agents/google/gmail_read.py` (`unread`/`search`/`read`) |
| **Gmail label/triage** (CLI) | `~/agents/google/gmail_label.py` (`list`/`add`/`remove`; `gmail.modify`) |
| **Contacts lookup** (CLI, read-only) | `~/agents/google/contacts.py` (`search "<name>"` → email/phone) |
| Full reference | `~/agents/google/README.md` |

### Send mail (CLI)

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/google/send_mail.py --to a@b.com --subject "Hi" --body "Hello" \
    --attach file.pdf            # --to/--cc/--bcc/--attach repeatable; --body - reads stdin
```

Sends from the authorized account (today `jasonwadejob@gmail.com`); prints the
sender + message id. Attachments are supported (multipart) up to Gmail's 25 MB.

### Calendar (CLI)

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/google/gcal.py agenda --days 7            # upcoming events
$PY ~/agents/google/gcal.py add --title "Lunch" --start "2026-06-27 12:30" --end "2026-06-27 13:30"
$PY ~/agents/google/gcal.py quickadd --text "Dentist Thursday 3pm"
$PY ~/agents/google/gcal.py delete --event-id <id>     # (also: calendars)
```

Timezone auto-detects from the calendar (override with `--tz`); `--calendar`
defaults to `primary`. Note the file is `gcal.py`, **not** `calendar.py` (that
would shadow the stdlib `calendar` module).

### Read / search mail (CLI)

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/google/gmail_read.py unread --max 10
$PY ~/agents/google/gmail_read.py search "from:x@y.com newer_than:7d" --max 20
$PY ~/agents/google/gmail_read.py read <message_id>
```

Uses the token's `gmail.modify` scope (read included) — no re-auth. `search`
takes normal Gmail query syntax; `read` prints headers + plain-text body.

### Label / triage mail (CLI)

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/google/gmail_label.py list
$PY ~/agents/google/gmail_label.py add <message_id> "Follow up" --create
$PY ~/agents/google/gmail_label.py remove <message_id> "Follow up"
```
Uses `gmail.modify` (already granted) — no re-auth. Message ids come from
`gmail_read.py`.

### Contacts lookup (CLI, read-only)

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/google/contacts.py search "Bob Smith"      # name -> email/phone
```
Read-only (`contacts.readonly` scope). **Creating/editing contacts is NOT
possible** with the current token — that needs the `contacts` (read-write) scope
added to `auth.py:SCOPES` + a `reauth.py` re-consent.

### Google Tasks (no ready-made CLI yet)

For Google Tasks, use the shared auth directly (the token already authorizes it):

```python
import sys; sys.path.insert(0, "/Users/jasonjob/agents/google")
from auth import load_credentials
from googleapiclient.discovery import build
svc = build("tasks", "v1", credentials=load_credentials())
```

If you find yourself repeating one, promote it to a `~/agents/google/` CLI helper
(mirroring `send_mail.py` / `gcal.py` / `gmail_read.py` / `contacts.py`).

## Relationship to the claude.ai MCP connectors

Goal: **no MCP** for Google. Status — the token CLI now covers everything except Drive:

- **Gmail read/search** — ✅ `gmail_read.py`. The claude.ai Gmail MCP is now
  **redundant and can be disconnected.**
- **Gmail send** — ✅ `send_mail.py` (the MCP never could send anyway).
- **Calendar read/write** — ✅ `gcal.py`. The claude.ai Calendar MCP is redundant.
- **Google Tasks / Contacts** — token-authorized; no CLI yet (use `auth.py`).
- **Drive** — still MCP-only; no `~/agents/google/` helper (only remaining reason
  to keep any claude.ai Google connector).

There is no longer a local `gmail-send` MCP. Prefer the token CLIs above over any
MCP for Gmail/Calendar.
