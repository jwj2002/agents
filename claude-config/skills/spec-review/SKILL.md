---
name: spec-review
version: 3.0
description: Analyze specifications and generate GitHub issues
---

# Spec Review Skill (v3.0)

Analyze spec documents against codebase, identify gaps, create issues.

## When to Use

- New feature specification ready
- Need to break down large spec into issues
- Want to verify implementation completeness

## Process

1. **Parse spec** — Extract all requirements
2. **Analyze codebase** — Search for implementations
3. **Classify gaps** — Implemented/Partial/Missing/Differs
4. **Generate issues** — Create GitHub issues for gaps
5. **Recommend order** — Suggest implementation sequence

## Usage

```bash
# Full review with issue creation
/spec-review docs/features/invitation_system.md

# Preview without creating issues
/spec-review docs/features/invitation_system.md --dry-run

# Break into smaller issues
/spec-review docs/features/invitation_system.md --breakdown
```

## Output

- Artifact: `.agents/outputs/spec-review-{name}-{date}.md`
- GitHub issues with labels: `from-spec`, complexity, stack

## See Also

- `.claude/agents/spec-reviewer.md` — Agent definition
- `.claude/rules/spec-review-workflow.md` — Full workflow
