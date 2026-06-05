# Central Google credentials (`~/agents/google`)

**One Google authorization for every agent on a machine.** Re-auth once, send/read
from anywhere, no per-tool credential sprawl.

## Layout

| File | Tracked in git? | What it is |
|---|---|---|
| `auth.py` | ✅ | Shared loader — `load_credentials()` returns valid creds, auto-refreshing. |
| `reauth.py` | ✅ | One browser consent → writes `token.json`. **Your "reauth google" command.** |
| `send_mail.py` | ✅ | Sender used by all agents (mirrors `m365/send_mail.py`). |
| `requirements.txt` | ✅ | `google-auth`, `google-auth-oauthlib`, `google-api-python-client`. |
| `oauth_client.json` | ❌ (git-ignored) | Installed-app OAuth client (client_id/secret). Same on every machine. |
| `token.json` | ❌ (git-ignored) | Your user authorization (refresh token). **Secret. Per-user.** |
| `legacy-gmail-mcp/` | ❌ (git-ignored) | Old `@gongrzhe` gmail-send MCP creds, kept only so the deprecated MCP still resolves. Safe to delete once the MCP is removed (`claude mcp remove gmail-send`). |

Scopes (superset, so one token covers all agents): `gmail.send`, `gmail.modify`,
`calendar`, `tasks`, `contacts.readonly`.

## Everyday use

```bash
PY=~/agents/.venv/bin/python

# Re-authorize (opens a browser; pick the right Google account):
$PY ~/agents/google/reauth.py

# Send mail (from the authorized account):
$PY ~/agents/google/send_mail.py --to a@b.com --subject "Hi" --body "Hello" --attach file.md
```

In Python (any agent):

```python
import sys; sys.path.insert(0, "/Users/jasonjob/agents/google")
from auth import load_credentials
from googleapiclient.discovery import build
svc = build("gmail", "v1", credentials=load_credentials())
```

## How buddy uses it

buddy reads `~/.buddy/google_token.json` and `~/.buddy/google_credentials.json`.
Those are **symlinked** to this directory's `token.json` and `oauth_client.json`,
so buddy and every other agent share one token. buddy's auto-refresh writes back
through the symlink, keeping everyone in sync. No buddy code change required.

## Enabling email on another machine

The **code** arrives via git (the `.py` files are tracked). The **secrets** do not
(git-ignored) — you provide them on the new box. Two files must exist in
`~/agents/google/`:

1. **`oauth_client.json`** — the app identity (not your mailbox). Copy it from an
   existing machine, or re-download the *installed-app* OAuth client from Google
   Cloud Console. Identical on every machine.
2. **`token.json`** — your authorization. Choose by machine type:

   - **Laptop / has a browser →** run `reauth.py` on that machine:
     ```bash
     ~/agents/.venv/bin/python ~/agents/google/reauth.py
     ```
   - **Headless server / jbox06 (no browser) →** authorize on your laptop once,
     then copy the token over:
     ```bash
     scp ~/agents/google/token.json  jbox06:~/agents/google/token.json
     scp ~/agents/google/oauth_client.json jbox06:~/agents/google/oauth_client.json
     ```
     The refresh token is **portable across machines** for the same OAuth client.

Then (for buddy) symlink its paths at the central files:
```bash
ln -sf ~/agents/google/token.json        ~/.buddy/google_token.json
ln -sf ~/agents/google/oauth_client.json ~/.buddy/google_credentials.json
```
Don't forget deps on the new box: `~/agents/.venv/bin/pip install -r requirements.txt`.

## Make it durable — publish the OAuth app

While the OAuth consent screen is in **"Testing"**, Google **expires refresh tokens
after 7 days** (that's the recurring `invalid_grant`). One-time fix:

> Google Cloud Console → APIs & Services → OAuth consent screen →
> **Publishing status → "In production"**

After that the token only dies if you revoke it — so the headless "copy token once"
flow above keeps working indefinitely.

## Most robust option for the Workspace domain (future)

For sending **as `@vital-enterprises.com`** (Google Workspace), the headless-friendly
pattern is a **service account with domain-wide delegation** — no browser, no per-user
token, works on every machine. (Not applicable to the personal `gmail.com` account,
which still needs the user-consent flow above.)
