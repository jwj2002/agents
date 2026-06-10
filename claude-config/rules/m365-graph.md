---
description: "M365 / Microsoft Graph credentials and helpers (this laptop's agent identity)"
paths: ["**/m365/**", "**/email-digest/**"]
---

# M365 / Microsoft Graph (this laptop)

> Moved out of CLAUDE.md (#384) to keep the always-loaded prompt under budget.
> Loads on demand — read when a task involves sending/reading mail via Graph.

This laptop has working Graph credentials for Jason's agent identity
**`jjob@vital-enterprises.com`** (parallel to Paul's `ai-coder@vital-enterprises.com`
and Ryan's `ryan-agent@vitalailabs.com`). The app is scoped via
ApplicationAccessPolicy to that single mailbox — it cannot send-as or read
any other address.

| What | Where |
|---|---|
| Credentials (chmod 600, gitignored) | `~/.claude/m365/agent.json` |
| Send helper | `~/agents/m365/send_mail.py --to … --subject … --body … [--attach …]` |
| Read helper | `~/agents/m365/read_mail.py [--top N] [--from …] [--subject-contains …] [--since …] [--unread-only]` |
| Renderer (markdown → HTML for email body) | `~/agents/m365/render_markdown.py` |
| Token cache | `~/.claude/m365/token-cache.bin` (managed by msal) |

**Always send as `jjob@vital-enterprises.com`** — never override the sender.
On other machines this section may not apply (different identity / different
provider); the credential file's absence at the path above is the signal
that the M365 capability isn't configured on that machine.

---

## SharePoint — client documents (same app, same credentials)

Client documents live in the **Documents** library of the VitalAILabs
SharePoint site (`vtmgroup.sharepoint.com:/sites/VItalAILabs`). The library
root holds **one folder per client**; inside each client are subfolders such
as *Transcripts*, *Sample Client Files*, *Product Requirement Docs*, and
*Legal Docs*. **That subfolder set varies and changes** — list whatever
folders actually exist for a client; never assume the fixed list.

Auth is the **same app registration as mail** — the client-credentials token
from `agent.json` already carries the `Sites.Selected` role and is granted on
this one site (verified 2026-06-10: lists 49 client folders). No extra
credential, no new app reg. Access is confined to this single site; the app
cannot see any other SharePoint site.

| What | Where |
|---|---|
| Helper (list / read / write) | `~/agents/m365/sharepoint.py` |
| Credentials (shared with mail) | `~/.claude/m365/agent.json` |

```bash
python3 ~/agents/m365/sharepoint.py list-clients
python3 ~/agents/m365/sharepoint.py list "Broken Top Club"            # see real subfolders
python3 ~/agents/m365/sharepoint.py list "Broken Top Club" "Transcripts"
python3 ~/agents/m365/sharepoint.py read  "Broken Top Club/Transcripts/kickoff.txt"
python3 ~/agents/m365/sharepoint.py read  "Broken Top Club/Legal Docs/nda.pdf" --out ./nda.pdf
python3 ~/agents/m365/sharepoint.py write "Broken Top Club/Product Requirement Docs/prd.md" --file ./prd.md
```

The site id is hardcoded in the helper (so an agent can't wander to other
company sites) and is not a secret. The capability is gated by the
machine-local `agent.json`: it works wherever that file is present and is inert
elsewhere. **To enable on another work machine (jbox06, et01, spark):** make
`~/agents/m365/sharepoint.py` available there (clone/sync this repo, or copy
the single file + `pip install msal requests`), drop the same `agent.json` at
`~/.claude/m365/agent.json`, and `chmod 600` it. Nothing else changes — the
secret never leaves the machine it's installed on.
