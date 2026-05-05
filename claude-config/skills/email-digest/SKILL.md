---
name: email-digest
version: 1.0
description: Send a project's dashboard digest by email via Microsoft Graph (jason-agent@vital-enterprises.com → recipient agent). Wraps /dashboard --format markdown + the M365 send helper.
---

# /email-digest

Generate a markdown dashboard digest and email it from `jason-agent` to a
recipient. Used to keep peer agents (e.g. paul-agent) in sync with the
current state of a shared project.

## Usage

```
/email-digest paul-jason                                # daily, send to project's default recipient
/email-digest paul-jason --window weekly
/email-digest paul-jason --window monthly
/email-digest paul-jason --window full
/email-digest paul-jason --to paul@example.com          # explicit recipient override
/email-digest paul-jason --for Paul                     # owner-filter Actions
/email-digest paul-jason --dry-run                      # render the digest, don't send
```

## Behavior

1. **Resolve recipient.** If `--to` is given, use it. Otherwise read
   `~/.claude/skills/email-digest/recipients.json`:

   ```json
   { "paul-jason": ["paul@example.com"] }
   ```

   If the project has no recipient configured and `--to` is not given,
   abort with: `no recipient configured for {project} — pass --to or
   add it to ~/.claude/skills/email-digest/recipients.json`.

2. **Generate the digest.** Run `/dashboard {project} --window {window}
   --format markdown` (with `--for` if provided). Capture the output.

3. **Build the subject line.**
   - Daily: `{project} — daily digest {YYYY-MM-DD}`
   - Weekly: `{project} — weekly digest (week of {YYYY-MM-DD})`
   - Monthly: `{project} — monthly digest ({YYYY-MM})`
   - Full: `{project} — full state snapshot {YYYY-MM-DD}`

4. **Send.** Shell out to the helper:

   ```bash
   python3 ~/agents/m365/send_mail.py \
       --to "$RECIPIENTS" \
       --subject "$SUBJECT" \
       --body-file "$DIGEST_PATH" \
       --content-type Markdown
   ```

   The helper handles auth, token cache, and the Graph POST. Sender is
   always `jason-agent@vital-enterprises.com` (configured in
   `~/.claude/m365/jason-agent.json`).

5. **Journal the send.** Call
   `mcp__knowledge__update_project_context` is overkill — instead append
   a `journal` entry via the knowledge MCP if available, otherwise skip.
   Entry format: `digest_sent: {window} → {recipients}`.

6. **Dry-run.** When `--dry-run` is set, write the digest to
   `/tmp/email-digest-{project}-{YYYY-MM-DD}.md` and print the path
   instead of sending. The user can inspect before invoking for real.

## Failure handling

- **No credentials:** if `~/.claude/m365/jason-agent.json` is missing,
  print the path to `~/projects/paul-jason/docs/jason-agent-setup.md`
  and exit. Do not attempt to send.
- **Helper non-zero exit:** surface stderr verbatim and exit non-zero.
  Do not retry — credential and policy errors are not transient.
- **Empty digest:** if `/dashboard --format markdown` produces only the
  header (no sections), still send it — "nothing happened today" is
  itself useful signal for the recipient.

## Setup

See `~/projects/paul-jason/docs/jason-agent-setup.md` for the one-time
Azure / Exchange setup. After credentials are dropped at
`~/.claude/m365/jason-agent.json`, this skill works without further
configuration.

## Notes

- **Sender is hardcoded** to `jason-agent@vital-enterprises.com` via the
  helper's credential file. To change senders, change the credential
  file (or add a separate one and a `--sender` flag — not yet wired).
- **Markdown over Text MIME:** Graph has no Markdown content-type, so
  the body ships as `Text`. Recipient agents parsing the digest see raw
  markdown, which is what the `<!-- dashboard-digest v1 ... -->` header
  contract expects.
- **Idempotency:** Graph does not deduplicate sends. Calling this skill
  twice in the same day will deliver two emails. The recipient agent
  uses the digest header to recognize and merge — but to avoid noise,
  prefer scheduled runs (one per day for `--window daily`).
