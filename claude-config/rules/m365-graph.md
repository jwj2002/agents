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
