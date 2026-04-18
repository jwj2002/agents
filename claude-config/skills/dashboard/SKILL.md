---
name: dashboard
version: 3.0
description: Cross-project status overview (Knowledge MCP + Flotilla) with issue and capture listings
---

# /dashboard

Show cross-project status at a glance. Merges context from **Knowledge MCP** (focus,
next steps, blockers, inbox) with operational data from **Flotilla** (last commit,
open issues, work in progress) when Flotilla is reachable.

Active projects show full listings (next steps, issues, captures, blockers, questions).
Paused projects show condensed view (focus + counts).

## Usage

```
/dashboard
/dashboard --status active
```

## Data Sources

### Knowledge MCP (REQUIRED — always call)

1. `mcp__knowledge__get_dashboard` — returns projects with focus, next_steps, blockers, open_questions, updated_at + `inbox_open` count.
2. `mcp__knowledge__get_inbox` with `status: "open"` — flat list. Group by `project` client-side.

### Flotilla API (OPTIONAL — graceful degradation)

Base URL: `http://localhost:9000`. 2s timeout on all calls.

1. Health probe: `curl -s --max-time 2 -o /dev/null -w '%{http_code}' http://localhost:9000/api/v1/health` — must be `200` to proceed.
2. `GET /api/v1/projects` — returns `{"projects": [...]}` with `id`, `name`, `last_commit_message`, `last_commit_at`, `open_issues`, `open_prs`.
3. `GET /api/v1/projects/{id}/work` — returns `{"items": [...]}`. Filter for `status IN ('leased', 'in_progress')` for WIP.
4. `GET /api/v1/projects/{id}/issues?state=open&limit=3` — returns `{"issues": [...]}` with `issue_number`, `title`. **Only for ACTIVE projects.**

## Merge Logic

Match by project name (case-insensitive). Attach Flotilla fields when a match exists.

## Output Format

### Active Projects — Full Listing

Show all details for active projects since these are the focus:

```
ACTIVE
┌─ flotilla ─────────────────────────────────────────────────────┐
│ Focus: Phase 2 integration complete                       now │
│ Last:  feat: ProjectView Context section (#199)           now │
│ ▶ WIP: #193 Playwright E2E (agent running)                    │
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

Paused projects show one-line focus + counts only (you're not actively tracking):

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

## Rendering Rules

### All Cards
- `Focus` line: focus + right-aligned staleness (⚠ Nd stale if >48h, else relative time)
- `Last` line (Flotilla): last commit message truncated + relative time
- `▶ WIP` line (Flotilla): up to 2 in-progress items (active projects only)

### Active Cards
- **Next Steps**: numbered list, first 3 items (full text, not truncated)
- **Issues**: up to 3 most recent open GitHub issues, format `#N  title`. Header shows `(N open)` where N is the total count. If more than 3, add `  +{N-3} more` on a line below.
- **Captures**: all open captures for this project (usually <5), format `#N [type]  content`. Header shows `(N open)`.
- **Blockers**: all blockers, format `  {blocker text}`. Only shown if blockers exist.
- **Open Questions**: all questions, format `  {question text}`. Only shown if questions exist.

### Paused Cards
- Focus + Last + Next (first 1-2 joined with ` > `) + counts only
- `Issues: N open | Captures: N` — use ` | ` only if both non-zero, omit line if both zero

### Blocked Cards
- Focus + Blockers (full list). Issues/captures/next hidden — fix the blocker first.

## Graceful Degradation

1. **Flotilla unreachable**:
   - Services line: `Flotilla ✗`
   - Skip all Flotilla calls
   - Omit `Last`, `WIP`, `Issues` from cards
   - Captures and Knowledge data still render

2. **Knowledge MCP unreachable**:
   - Error message: "Knowledge MCP unavailable — /dashboard cannot render"
   - No fallback

3. **Partial Flotilla failure**: treat as down.

## Execution Order

1. `mcp__knowledge__get_dashboard` (with `status` if provided)
2. `mcp__knowledge__get_inbox` with `status: "open"` — group by project client-side
3. Flotilla health probe (2s timeout)
4. If healthy:
   - `GET /api/v1/projects`
   - For each **active** project: parallel `GET /projects/{id}/work` + `GET /projects/{id}/issues?state=open&limit=3`
   - For **paused/blocked** projects: skip issues endpoint (counts come from `project.open_issues`)
5. Merge by project name (case-insensitive)
6. Render per Output Format (different card shape for active vs paused vs blocked)
