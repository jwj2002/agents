---
name: dashboard
version: 5.1
description: Cross-project status overview (or single-project deep view via cwd detection / explicit name) with automation, stale prompt, and inbox roll-up
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
/dashboard                       # cwd-detect: single-project if in a tracked repo, else multi
/dashboard flotilla              # explicit single-project deep view
/dashboard --all                 # force multi-project view (override cwd)
/dashboard --status active       # multi-project, filter by status
```

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

### git/gh overlay (OPTIONAL — graceful degradation per project)

For each project, attempt to resolve a local repo path using the convention
`~/projects/{project_name}`. Special case: `agents` → `~/agents`. If the
path doesn't exist or isn't a git repo, skip overlay for that project (no
error, just no commit/issue fields rendered).

**Active projects only — fetch all three in parallel per project:**

```bash
git -C <repo> log -1 --format='%s|%ar' 2>/dev/null         # last commit msg + relative time
gh -R <github_slug> issue list --state open --limit 3 \
    --json number,title 2>/dev/null                         # top 3 open issues
gh -R <github_slug> issue list --state open --json number \
    -q 'length' 2>/dev/null                                 # total open count
```

Resolve `<github_slug>` from `git -C <repo> config --get remote.origin.url`
(parse `owner/repo` from either `git@github.com:owner/repo.git` or
`https://github.com/owner/repo.git`).

**Paused/blocked projects:** skip the gh calls entirely. Show focus + counts
from Knowledge MCP only.

**Timeout:** 3 seconds per command. If anything times out, that project
just shows the Knowledge MCP fields without overlay.

## Output Format

### Single-Project Deep View

Wider card (~80 chars), uncapped lists, plus journal/decisions sections.

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
- All next_steps shown (not capped at 3)
- All open issues shown (not capped at 3)
- Recent journal: last 5 entries with date + entry_type + truncated text
- Recent decisions: last 5 with id + date + truncated title
- Status label appears top-right (`ACTIVE` / `PAUSED` / `BLOCKED` / `DONE`)
- Inbox footer shows project-scoped count only (not the cross-project sum)
- Stale prompt suppressed (single-project mode is implicitly focused)

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
- **Issues**: up to 3 most recent open GitHub issues, format `#N  title`. Header shows `(N open)` where N is the total count. If more than 3, add `  +{N-3} more` on a line below. Omit entirely if no repo overlay.
- **Captures**: all open captures for this project (usually <5), format `#N [type]  content`. Header shows `(N open)`.
- **Blockers**: all blockers, format `  {blocker text}`. Only shown if blockers exist.
- **Open Questions**: all questions, format `  {question text}`. Only shown if questions exist.

### Paused Cards
- Focus + Last + Next (first 1-2 joined with ` > `) + counts only
- `Issues: N open | Captures: N` — use ` | ` only if both non-zero, omit line if both zero
- Issue count comes from `gh` overlay if available, else omitted

### Blocked Cards
- Focus + Blockers (full list). Issues/captures/next hidden — fix the blocker first.

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

1. Parse args: `--all`, `--status <s>`, positional project name.
2. If `--all` → multi-project mode.
3. Else if positional name → single-project mode for that name.
4. Else: read `pwd`. If `pwd == $HOME/agents` or starts with `$HOME/agents/`, mode = single-project (`agents`). If `pwd` starts with `$HOME/projects/`, take the first segment after; if it matches a tracked project, mode = single-project (that name).
5. Else → multi-project mode.

### Single-project mode

1. `mcp__knowledge__get_project_context` with the resolved name.
2. If null/error → emit `project "<name>" not tracked — use /project <name> --focus "..." to add it`, then fall through to multi-project mode.
3. `mcp__knowledge__get_inbox` with `project: "<name>", status: "open"`.
4. Resolve repo path (same convention). If it exists:
   - parallel `git log -1 --format='%s|%ar'` + `gh issue list --state open --limit 10 --json number,title` + `gh issue list --state open --json number -q 'length'`
5. Render the Single-Project Deep View card.

### Multi-project mode

1. `mcp__knowledge__get_dashboard` (with `status` if provided)
2. `mcp__knowledge__get_inbox` with `status: "open"` — group by project client-side
3. For each project in result:
   - Resolve repo path (`~/projects/{name}`, special case `agents` → `~/agents`)
   - If repo exists and is a git repo:
     - Resolve github slug from origin URL
     - For **active** projects: parallel `git log` + `gh issue list --limit 3` + `gh issue list -q 'length'`
     - For **paused/blocked** projects: parallel `git log` + `gh issue list -q 'length'` only (skip the title list)
4. Merge git/gh data with Knowledge MCP data per project
5. Render per Output Format (different card shape for active vs paused vs blocked)
6. Append inbox footer + stale prompt + review nudge as applicable

## Notes

- This skill replaces the prior Flotilla-API-based dashboard. There is no
  longer a service to keep running for `/dashboard` to work.
- Across machines, the convention `~/projects/{name}` should hold; if a
  machine puts repos elsewhere, the skill silently degrades to Knowledge-only.
- If you need WIP/agent-work tracking, use `git branch --list 'feature/*'` —
  there is no Flotilla equivalent in the consolidated stack.
