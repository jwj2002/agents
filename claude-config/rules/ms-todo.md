---
description: "Microsoft To Do (personal MS account) for all agents — read/write via Graph delegated token. Personal machines."
paths: ["**/m365-todo/**"]
---

# Microsoft To Do — personal task lists for every agent (personal machines)

> Loads on demand — read when a task involves the user's Microsoft To Do lists
> (task capture, list review, marking done). Orientation line is in `CLAUDE.md`.

The user's task lists live in **Microsoft To Do under their personal Microsoft
account** (`jasonwadejob@gmail.com`). Agents reach them via Microsoft Graph with
a **delegated** token (device-code flow, public client) under `~/agents/m365-todo/`.
This is separate from Google Tasks and from the work M365 mail app — different
identity, different auth model. See [[google-mail]] and [[m365-graph]].

## Per-machine gate

Configured **only where `~/agents/m365-todo/token.json` exists** (git-ignored,
per-user, chmod 600). Absence = not set up on this machine. Mirrors the Google /
M365 gates.

## Auth

- Personal Microsoft account → authority `…/consumers`, delegated scope
  `Tasks.ReadWrite`, **public client** (no secret, no admin consent).
- App registration (Entra): client id `d9df9a09-f0ee-4093-90ab-2dbb319b4570`.
- Re-authorize (token lost/revoked): two steps —
  `~/agents/.venv/bin/python ~/agents/m365-todo/authorize.py start` (prints a
  URL + code), then `… authorize.py finish` (blocks until you approve in the
  browser). Validated live 2026-06-26: full read + write (create/update/delete).

## Helpers

| What | Where |
|---|---|
| Shared loader (silent refresh) | `~/agents/m365-todo/auth.py` → `get_token()` |
| First-time / re-auth | `~/agents/m365-todo/authorize.py` (`start` then `finish`) |
| **CLI** | `~/agents/m365-todo/todo.py` |

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/m365-todo/todo.py lists                  # all task lists
$PY ~/agents/m365-todo/todo.py tasks "Groceries"      # open tasks in a list (--all for completed)
$PY ~/agents/m365-todo/todo.py add "Groceries" "Milk" # create a task
$PY ~/agents/m365-todo/todo.py complete "Groceries" "Milk"
```

In Python (any agent): `sys.path.insert(0,"/Users/jasonjob/agents/m365-todo");
from auth import get_token` → `Authorization: Bearer {get_token()}` against
`https://graph.microsoft.com/v1.0/me/todo/lists[/{id}/tasks]`. Delete is
`DELETE …/tasks/{id}` (returns 204).
