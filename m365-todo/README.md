# Microsoft To Do for agents (`~/agents/m365-todo`)

Read/write the user's **Microsoft To Do** task lists from any agent (and the
Buddy resident) via Microsoft Graph with a **delegated** token (device-code
flow, public client). Mirrors the `~/agents/google` pattern: committed code, a
git-ignored per-machine credential file, one shared loader.

This is separate from Google Tasks and from the work M365 **mail** app (see
`../m365/`) — different identity, different auth model.

## Layout

| File | Tracked in git? | What it is |
|---|---|---|
| `todo.py` | ✅ | CLI over Graph `me/todo/*` — `lists`, `tasks`, `add`, `complete`. |
| `auth.py` | ✅ | Shared loader — `get_token()` returns a valid access token (silent refresh). |
| `authorize.py` | ✅ | One-time device-code authorization (`start` then `finish`). |
| `config.example.json` | ✅ | Template for the per-machine identity profile. |
| `requirements.txt` | ✅ | `msal`, `requests`. |
| `test_todo.py` | ✅ | Mocked-Graph unit tests (no network). |
| `config.json` | ❌ (git-ignored) | This machine's identity profile (client_id / authority / account). |
| `token.json` | ❌ (git-ignored) | The MSAL token cache (refresh token). **Secret. Per-machine, chmod 600.** |

The capability is **active only where BOTH `config.json` and `token.json`
exist** — otherwise `auth.get_token()` fails closed with a clear message.

## Everyday use

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/m365-todo/todo.py lists                       # all task lists
$PY ~/agents/m365-todo/todo.py tasks "Groceries"           # open tasks (--all incl. completed)
$PY ~/agents/m365-todo/todo.py add "Groceries" "Milk"      # create
$PY ~/agents/m365-todo/todo.py add "Groceries" "Rent" --due 2026-07-05
$PY ~/agents/m365-todo/todo.py complete "Groceries" "Milk" # mark done
```

In Python (any agent):

```python
import sys; sys.path.insert(0, "/Users/jasonjob/agents/m365-todo")
from auth import get_token
headers = {"Authorization": f"Bearer {get_token()}"}
# GET https://graph.microsoft.com/v1.0/me/todo/lists
```

## Auth provisioning — how to activate on a new machine (e.g. jns)

> **This is the manual step the code cannot do for you.** The `.py` files arrive
> via git; the credentials do not (git-ignored). You provision them once per
> machine. Until both `config.json` and `token.json` exist, the capability is
> inert.

### 1. Register (or reuse) an Entra app with delegated `Tasks.ReadWrite`

- **Personal Microsoft account** (the user's `jasonwadejob@gmail.com` To Do):
  Azure Portal → **Microsoft Entra ID → App registrations → New registration**.
  - Supported account types: **Personal Microsoft accounts** (or
    "Accounts in any org directory and personal MS accounts").
  - Authentication → **Allow public client flows → Yes** (device-code needs this).
  - API permissions → **Microsoft Graph → Delegated → `Tasks.ReadWrite`**. No
    secret and no admin consent are required for a personal-account public client.
  - Copy the **Application (client) ID**.
- **Work tenant** (optional): register the app in the work tenant with delegated
  `Tasks.ReadWrite`; use the tenant id/domain as the authority (not `consumers`).
  Some tenants require admin consent.

### 2. Create `config.json` on the machine

```bash
cp ~/agents/m365-todo/config.example.json ~/agents/m365-todo/config.json
# then edit config.json:
#   "client_id": "<the Application (client) ID from step 1>"
#   "authority": "https://login.microsoftonline.com/consumers"   # personal
#                (or ".../<work-tenant-id-or-domain>" for a work profile)
#   "scopes":    ["Tasks.ReadWrite"]
#   "account":   "jasonwadejob@gmail.com"
```

### 3. Authorize (device-code — works headless / over SSH)

```bash
PY=~/agents/.venv/bin/python
$PY ~/agents/m365-todo/authorize.py start    # prints a URL + code, exits immediately
# open the URL in ANY browser, enter the code, approve as the target account
$PY ~/agents/m365-todo/authorize.py finish   # blocks until approved, writes token.json
```

`token.json` is written chmod 600 and refreshes silently thereafter. To move an
existing authorization to another machine, copy `config.json` + `token.json`
(the refresh token is portable for the same app registration).

### 4. Install deps on the new box

```bash
~/agents/.venv/bin/pip install -r ~/agents/m365-todo/requirements.txt
```

## Status

- **Laptop (personal profile):** validated live 2026-06-26 — full read + write.
- **jns (the Buddy resident):** **NOT yet provisioned** — no Graph credentials on
  the server. Provisioning is steps 1–4 above (Jason's action). This is the
  intended stop point; the resident gains To Do access only after `config.json` +
  `token.json` exist on jns and are verified live.
