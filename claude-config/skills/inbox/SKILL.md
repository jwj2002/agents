---
name: inbox
version: 1.0
description: View and triage inbox captures
---

# /inbox

View open inbox items and triage them.

## Usage

```
/inbox                          # show open items
/inbox assign 12 routeiq        # assign item to project
/inbox done 12                  # mark as done
/inbox dismiss 10               # dismiss (not actionable)
```

## Behavior

### View mode (no args)

1. Call `mcp__knowledge__get_inbox` with status="open"
2. Also get recently done items (last 5): `mcp__knowledge__get_inbox` with status="done"
3. Format output:

```
OPEN ({count})

#12 [task]     Check concurrent migrations           @routeiq
               Captured: 2026-04-16

#11 [question] Ask Paul about staging schedule
               Captured: 2026-04-16

#10 [idea]     Shared component library
               Captured: 2026-04-15

RECENTLY DONE (3)

#7  [task]     Split onboarding into 3 specs          done 2026-04-16
#6  [question] One project agent or many?             done 2026-04-16

Actions: /inbox assign {id} {project}  |  /inbox done {id}  |  /inbox dismiss {id}
```

### Triage mode (with args)

1. Parse action: assign, done, dismiss
2. Call `mcp__knowledge__triage_inbox` with id, action, and project (for assign)
3. Show confirmation:

```
✓ #12 assigned to routeiq
```
or
```
✓ #12 marked done
```
