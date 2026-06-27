---
name: google-workspace
version: 1.0
description: Read, search, and send email via Gmail and read/write Google Calendar on personal machines, using the shared ~/agents/google OAuth (gmail_read.py / send_mail.py / gcal.py). Use whenever asked to read/search the inbox, send/draft an email, check the calendar, or add/move/delete a calendar event. You ARE authorized here — do not claim you lack Gmail access without checking for the token first.
---

# google-workspace

On personal machines you **are** authorized for Gmail + Google Calendar via a
shared OAuth token at `~/agents/google/token.json` — **no MCP or extra login
needed.** Do not tell the user you lack Gmail/Calendar access without first
checking that token file exists. If it is absent, the capability isn't set up on
*this* machine (e.g. a work machine) — say that instead of guessing.

```
PY=~/agents/.venv/bin/python
```

## Read / search email
```
$PY ~/agents/google/gmail_read.py unread --max 10
$PY ~/agents/google/gmail_read.py search "from:boss@x.com newer_than:7d" --max 20
$PY ~/agents/google/gmail_read.py read <message_id>
```
`search` takes the normal Gmail query syntax. `unread`/`search` print id + from +
subject + snippet; `read` prints headers + the plain-text body. This is the
token path — **no MCP needed to read.**

## Send email
```
$PY ~/agents/google/send_mail.py --to a@b.com --subject "Hi" --body "Hello" [--attach file.pdf]
```
`--to` / `--cc` / `--bcc` / `--attach` repeat; `--body -` reads stdin. Sends from
the authorized account (currently jasonwadejob@gmail.com); prints sender +
message id. Attachments up to 25 MB.

## Calendar (read/write)
```
$PY ~/agents/google/gcal.py agenda --days 7
$PY ~/agents/google/gcal.py add --title "Lunch" --start "2026-06-28 12:30" --end "2026-06-28 13:30"
$PY ~/agents/google/gcal.py quickadd --text "Dentist Thursday 3pm"
$PY ~/agents/google/gcal.py calendars
$PY ~/agents/google/gcal.py delete --event-id <id>
```
Timezone auto-detects from the calendar; `--calendar` defaults to `primary`.

## Notes
- This shared token is canonical — **never hand-roll a sender/reader or a second token.**
- Read + send + calendar all run off this one token (scopes: gmail.modify,
  gmail.send, calendar). The claude.ai Gmail MCP is no longer needed for reading.
- Google Tasks / Contacts have no CLI yet: build a client off
  `~/agents/google/auth.py:load_credentials()`.
- Full detail + per-machine gate: `~/.claude/rules/google-mail.md`.
- Microsoft To Do (the user's real task lists) is a separate capability —
  use the `ms-todo` skill / `~/agents/m365-todo/todo.py` (see `rules/ms-todo.md`).
