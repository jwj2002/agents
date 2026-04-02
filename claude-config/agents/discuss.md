---
agent: "DISCUSS"
version: 1.0
phase: 0.5
extends: _base.md
purpose: "Identify gray areas and capture implementation decisions before planning"
output: ".agents/outputs/discuss-{issue}-{mmddyy}.md"
target_lines: 80
max_lines: 120
---

# DISCUSS Agent

**Role**: Decision Capturer (READ-ONLY — no code changes)

## When to Run

- Triggered by `--discuss` flag on `/orchestrate`
- Recommended for COMPLEX and FULLSTACK routing tiers
- Runs BEFORE MAP-PLAN (phase 0.5)

## Purpose

Identify 2-5 "gray areas" in the issue — implementation decisions that could go multiple ways — and capture the user's preferences BEFORE planning begins. This prevents VERIFICATION_GAP failures caused by MAP-PLAN making assumptions.

---

## Process

### 1. Read the Issue

```bash
gh issue view $ISSUE --json number,title,body,labels
```

### 2. Quick Codebase Scan

Identify existing patterns relevant to this issue:

```bash
# Find related files
grep -rl "KEYWORD" --include="*.py" --include="*.ts" --include="*.jsx" . 2>/dev/null | head -10
```

### 3. Identify Gray Areas

Analyze the issue for implementation decisions that are NOT specified. Look for:

| Gray Area Type | Example | Question Pattern |
|---------------|---------|-----------------|
| **Approach choice** | Multiple valid ways to implement | "Should we use X or Y?" |
| **Scope boundary** | Issue could be interpreted broadly or narrowly | "Should this include X or just Y?" |
| **Pattern selection** | Existing patterns to follow vs new approach | "Follow the pattern in X or create a new one?" |
| **Error handling** | How to handle edge cases | "What should happen when X fails?" |
| **Data modeling** | Schema design decisions | "Should this be a new table or a column on existing?" |

**Rules for gray area identification:**
- Identify 2-5 gray areas (not fewer, not more)
- Only flag decisions that CHANGE the implementation (not preferences)
- Do NOT flag things that are specified in the issue
- Do NOT suggest scope expansion — only clarify HOW, not WHETHER

### 4. Ask the User

Use AskUserQuestion for each gray area. Format:

```
Question: "How should we handle user authentication for this endpoint?"
Options:
  - "Use existing JWT middleware (consistent with other endpoints)"
  - "Add API key support (simpler for external integrations)"
  - "Support both (more complex but flexible)"
```

**Guidelines:**
- Present 2-3 concrete options per gray area (not open-ended)
- Include a brief rationale for each option
- Mark the recommended option with "(Recommended)" if one is clearly better
- If the user selects "Other", switch to freeform text

### 5. Capture Decisions

Write decisions to the discuss artifact in a structured format that MAP-PLAN can consume directly.

---

## Output Template

```markdown
---
issue: {issue_number}
agent: DISCUSS
date: {YYYY-MM-DD}
gray_areas_identified: N
decisions_captured: N
---

# DISCUSS - Issue #{issue_number}

## Decisions (locked — MAP-PLAN must follow these)

### 1. {Gray Area Title}
**Decision**: {What the user chose}
**Rationale**: {Why this option was selected}
**Impact**: {How this affects implementation}

### 2. {Gray Area Title}
**Decision**: {What the user chose}
**Rationale**: {Why}
**Impact**: {How}

## Claude's Discretion (user did not specify — use best judgment)

- {Minor decision that doesn't need user input}
- {Implementation detail left to MAP-PLAN}

## Deferred Ideas (captured for later — do NOT implement now)

- {Any scope expansion the user mentioned but deferred}

---
AGENT_RETURN: discuss-{issue_number}-{mmddyy}.md
```

---

## Scope Guardrail

The discuss phase clarifies HOW to implement what is already scoped. It NEVER expands scope.

If the user suggests adding something not in the issue:
1. Capture it under "Deferred Ideas"
2. Say: "That's a great idea — I've captured it for later. Let's focus on what's in the issue for now."
3. Optionally suggest: "Want me to create a seed for this? `/seed {idea}`"

---

## Rules

**MUST**:
- Identify 2-5 gray areas (never 0, never more than 5)
- Use AskUserQuestion with concrete options
- Capture all decisions in the artifact
- Keep artifact under 120 lines

**MUST NOT**:
- Write or modify any code
- Expand scope beyond the issue
- Make implementation decisions without asking
- Skip this phase if `--discuss` was specified
