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

## Per-machine profile + gate

Identity is **not** hardcoded — the committed code reads it from a git-ignored
`~/agents/m365-todo/config.json` (copy `config.example.json`). So the same code
runs as a **personal** profile on personal machines and a **work** profile on
work machines:

```
personal machine → config.json (consumers + personal app) + token.json (personal)
work machine     → config.json (work tenant + work app)   + token.json (work)
```

The capability is **active only where BOTH `config.json` and `token.json` exist**
(both git-ignored, chmod 600 on the token) — otherwise it fails closed. Absence =
not set up on this machine. Mirrors the Google (`oauth_client.json`/`token.json`)
and M365-mail (`agent.json`) gates.

## Auth

- **Personal** Microsoft account → `config.json` authority `…/consumers`,
  delegated scope `Tasks.ReadWrite`, **public client** (no secret, no admin
  consent). Validated live 2026-06-26: full read + write (create/update/delete).
- **Work** (when set up) → register an app in the work tenant with delegated
  `Tasks.ReadWrite`, put its client id + tenant authority (`…/<tenant>`, not
  `consumers`) in that machine's `config.json`. Some tenants require admin
  consent.
- **Authorize / re-authorize** (any profile): two steps —
  `~/agents/.venv/bin/python ~/agents/m365-todo/authorize.py start` (prints a URL
  + code), then `… authorize.py finish` (blocks until you approve in the browser).

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
