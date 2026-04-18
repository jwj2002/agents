---
name: review-session
version: 1.0
description: Review session commits and propose focus updates per project
---

# /review-session

Reads pending session activity recorded by the session-end hook. For each project
with new commits, Claude drafts a proposed focus update based on the commits and
presents it for approval.

## Usage

```
/review-session
```

## Behavior

### Step 1: Load pending reviews

Read `~/.claude/pending_focus_reviews.json`. Format:

```json
{
  "flotilla": {
    "commits": [
      { "sha": "abc123", "message": "feat: Phase 4 automation" },
      { "sha": "def456", "message": "fix: YAML back-write" }
    ],
    "current_focus": "Phase 2 integration complete",
    "session_end": "2026-04-18T..."
  }
}
```

If the file doesn't exist or is empty, say:
```
No pending session reviews. You're all caught up.
```

### Step 2: Per project, draft a proposed focus

For each project in the pending file:

1. Read the list of commits (look at messages as a group)
2. Read the current focus
3. **Claude's job**: synthesize a new focus statement (≤80 chars) that reflects
   what just got accomplished. Focus on the outcome, not the mechanism.
   - Good: "Phase 4 automation deployed — monitoring for drift"
   - Bad: "Merged PRs #71, #72 and fixed YAML back-write"

### Step 3: Present for each project

```
📝 flotilla — 8 commits this session

  Current: Phase 2 integration complete
  Proposed: Phase 4 automation deployed — monitoring for drift

  Based on commits:
    - feat: Phase 4 automation — auto-blockers, auto-status, auto-journal
    - fix: update_project_context writes YAML back
    - feat: /dashboard lists issues, captures, blockers
    (+5 more)

  Actions: [y] apply  [n] skip  [e] edit focus text
```

Wait for user choice per project:
- **y** / yes / apply: call `mcp__knowledge__update_project_context` with the proposed focus
- **n** / skip: leave focus unchanged (entry gets cleared anyway)
- **e** / edit: ask "Enter new focus text:" then apply user's text

Also ask if next_steps should be updated based on open items:
- After focus is resolved, propose: "Want to update next steps too? (y/n)"
- If yes, Claude reads open captures + current next_steps and proposes new ordering

### Step 4: Clear processed entries

After processing each project, remove it from `~/.claude/pending_focus_reviews.json`.
When the file is empty (all projects resolved), delete the file.

## Tone

- Be brief. One proposal at a time, clear actions.
- Don't over-explain the commits.
- Respect skip — if user says no, move on immediately.
- No follow-up questions unless the user typed `e` (edit).

## Integration with /dashboard

The `/dashboard` skill should show a one-line notice at the top when
pending_focus_reviews.json exists:

```
📝 2 projects have session activity to review — run /review-session
```

This creates a gentle nudge without forcing the review.
