---
name: project
version: 1.1
description: View or update project context
---

# /project

View or update full context for one project. Calls `get_project_context` and `update_project_context` MCP tools.

## Usage

```
/project flotilla                        # view context
/project flotilla --focus "Terminal layout"  # update focus
/project flotilla --next "Add E2E tests"     # add next step
/project flotilla --done "Add Project modal" # remove completed step
/project flotilla --blocker "Waiting on API" # add blocker
/project flotilla --unblock "Waiting on API" # remove blocker
/project flotilla --question "Should we merge captures?" # add question
/project flotilla --subscribe                # show on this machine's /dashboard
/project flotilla --unsubscribe              # hide on this machine's /dashboard
```

## Behavior

### View mode (no flags)

1. Call `mcp__knowledge__get_project_context` with project name
2. Format output:

```
┌─ {project} ──────────────────────────────────────────────┐
│ Status: {STATUS}          Updated: {updated_at}          │
│ Focus:  {focus}                                          │
│                                                          │
│ NEXT STEPS                                               │
│ 1. [ ] {next_steps[0]}                                   │
│ 2. [ ] {next_steps[1]}                                   │
│                                                          │
│ BLOCKERS                                                 │
│ ! {blockers[0]}                                          │
│                                                          │
│ OPEN QUESTIONS                                           │
│ ? {open_questions[0]}                                    │
│                                                          │
│ RECENT JOURNAL                                           │
│ {created_at}  {entry}                                    │
│                                                          │
│ RECENT DECISIONS                                         │
│ {id}  {title}                            {date}          │
└──────────────────────────────────────────────────────────┘
```

### Update mode (with flags)

1. Parse flags into update fields
2. For `--done`: remove the matching item from next_steps array
3. For `--unblock`: remove the matching item from blockers array
4. For `--next`: append to next_steps array
5. For `--blocker`: append to blockers array
6. For `--question`: append to open_questions array
7. For `--focus`: set focus field (auto-journals the change)
8. Call `mcp__knowledge__update_project_context` with the changes
9. Show updated context

### Subscription flags (machine-local, no MCP call)

`--subscribe` / `--unsubscribe` edit the per-machine view file at
`~/.claude/dashboard-subscriptions.json` and do **not** touch the shared
knowledge DB. They control which projects appear on this machine's
`/dashboard` (multi-project mode).

File format: `{"subscribed": ["agents", "paul-jason"]}`

Behavior:

1. Read the file. If missing or malformed, treat as `{"subscribed": []}`.
2. **`--subscribe`**: add the project name to `subscribed` if not already
   present. Write the file back. Confirm with: `subscribed to {name} on this
   machine — will appear in /dashboard`.
3. **`--unsubscribe`**: remove the project name from `subscribed` if
   present. Write the file back. Confirm with: `unsubscribed from {name} on
   this machine — hidden from /dashboard (use --all to see all)`.
4. Subscription flags do not require the project to exist in the tracker —
   they're a machine-local view preference.
5. Subscription flags can be combined with other flags in the same
   invocation (e.g. `/project foo --focus "bar" --subscribe`); apply MCP
   updates first, then update the subscription file.
