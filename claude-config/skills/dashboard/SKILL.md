---
name: dashboard
version: 2.0
description: Cross-project status overview (Knowledge MCP + Flotilla)
---

# /dashboard

Show cross-project status at a glance. Merges context from **Knowledge MCP** (focus,
next steps, blockers, inbox) with operational data from **Flotilla** (last commit,
open issues, work in progress) when Flotilla is reachable.

## Usage

```
/dashboard
/dashboard --status active
```

## Data Sources

### Knowledge MCP (REQUIRED — always call)

1. `mcp__knowledge__get_dashboard` — returns:
   ```json
   {
     "projects": [
       { "project": "flotilla", "status": "active", "focus": "...",
         "next_steps": ["..."], "blockers": ["..."], "open_questions": ["..."],
         "updated_at": "..." }
     ],
     "inbox_open": 3
   }
   ```
   Pass `status` arg if `--status` flag was provided.

2. `mcp__knowledge__get_inbox` with `status: "open"` — returns a flat list of
   inbox items each with a `project` field. Group client-side by `project` to
   compute **captures per project** count.

### Flotilla API (OPTIONAL — graceful degradation)

Base URL: `http://localhost:9000`. Use a short timeout (2s) so the command
stays snappy when the service is down.

1. Health probe — decide whether to call Flotilla at all:
   ```bash
   curl -s --max-time 2 -o /dev/null -w '%{http_code}' \
     http://localhost:9000/api/v1/health
   ```
   If this is **not** `200`, skip all Flotilla calls and render the
   Knowledge-only view (see Graceful Degradation below).

2. `GET /api/v1/projects` — returns `{"projects": [...]}`. Each project has:
   - `id`, `name`, `category`, `status`
   - `last_commit_message`, `last_commit_at` (from GitHub sync)
   - `open_issues`, `open_prs`
   - `agent_count`, `agents_blocked`, `last_activity_at`

3. `GET /api/v1/projects/{id}/work` — returns `{"items": [...]}`. Filter for
   items with `status IN ('leased', 'in_progress')` to get **WIP**. Each
   work item has: `issue_number`, `status`, `title` (or `issue_title`),
   `agent_id`.

   Only call this for projects that also appear in the Knowledge dashboard
   (skip Flotilla projects with no Knowledge counterpart — nothing to merge
   onto).

## Merge Logic

Match by **project name**: Flotilla `project.name` == Knowledge `project_tracker.project`.
Names are user-controlled and expected to be identical (e.g. both `"flotilla"`,
`"buddy"`, `"mymoney-dev"`). Match is case-insensitive to be safe.

For each Knowledge project, attach optional Flotilla fields when a matching
Flotilla project exists:

| Field | Source |
|-------|--------|
| `focus`, `next_steps`, `blockers`, `open_questions`, `status`, `updated_at` | Knowledge |
| `last_commit_message`, `last_commit_at` | Flotilla `project.last_commit_*` |
| `open_issues`, `open_prs` | Flotilla `project.open_issues/open_prs` |
| `wip` (list of in-progress work items) | Flotilla `/projects/{id}/work` filtered to `leased`/`in_progress` |
| `captures_open` | Count of Knowledge inbox items where `item.project == project` and `status == 'open'` |

If no Flotilla match: the operational fields are simply absent and their rows
are omitted from the rendered card.

## Output Format

```
Services: Flotilla ✓  Knowledge MCP ✓

ACTIVE
┌─ flotilla ─────────────────────────────────────────────┐
│ Focus: Cross-env platform — Phase 2           1h ago │
│ Last:  fix: Start endpoint signal-only (#177) 1h ago │
│ ▶ WIP: #193 Playwright E2E (agent running)           │
│ Next:  1. Phase 2 Flotilla integration                │
│ Issues: 4 open  |  Captures: 2 open                   │
└────────────────────────────────────────────────────────┘

PAUSED
┌─ buddy ────────────────────────────────────────────────┐
│ Focus: Meeting transcription pipeline      ⚠ 10d stale │
│ Last:  fix: audio chunking (2w ago)                   │
│ Next:  Fix audio chunking > Add speaker labels        │
│ Issues: 1 open                                         │
└────────────────────────────────────────────────────────┘

INBOX (2 open — triage with /inbox)
```

### Rendering rules

- Header `Services:` line: always show both, with `✓` if reachable or `✗` if not.
- Group projects by `status`: `ACTIVE` first, then `PAUSED`, then `BLOCKED`.
  Omit section headers for empty groups.
- `Focus` line: project focus + right-aligned staleness indicator.
  - Staleness computed from Knowledge `updated_at`: if >48h ago, show
    `⚠ {N}d stale`; otherwise show a relative time (e.g. `1h ago`, `3d ago`).
- `Last` line (Flotilla only): `{last_commit_message} ({relative last_commit_at})`.
  Truncate message to fit card width. Omit line if Flotilla down or no commit data.
- `▶ WIP` line (Flotilla only): show up to 2 in-progress items as
  `#{issue_number} {title}`. Omit if none.
- `Next` line: first 1–2 items from Knowledge `next_steps`, joined with ` > `.
  Omit if empty.
- `! Blocked` line: first blocker from Knowledge `blockers`. Omit if empty.
- `? Open` line: first question from Knowledge `open_questions`. Omit if empty.
- `Issues: X open  |  Captures: Y open` line:
  - Include `Issues` only if Flotilla is up (from `project.open_issues`).
  - Include `Captures` always (from grouped inbox count). Omit if both are 0.
  - Use ` | ` separator only when both halves are present.
- `INBOX (N open — triage with /inbox)` footer: use total `inbox_open` from
  `get_dashboard` response.

## Graceful Degradation

1. **Flotilla unreachable** (health check fails or times out):
   - Services line shows `Flotilla ✗`.
   - Skip `GET /api/v1/projects` and `/work` entirely.
   - Cards omit `Last`, `▶ WIP`, and `Issues` lines.
   - Captures and all Knowledge-sourced lines still render.
   - This is the legacy `v1.0` behavior — everything continues to work.

2. **Knowledge MCP unreachable** (tool call errors):
   - Report the error to the user: `Knowledge MCP unavailable — /dashboard
     cannot render without project context.`
   - Do not fall back to a Flotilla-only view — project context is the spine
     of the dashboard.

3. **Partial Flotilla failure** (health OK but `/projects` or `/work` errors):
   - Treat as Flotilla down — fall back to Knowledge-only view and note the
     error briefly above the Services line.

## Execution Order

1. Call `mcp__knowledge__get_dashboard` (with `status` if provided).
2. Call `mcp__knowledge__get_inbox` with `status: "open"`.
3. Health-probe Flotilla with a 2s timeout.
4. If healthy: `GET /api/v1/projects`, then `GET /projects/{id}/work` for each
   Flotilla project that has a Knowledge match (parallel is fine).
5. Merge by project name (case-insensitive).
6. Render per the Output Format above.
