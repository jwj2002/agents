---
name: project
version: 1.0
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
