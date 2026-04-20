---
name: dashboard
version: 5.0
description: Cross-project status overview with automation (auto-blockers, auto-status, auto-journal) and stale project prompt
---

# /dashboard

Show cross-project status at a glance. Source of truth is **Knowledge MCP**.
Operational signals (last commit, open issues) come from `git`/`gh` directly,
not from a separate service.

Active projects show full listings (next steps, issues, captures, blockers,
questions). Paused projects show condensed view (focus + counts).

## Usage

```
/dashboard
/dashboard --status active
```

## Data Sources

### Knowledge MCP (REQUIRED — always call)

1. `mcp__knowledge__get_dashboard` — returns projects with focus,
   next_steps, blockers, open_questions, updated_at + `inbox_open` count.
2. `mcp__knowledge__get_inbox` with `status: "open"` — flat list. Group by
   `project` client-side.

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
