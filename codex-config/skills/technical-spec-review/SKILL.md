---
name: technical-spec-review
description: Interactively review technical specs for build readiness. Use when a spec needs complete gap analysis and concrete recommendations. Ask clarifying questions one at a time, wait for user response each time, provide options with a recommended senior-default, always include a discuss-further option, then provide a final shareable output for Claude with all identified gaps prioritized by criticality.
---

# Workflow

1. Read the spec first
- Start from the provided spec only.
- Do not require team size, timeline, or other metadata upfront.

2. Run interactive clarification
- Ask clarifying questions one at a time.
- After each question, wait for user response before asking the next.
- Ask as many questions as needed to remove ambiguity.
- For each question, provide concise options and mark one as the recommended senior-default.
- Always include an explicit option to discuss further.

3. Analyze build readiness
- Identify all gaps: ambiguity, hidden assumptions, missing acceptance criteria, undefined dependencies, operational/security/test gaps, rollout/rollback gaps, and ownership gaps.
- Prioritize every identified gap by criticality using priority labels.

4. Produce final shareable output
- Return only two sections in final output:
  - Critical gaps (complete list, prioritized by criticality labels)
  - Recommendations (concrete spec changes mapped to the gaps)
- Write recommendations so the user can hand them directly to Claude.

# Output Contract

Final output must contain only:
- Critical gaps
  - Every gap must include a priority label: P0, P1, P2, P3...
  - Order gaps from highest to lowest priority
- Recommendations

Do not include extra sections in the final output.

# Clarifying Question Format

For each clarifying question, use this structure:
- Question
- Options:
  - A) ...
  - B) ...
  - C) ...
  - D) Discuss further
- Recommended: <option> (senior-default)

# Quality Bar

A spec is build-ready only if it is:
- Unambiguous
- Testable
- Feasible
- Operable
- Correctly scoped
