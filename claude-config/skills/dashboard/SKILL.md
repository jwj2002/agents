---
name: dashboard
version: 1.0
description: Cross-project status overview
---

# /dashboard

Show cross-project status at a glance. Calls `get_dashboard` MCP tool.

## Usage

```
/dashboard
/dashboard --status active
```

## Behavior

1. Call `mcp__knowledge__get_dashboard` (no args for all, or status filter)
2. Check service health:
   - Flotilla: try `curl -s http://localhost:9000/api/v1/health` (✓ or ✗)
   - Knowledge MCP: if the tool call worked, it's up (✓)
3. Format output as:

```
Services: Flotilla ✓  Knowledge MCP ✓

ACTIVE
┌─ {project} ──────────────────────────────────────────┐
│ Focus: {focus}                          {staleness}  │
│ Next:  {next_steps[0]} > {next_steps[1]}             │
│ ! Blocked: {blockers[0]}                             │
│ ? Open: {open_questions[0]}                          │
└──────────────────────────────────────────────────────┘

PAUSED
┌─ {project} ──────────────────────────────────────────┐
│ Focus: {focus}                          {staleness}  │
└──────────────────────────────────────────────────────┘

INBOX ({inbox_open} open)
```

4. Staleness: if `updated_at` is >48h ago, show `⚠ {N}d stale`
5. Group projects by status: active first, then paused, then blocked
6. Show inbox count at bottom
