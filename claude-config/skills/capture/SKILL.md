---
name: capture
version: 1.0
description: Quick non-interrupting capture to inbox
---

# /capture

Quick-add to inbox. Non-interrupting — like /btw. Fire and forget.

## Usage

```
/capture add dark/light theme toggle to flotilla dashboard
/capture check concurrent migration handling @routeiq #task
/capture ask Paul about staging deploy schedule #question
/capture shared component library idea #idea
```

## Tags

- `@project` — assigns to a project (optional)
- `#type` — task, question, idea, concern (default: task)

## Behavior

1. Parse the text, extracting `@project` and `#type` tags
2. Call `mcp__knowledge__capture` with content, project (if tagged), type (if tagged)
3. Return ONE LINE acknowledgment:

```
✓ Captured #47: "add dark/light theme toggle..." (idea → flotilla)
```

4. **Do NOT ask follow-up questions.** Do NOT elaborate. Continue the current task immediately.

## Important

This skill is NON-INTERRUPTING. The entire response must be a single acknowledgment line. No confirmation prompts, no suggestions, no "would you like to..." — just capture and move on.
