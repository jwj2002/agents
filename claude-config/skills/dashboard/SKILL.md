---
name: dashboard
version: 6.0
description: Cross-project status overview (or single-project deep view via cwd detection / explicit name) with windowed activity (daily/weekly/monthly/full), owner filter, and markdown digest format for agent-to-agent email
---

# /dashboard

Show project status. Source of truth is **Knowledge MCP**. Operational
signals (last commit, open issues) come from `git`/`gh` directly, not
from a separate service.

Two modes:

- **Single-project deep view** — full focus, all next steps, all issues,
  recent journal, recent decisions. Triggered by cwd auto-detection or
  explicit project name.
- **Multi-project overview** — active cards with full listings, paused
  cards condensed, blocked cards show only blockers. Triggered by
  `--all` or running outside any tracked project.

## Usage

```
/dashboard                          # cwd-detect; window=daily by default
/dashboard flotilla                 # explicit single-project deep view
/dashboard --all                    # multi-project, ignore subscription filter
/dashboard --status active          # multi-project, filter by status

# Activity window — applies to issues, actions, decisions, journal, patterns
/dashboard --window daily           # open + closed/created in last 24h (DEFAULT)
/dashboard --window weekly          # open + closed/created in last 7d
/dashboard --window monthly         # open + closed/created in last 30d
/dashboard --window full            # no window — show all states / full history

# Owner filter (Actions only — issues/decisions/journal stay shared)
/dashboard paul-jason --for Paul    # actions where Owner=Paul; shared context untouched

# Output format
/dashboard --format terminal        # ASCII boxes (DEFAULT)
/dashboard --format markdown        # parseable markdown digest with stable header
                                    # — used as body for agent-to-agent email digests

# Common combos
/dashboard paul-jason --window weekly --for Paul --format markdown
/dashboard --window daily --format markdown   # multi-project markdown digest
```

## Activity Window

Every multi-row section (issues, actions, decisions, journal, patterns) is
filtered by an **activity window**. Default is `daily`.

| Window  | Open items | "In window" closed/created items |
|---------|------------|-----------------------------------|
| daily   | always     | last 24h                          |
| weekly  | always     | last 7d                           |
| monthly | always     | last 30d                          |
| full    | always     | no filter — full history          |

What "in window" means per source:

- **Issues (gh)**: `closedAt >= now - window` (closed in window) OR
  `state=open`. Always include open. For `full`, include all states.
- **Actions (ACTIONS.md)**: `## Open` table is always included; `## Recently
  Closed` rows are included if `Closed >= now - window`. For `full`, also
  include `## Archive` rows.
- **Decisions**: `created_at >= now - window`. For `full`, show all (still
  cap multi-project rendering at 10 most-recent for sanity).
- **Journal**: `created_at >= now - window`. For `full`, show last 20.
- **Patterns**: same as decisions — filter by `created_at`. Section is
  hidden when zero rows in window (most days).

Closed-in-window rows render with `✓` and the closed date suffix in
terminal mode.

## Owner Filter

`--for <owner>` filters **Actions only** to rows where `Owner == <owner>`
(case-insensitive). Issues, decisions, journal, blockers, and questions
are shared context and are not filtered. This lets a digest sent *to Paul*
foreground Paul's actions without losing the surrounding context.

`--for` is silently ignored in multi-project mode unless combined with
`--format markdown` (where it filters Action counts per card).

## Output Format Selector

`--format` controls the rendering surface:

- `terminal` (default): ASCII boxes, friendly to read in a terminal. May
  truncate long Action text to fit card width.
- `markdown`: parseable markdown with explicit tables and a stable
  digest header. **No truncation** — emit the full content so a recipient
  agent can sync it back into its own state.

The markdown digest always begins with a stable HTML comment so a
downstream agent can recognize and idempotently consume it:

```
<!-- dashboard-digest v1 {project_or_multi} {window} {YYYY-MM-DD} -->
```

For multi-project markdown the project segment is the literal `multi`.

## Per-Machine Subscriptions

Multi-project mode is filtered by a per-machine subscription file at
`~/.claude/dashboard-subscriptions.json`. This keeps the shared knowledge DB
free of machine-specific view state — different laptops can subscribe to
different projects.

File format:

```json
{
  "subscribed": ["agents", "paul-jason"]
}
```

Filter rules (multi-project mode only):

- File **exists** with non-empty `subscribed` array → show only those projects.
  If a subscribed name isn't in the tracker, silently skip it (no error).
- File **missing**, malformed, or `subscribed` is empty/absent → show all
  tracked projects (back-compat).
- `--all` flag → bypass the filter and show everything in the tracker.

Single-project mode is **not** filtered — explicit `/dashboard <name>` and
cwd-detection always work even if the project isn't subscribed on this
machine.

Manage subscriptions with `/project <name> --subscribe` and `--unsubscribe`.

## Mode Selection

1. If `--all` is present → multi-project mode.
2. If a positional argument is present (e.g. `flotilla`) → single-project mode for that name.
3. Otherwise: read `pwd`. Strip `$HOME/projects/` prefix; if remaining path's first segment matches a tracked project, single-project mode for that name. Special case: `$HOME/agents` → `agents` project.
4. If no match and no flag → multi-project mode (today's default).

If single-project mode resolves to a project that isn't in the tracker,
emit a one-line notice ("project `X` not tracked — use `/project X --focus
\"...\"` to add it") and fall back to multi-project mode.

## Data Sources

### Knowledge MCP (REQUIRED)

**Multi-project mode:**
1. `mcp__knowledge__get_dashboard` — returns projects with focus,
   next_steps, blockers, open_questions, updated_at + `inbox_open` count.
2. `mcp__knowledge__get_inbox` with `status: "open"` — flat list. Group by
   `project` client-side.

**Single-project mode:**
1. `mcp__knowledge__get_project_context` with the resolved project name —
   returns focus, status, next_steps, blockers, open_questions, plus
   `recent_journal` (last 20) and `recent_decisions` (last 10).
2. `mcp__knowledge__get_inbox` with `project: "<name>", status: "open"` —
   only this project's captures.

### ACTIONS.md overlay (OPTIONAL — per-project repo file)

For each project, look for an `ACTIONS.md` at the resolved repo path
(`~/projects/{name}/ACTIONS.md`, special case `agents` →
`~/agents/ACTIONS.md`). If present, parse three tables:

**`## Open`** — open work:
```
| ID | Issue | Action | Owner | Status | Opened | Src | Notes |
```

**`## Recently Closed`** — closed within ~30d:
```
| ID | Issue | Action | Owner | Closed | Notes |
```

**`## Archive`** — closed beyond Recently Closed window. Only read for
`--window full`.

Rules:

- From `## Open`: include rows whose `Status` is `open`, `wip`, or
  `blocked`. Skip `done`/`cancelled` (they belong in Recently Closed).
- From `## Recently Closed`: include rows whose `Closed >= now - window`.
- From `## Archive`: only when `--window full`.
- A row is parsed if it has at least the `ID`, `Action`, `Owner`, and
  status-or-closed cell. Missing optional cells are fine.
- Trim whitespace; treat empty cells as missing.
- Apply `--for <owner>` filter (case-insensitive) to Action rows only.
- If a file is missing or has no parseable rows, treat as zero (no error).

Status indicators when rendering (terminal):
- `open` → no prefix
- `wip` → ` ⚙` suffix
- `blocked` → ` ⛔` suffix
- closed-in-window → ` ✓ {YYYY-MM-DD}` suffix

### git/gh overlay (OPTIONAL — graceful degradation per project)

For each project, attempt to resolve a local repo path using the convention
`~/projects/{project_name}`. Special case: `agents` → `~/agents`. If the
path doesn't exist or isn't a git repo, skip overlay for that project (no
error, just no commit/issue fields rendered).

**Active projects (per project, parallel):**

```bash
git -C <repo> log -1 --format='%s|%ar' 2>/dev/null

# open issues (always)
gh -R <github_slug> issue list --state open --limit 100 \
    --json number,title 2>/dev/null

# closed-in-window issues (skip when --window full → use --state all)
gh -R <github_slug> issue list --state closed \
    --search "closed:>=$WINDOW_START_DATE" \
    --limit 50 --json number,title,closedAt 2>/dev/null

# total open count
gh -R <github_slug> issue list --state open --json number \
    -q 'length' 2>/dev/null
```

`$WINDOW_START_DATE` = today minus 1d/7d/30d depending on `--window`. For
`--window full`, drop the `--state closed --search ...` call and instead
fetch `--state all` paginated.

Resolve `<github_slug>` from `git -C <repo> config --get remote.origin.url`
(parse `owner/repo` from either `git@github.com:owner/repo.git` or
`https://github.com/owner/repo.git`).

**Paused/blocked projects:** skip the closed-issue and title queries; just
get the open count. Counts in window-aware form: `Issues: N open` (no
closed segment for paused cards — they're paused).

**Timeout:** 3 seconds per command. If anything times out, that project
just shows the Knowledge MCP fields without overlay.

## Output Format

### Single-Project Deep View (terminal)

Wider card (~80 chars). All rows uncapped. Window-scoped sections:

```
PROJECT: flotilla                                              ACTIVE
┌──────────────────────────────────────────────────────────────────────────────┐
│ Focus:  Phase 4 automation complete — auto-blockers, auto-status,        1d │
│         auto-journal, stale prompts live                                     │
│ Last:   feat: ProjectView Context section (#199)                        33h │
│                                                                              │
│ Next Steps:                                                                  │
│ 1. Test automation end-to-end across all projects                            │
│ 2. Plan Phase 3 (multi-env + client engagement setup) when needed            │
│ 3. Monitor dashboard for drift over a week of real use                       │
│                                                                              │
│ Issues (1 open):                                                             │
│   #16  feat: admin agent should escalate blocked messages to human via      │
│        dashboard                                                             │
│                                                                              │
│ Actions (3 open):                                                            │
│   A-001  Jason  Review material Paul sent (transcripts, PRD, debrief...)    │
│   A-002  Jason  Get v0.5B running on JBox                                ⚙  │
│   A-009  Paul   Finish & freeze v0.6 by tonight                          ⛔  │
│                                                                              │
│ Captures (1 open):                                                           │
│   #2 [idea]  Add dark/light theme toggle to flotilla dashboard              │
│                                                                              │
│ ? Open Questions:                                                            │
│   Should /weekly digest auto-post to Slack or just render in terminal?      │
│                                                                              │
│ Recent Journal (5):                                                          │
│   2026-04-18  focus_change  Phase 4 automation complete — auto-blockers     │
│   2026-04-18  commit        feat: ProjectView Context section (#199)        │
│   2026-04-18  focus_change  Phase 2 integration complete                    │
│   ...                                                                        │
│                                                                              │
│ Recent Decisions (5):                                                        │
│   D-098  2026-04-08  Federated flotilla instances with WebSocket bridge     │
│   D-095  2026-04-07  Orchestration accountability — strategic creates...    │
│   ...                                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

Single-project view rules:
- All next_steps shown (not capped)
- **Issues**: all open + all closed-in-window. Closed rows render with
  `✓ {YYYY-MM-DD}`. Header: `Issues (N open, M closed-{window})`.
- **Actions**: all open `## Open` rows + all closed-in-window
  `## Recently Closed` rows (and `## Archive` rows when `--window full`).
  Format `{ID}  {Owner}  {Action}` with status suffix. Apply `--for`
  filter to this section only. Header: `Actions (N open, M closed-{window})`
  — or `Actions (N for {Owner}; M closed-{window})` when `--for` is set.
- **Captures**: all open captures (no window filter — captures are
  ephemeral inbox items and stay until triaged).
- **Decisions (in window)**: filter `recent_decisions` by `created_at >=
  now - window`. Show `{id}  {date}  {title}`. Section omitted if zero.
  For `--window full`: show last 10.
- **Patterns (in window)**: query `mcp__knowledge__get_patterns`, filter
  by created/touched-in-window. Section omitted if zero.
- **Journal (in window)**: filter `recent_journal` by `created_at >= now -
  window`. Show `{date}  {entry_type}  {entry}`. For `--window full`:
  show last 20.
- Status label appears top-right (`ACTIVE` / `PAUSED` / `BLOCKED` / `DONE`)
- Inbox footer shows project-scoped count only (not the cross-project sum)
- Stale prompt suppressed (single-project mode is implicitly focused)
- Window label appears under status, e.g. `window: daily (since 2026-05-04)`

### Active Projects — Full Listing

```
ACTIVE
┌─ flotilla ─────────────────────────────────────────────────────┐
│ Focus: Phase 2 integration complete                       now │
│ Last:  feat: ProjectView Context section (#199)           now │
│                                                                │
│ Next Steps:                                                    │
│ 1. Build MCP tools for dashboard, project context             │
│ 2. Create CLI skills (/dashboard, /project, /capture)          │
│ 3. Flotilla integration — Context section in ProjectView       │
│                                                                │
│ Issues (1 open):                                               │
│   #16  feat: admin agent should escalate blocked messages     │
│                                                                │
│ Captures (1 open):                                             │
│   #2 [idea]  Add dark/light theme toggle to flotilla          │
│                                                                │
│ ! Blockers:                                                    │
│   AD connection details from infra                             │
│                                                                │
│ ? Open Questions:                                              │
│   Should /weekly auto-post to Slack?                           │
└────────────────────────────────────────────────────────────────┘
```

### Paused Projects — Condensed View

Paused cards do **not** apply the window — they show open counts only.
The whole point of paused is "no recent activity expected."

```
PAUSED
┌─ buddy ────────────────────────────────────────────────────────┐
│ Focus: Meeting transcription pipeline          ⚠ 10d stale   │
│ Last:  fix(config): strip voice_unified_reasoning         19d │
│ Next:  Fix audio chunking > Add speaker labels                │
│ Issues: 1 open  |  Captures: 0                                │
└────────────────────────────────────────────────────────────────┘
```

### Blocked Projects — Show Blockers

```
BLOCKED
┌─ project-name ─────────────────────────────────────────────────┐
│ Focus: Current focus                             ⚠ 5d stale  │
│ ! Blockers:                                                    │
│   Waiting on client API contract                               │
└────────────────────────────────────────────────────────────────┘
```

### Footer

```
INBOX (2 open — triage with /inbox)
```

### Stale Project Prompt

After rendering the dashboard, if any **active** project has `updated_at`
>48h ago, append a prompt:

```
⚠ Stale context detected:
  - flotilla (3d since last update)
  - routeiq (5d since last update)

To update: /project {name} --focus "..."
```

Only active projects trigger this. Paused projects are expected to be stale.
This is a passive notice — no blocking interaction.

### Post-Session Review Nudge

Check `~/.claude/pending_focus_reviews.json`. If it exists with non-empty
entries, show a one-line notice at the TOP of the dashboard output:

```
📝 2 projects have session activity to review — run /review-session
```

Count = number of project keys in the pending file. Don't list them — that's
/review-session's job. This is a gentle nudge, not a blocker.

No notice shown if the file doesn't exist or has no entries.

## Rendering Rules

### All Cards
- `Focus` line: focus + right-aligned staleness (⚠ Nd stale if >48h, else relative time)
- `Last` line: last commit message truncated + relative time (omitted if no repo overlay)

### Active Cards
- **Next Steps**: numbered list, first 3 items (full text, not truncated)
- **Issues**: up to 3 most recent open + up to 3 closed-in-window.
  Format `#N  title`; closed rows have ` ✓ {date}` suffix. Header:
  `(N open, M closed-{window})`. If either count exceeds 3, add a
  `+{rest} more` line. Omit entirely if no repo overlay.
- **Actions** (from ACTIONS.md): up to 5 open + up to 5 closed-in-window
  rows. Header `(N open, M closed-{window})`. Honors `--for` if set.
  Omit if no ACTIONS.md.
- **Decisions (in window)**: up to 5 most-recent within window.
  Section omitted if zero.
- **Captures**: all open captures for this project (usually <5), format
  `#N [type]  content`. Header `(N open)`.
- **Blockers**: all blockers, format `  {blocker text}`. Shown if any.
- **Open Questions**: all questions, format `  {question text}`. Shown if any.

### Paused Cards
- Focus + Last + Next (first 1-2 joined with ` > `) + counts only
- `Issues: N open | Actions: N open | Captures: N` — only include the
  segments whose count is > 0; join with ` | `. Omit line entirely if all
  zero.
- Window not applied to paused cards (open counts only).
- Issue count comes from `gh` overlay if available, else omitted
- Actions count comes from ACTIONS.md overlay if present, else omitted

### Blocked Cards
- Focus + Blockers (full list). Issues/captures/next hidden — fix the blocker first.

## Markdown Digest Format

When `--format markdown`, emit a parseable digest instead of ASCII boxes.
**No truncation** — the digest is a wire format for downstream agents.

### Single-project markdown

```markdown
<!-- dashboard-digest v1 paul-jason daily 2026-05-05 -->
# paul-jason — daily summary (2026-05-05)

**Status:** ACTIVE
**Focus:** Paul and Jason recurring one-on-one
**Window:** daily (since 2026-05-04)
**Owner filter:** Paul          <!-- omitted when --for not set -->

## Next Steps
1. ...

## Issues

### Open (N)
| #  | Title | Updated |
|----|-------|---------|

### Closed in window (M)
| #  | Title | Closed |
|----|-------|--------|

## Actions

### Open (N)
| ID | Owner | Action | Status | Opened | Notes |
|----|-------|--------|--------|--------|-------|

### Closed in window (M)
| ID | Owner | Action | Closed | Notes |
|----|-------|--------|--------|-------|

## Decisions in window (N)
| ID | Date | Title |
|----|------|-------|

## Patterns in window (N)        <!-- section omitted when zero -->
| ID | Date | Title |

## Blockers                      <!-- omitted when none -->
- ...

## Open Questions                <!-- omitted when none -->
- ...

## Journal in window (N)
| Date | Type | Entry |

## Captures (N open)             <!-- omitted when zero -->
- #2 [idea] ...
```

### Multi-project markdown

```markdown
<!-- dashboard-digest v1 multi daily 2026-05-05 -->
# Multi-project — daily summary (2026-05-05)

**Window:** daily (since 2026-05-04)
**Subscriptions:** agents, paul-jason  <!-- when filter active -->

## paul-jason (ACTIVE)
**Focus:** Paul and Jason recurring one-on-one
**Counts:** Issues 0 open / 0 closed | Actions 16 open / 0 closed | Decisions 0 | Captures 0

[…repeat single-project sections inline, with H3 headers instead of H2…]

## agents (BLOCKED)
**Focus:** Stack consolidation — …
**Blockers:** Phase 2 channels: pick A/B/C
```

Rules:
- Counts line on each project header with the per-window numbers.
- Sections that would be empty are **omitted** (not rendered as "0").
- The first line is always the stable header comment so a downstream
  agent can recognize the digest. Header format:
  `dashboard-digest v1 {project_or_multi} {window} {YYYY-MM-DD}`.

## Graceful Degradation

1. **Knowledge MCP unreachable**:
   - Error message: "Knowledge MCP unavailable — /dashboard cannot render"
   - No fallback. Knowledge MCP is the single source of truth.

2. **Repo path missing or not a git repo for a project**:
   - Skip git/gh calls for that project
   - Card renders with Knowledge MCP fields only (no Last/Issues lines)

3. **`gh` not authenticated or rate-limited**:
   - Per-project: card renders without Issues line
   - No global error — the dashboard always returns

4. **Per-command timeout (3s)**:
   - Command result discarded for that project
   - Card renders with whatever else succeeded

## Execution Order

### Step 0 — Mode resolution

1. Parse args:
   - `--all`, `--status <s>`, positional project name (mode selectors)
   - `--window daily|weekly|monthly|full` (default: `daily`)
   - `--for <owner>` (default: none)
   - `--format terminal|markdown` (default: `terminal`)
2. If `--all` → multi-project mode.
3. Else if positional name → single-project mode for that name.
4. Else: read `pwd`. If `pwd == $HOME/agents` or starts with `$HOME/agents/`, mode = single-project (`agents`). If `pwd` starts with `$HOME/projects/`, take the first segment after; if it matches a tracked project, mode = single-project (that name).
5. Else → multi-project mode.
6. Compute `WINDOW_START` = today minus 1d/7d/30d, or null for `full`.

### Single-project mode

1. `mcp__knowledge__get_project_context` with the resolved name.
2. If null/error → emit `project "<name>" not tracked — use /project <name> --focus "..." to add it`, then fall through to multi-project mode.
3. `mcp__knowledge__get_inbox` with `project: "<name>", status: "open"`.
4. Resolve repo path (same convention).
   - Read `{repo_path}/ACTIONS.md` if present; parse `## Open` (always),
     `## Recently Closed` (filter rows by `Closed >= WINDOW_START`), and
     `## Archive` (only when `--window full`). Apply `--for` filter.
     Repo without `.git` is fine — ACTIONS.md is independent of git.
   - If the path is a git repo: parallel
     - `git log -1 --format='%s|%ar'`
     - `gh issue list --state open --limit 100 --json number,title,updatedAt`
     - For `daily`/`weekly`/`monthly`:
       `gh issue list --state closed --search "closed:>=$WINDOW_START_DATE" --limit 50 --json number,title,closedAt`
     - For `full`: `gh issue list --state all --limit 200 --json number,title,state,closedAt`
5. Filter Knowledge MCP fields by window:
   - `recent_decisions` → keep where `created_at >= WINDOW_START` (or all
     for `full`)
   - `recent_journal` → keep where `created_at >= WINDOW_START` (or all
     for `full`)
6. Optional patterns query: `mcp__knowledge__get_patterns`, filter by
   in-window timestamps. Section omitted when empty.
7. Render per `--format`:
   - `terminal` → Single-Project Deep View card
   - `markdown` → Single-project markdown digest with stable header.

### Multi-project mode

1. `mcp__knowledge__get_dashboard` (with `status` if provided)
2. **Apply subscription filter** (unless `--all`): read
   `~/.claude/dashboard-subscriptions.json`. If it parses to an object with a
   non-empty `subscribed` array, drop any project whose name isn't in that
   array. If the file is missing, malformed, or has no/empty `subscribed`,
   show all (back-compat).
3. `mcp__knowledge__get_inbox` with `status: "open"` — group by project
   client-side, then drop entries whose project was filtered out above.
4. For each project in result:
   - Resolve repo path (`~/projects/{name}`, special case `agents` → `~/agents`)
   - Read `{repo_path}/ACTIONS.md` if present:
     - For **active** projects: count open + count closed-in-window
     - For **paused/blocked**: count open only (no window)
   - If repo exists and is a git repo:
     - Resolve github slug from origin URL
     - For **active** projects: parallel `git log` + `gh issue list --limit 3 --state open` + `gh issue list -q 'length'` + `gh issue list --state closed --search "closed:>=$WINDOW_START_DATE" --limit 3` (skip closed query for `--window full`; use `--state all` instead)
     - For **paused/blocked** projects: parallel `git log` + `gh issue list -q 'length'` only
5. Filter Knowledge data per project: in-window decisions count; in-window
   patterns count (active projects only).
6. Merge all overlays with Knowledge MCP data per project.
7. Render per Output Format. With `--format markdown`, emit the
   Multi-project markdown digest with stable header. With
   `--format terminal`, render ASCII cards (active/paused/blocked shapes).
8. Append inbox footer + stale prompt + review nudge as applicable
   (terminal only — markdown digest skips the trailing nudges).

## Notes

- This skill replaces the prior Flotilla-API-based dashboard. There is no
  longer a service to keep running for `/dashboard` to work.
- Across machines, the convention `~/projects/{name}` should hold; if a
  machine puts repos elsewhere, the skill silently degrades to Knowledge-only.
- If you need WIP/agent-work tracking, use `git branch --list 'feature/*'` —
  there is no Flotilla equivalent in the consolidated stack.
