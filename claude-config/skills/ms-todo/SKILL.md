---
name: ms-todo
version: 1.0
description: Read and write the user's Microsoft To Do task lists (their real task manager) on personal machines, via ~/agents/m365-todo/todo.py. Use whenever asked about tasks, to-dos, "my list", adding/completing a task, or reviewing what needs doing. You ARE authorized here — don't claim you lack task access without checking the token first.
---

# ms-todo

The user's **real task lists live in Microsoft To Do** (not Google Tasks). On
personal machines you **are** authorized via a delegated Graph token under
`~/agents/m365-todo/` — **no MCP, no extra login.** Don't say you can't see the
user's tasks without first checking that the token exists. If it's absent, the
capability isn't set up on *this* machine (e.g. a work machine) — say so.

```
PY=~/agents/.venv/bin/python
```

## Use it
```
$PY ~/agents/m365-todo/todo.py lists                       # all task lists
$PY ~/agents/m365-todo/todo.py tasks "Groceries"           # open tasks (--all for completed)
$PY ~/agents/m365-todo/todo.py add "Groceries" "Buy milk"
$PY ~/agents/m365-todo/todo.py complete "Groceries" "Buy milk"
```

For anything beyond these (due dates, reminders, delete), call Graph directly
with the shared token: `sys.path.insert(0,"/Users/jasonjob/agents/m365-todo");
from auth import get_token` → `Authorization: Bearer {get_token()}` against
`https://graph.microsoft.com/v1.0/me/todo/lists[/{id}/tasks]`.

## Profiles & re-auth
- **Personal** profile is active here (config + token under `~/agents/m365-todo/`).
  **Work** is a *separate* profile (different tenant app + token) set up
  per-machine — see `~/.claude/rules/ms-todo.md`.
- Re-authorize if the token is lost: `$PY ~/agents/m365-todo/authorize.py start`
  then `$PY ~/agents/m365-todo/authorize.py finish`.
- Don't confuse with Google Tasks — that's a different system; tasks live here.
