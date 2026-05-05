---
name: email-digest
version: 1.2
description: Send a project's dashboard digest by email via Microsoft Graph (jason-agent@vital-enterprises.com → recipient agent). Renders the markdown digest to styled HTML for the body, attaches the source .md and any per-action files.
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

3. **Build the subject line.** Include a count summary so the recipient
   sees activity at a glance without opening the email.

   - Daily: `{project} daily {YYYY-MM-DD} — {N} open / {M} closed`
   - Weekly: `{project} weekly (week of {YYYY-MM-DD}) — {N} open / {M} closed`
   - Monthly: `{project} monthly ({YYYY-MM}) — {N} open / {M} closed`
   - Full: `{project} full snapshot {YYYY-MM-DD} — {N} open total`

   Counts are the **Actions** numbers from the digest (the most
   actionable signal). Issue counts are not in the subject — they're
   visible in the body.

4. **Collect attachments.** Parse the project's `ACTIONS.md` for every
   row that's part of the rendered digest (in-window open + closed,
   honoring `--for`). Read each row's `Files` cell (comma-separated
   absolute paths), de-duplicate, and verify each file still exists.
   Drop missing files with a single warning line per missing path.

5. **Render the digest to HTML.** Convert the markdown body to styled
   HTML using:

   ```bash
   python3 ~/agents/m365/render_markdown.py \
       --in "$DIGEST_MD_PATH" \
       --out "$DIGEST_HTML_PATH"
   ```

   The renderer ships inline CSS (table borders, monospace blocks,
   typography) tuned for Outlook/Gmail compatibility — no flexbox, no
   external assets. The `<!-- dashboard-digest v1 ... -->` header
   comment is preserved verbatim in the HTML so a downstream agent can
   still grep for it if it doesn't open the .md attachment.

6. **Send.** Shell out to the helper. Body is the rendered HTML; the
   markdown source is attached so recipient agents have a clean
   parseable copy:

   ```bash
   python3 ~/agents/m365/send_mail.py \
       --to "$RECIPIENTS" \
       --subject "$SUBJECT" \
       --body-file "$DIGEST_HTML_PATH" \
       --content-type HTML \
       --attach "$DIGEST_MD_PATH" \
       --attach "/home/jjob/projects/superior/docs/PROJECT-OVERVIEW.html" \
       --attach "/another/file.pdf"
   ```

   The helper handles auth, token cache, base64-inline attachment
   encoding, and the Graph POST. Sender is always
   `jason-agent@vital-enterprises.com` (configured in
   `~/.claude/m365/jason-agent.json`).

   **Size guardrail**: total attachment bytes must be ≤ 3 MB (Graph
   inline attachment limit). If exceeded, the helper exits non-zero and
   the digest is not sent — surface the error and ask whether to drop
   some attachments or split into multiple digests.

7. **Journal the send.** Append a `journal` entry via the knowledge MCP
   if available, otherwise skip. Entry format:
   `digest_sent: {window} → {recipients} (+{N} attachments)`.

8. **Dry-run.** When `--dry-run` is set, render both the markdown source
   and the HTML to `/tmp/email-digest-{project}-{YYYY-MM-DD}.{md,html}`,
   list the attachments that *would* be sent (with size for each), print
   the proposed subject line, and exit without calling Graph. The user
   can open the .html in a browser to preview exactly what the recipient
   will see.

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
- **HTML body + markdown attachment:** Body ships as styled HTML so
  humans see properly-rendered headings/tables in their inbox. The
  source markdown rides as an attachment so recipient agents can parse
  the original `<!-- dashboard-digest v1 ... -->` header and tables
  cleanly. Agents that only have HTML can still grep the body — the
  header comment is preserved in the rendered output.
- **Idempotency:** Graph does not deduplicate sends. Calling this skill
  twice in the same day will deliver two emails. The recipient agent
  uses the digest header to recognize and merge — but to avoid noise,
  prefer scheduled runs (one per day for `--window daily`).
