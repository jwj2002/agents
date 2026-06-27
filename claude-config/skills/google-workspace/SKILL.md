---
name: google-workspace
version: 1.0
description: Read/search/send/label email via Gmail, read/write Google Calendar, and look up or add Google Contacts (name -> email/phone) on personal machines, using the shared ~/agents/google OAuth (gmail_read.py / send_mail.py / gmail_label.py / gcal.py / contacts.py). Use whenever asked to read/search the inbox, send/draft an email, label or triage a message, check the calendar, add/move/delete an event, or find/save someone's contact. You ARE authorized here — do not claim you lack Gmail access without checking for the token first.
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

## Label / triage an email
```
$PY ~/agents/google/gmail_label.py list
$PY ~/agents/google/gmail_label.py add <message_id> "Follow up" [--create]
$PY ~/agents/google/gmail_label.py remove <message_id> "Follow up"
```
Uses `gmail.modify` (no re-auth). Get the message id from `gmail_read.py`.

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

## Contacts (look up / add)
```
$PY ~/agents/google/contacts.py search "Bob Smith"                       # name -> email/phone
$PY ~/agents/google/contacts.py add "Bob Smith" --email bob@x.com --phone 555-1234
$PY ~/agents/google/contacts.py delete people/c123...                    # resourceName from add/search
```
Read/write (`contacts` scope). Pairs with email triage: after reading a new
message, look up the sender or `add` them.

## Notes
- This shared token is canonical — **never hand-roll a sender/reader or a second token.**
- Read + send + label + calendar + contacts all run off this one token (scopes:
  gmail.modify, gmail.send, calendar, tasks, contacts). No MCP needed for these.
- Google Tasks has no CLI yet: build a client off
  `~/agents/google/auth.py:load_credentials()`.
- Full detail + per-machine gate: `~/.claude/rules/google-mail.md`.
- Microsoft To Do (the user's real task lists) is a separate capability —
  use the `ms-todo` skill / `~/agents/m365-todo/todo.py` (see `rules/ms-todo.md`).
