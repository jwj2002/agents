# Agent Prompt Template

Used by orchestrate.md to construct Task() prompts. The orchestrator reads this template and substitutes variables before passing to the Task tool.

## Context Isolation (MANDATORY)

Every agent spawned via this template runs with a **fresh context window**. To maintain consistent quality from task 1 to task 50:

1. **DO NOT** pass conversation history, prior tool results, or orchestrator reasoning to agents
2. **DO** pass only: this template (filled), the referenced artifact files, and rules/patterns
3. **DO** let the agent read its own files via Read tool rather than pasting file contents into the prompt
4. The agent's prompt should consume <30% of context, leaving >70% for the agent's own work

### What Goes Into an Agent Prompt
- Filled template variables (issue, branch, stack, complexity, artifact list)
- Prior failure block (if re-attempt)
- Agent-specific instructions (1-2 sentences)

### What NEVER Goes Into an Agent Prompt
- Orchestrator's exploration results or reasoning
- Contents of files (let the agent Read them)
- Conversation history between user and orchestrator
- Other agents' full artifact contents (pass file paths, not contents)

## Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{AGENT_NAME}` | Agent role name | MAP-PLAN, PATCH, PROVE |
| `{ISSUE}` | Issue number | 184 |
| `{TITLE}` | Issue title | Add member role validation |
| `{BRANCH}` | Current branch | feature/issue-184-validation |
| `{STACK}` | Stack scope | backend, frontend, fullstack |
| `{COMPLEXITY}` | Issue complexity | TRIVIAL, SIMPLE, COMPLEX |
| `{AGENT_FILE}` | Agent instruction filename | map-plan.md, patch.md |
| `{ARTIFACT_NAME}` | Output artifact filename | map-plan-184-032526.md |
| `{ARTIFACT_LIST}` | Prior artifacts (markdown list) | - MAP-PLAN: .agents/outputs/... |
| `{PRIOR_FAILURE_BLOCK}` | Failure context or "First attempt" | ## Prior Failure ... |
| `{AGENT_INSTRUCTIONS}` | Agent-specific extra instructions | Implement changes per MAP-PLAN. |
| `{SCOPE}` | Optional scope constraint | BACKEND ONLY, FRONTEND ONLY |

## Template

```markdown
You are {AGENT_NAME} agent.

## Inherited Context (DO NOT re-read these files)
- Issue: #{ISSUE} - {TITLE}
- Branch: {BRANCH}
- Stack: {STACK}
- Complexity: {COMPLEXITY}

## Critical Patterns
Loaded from rules/core-patterns.md (auto-loaded by Claude Code).
Apply VERIFICATION_GAP, ENUM_VALUE, and COMPONENT_API checks as relevant.

## Prior Artifacts
{ARTIFACT_LIST}

{PRIOR_FAILURE_BLOCK}

## Instructions
Read agent instructions (check .claude/agents/{AGENT_FILE} first, else ~/.claude/agents/{AGENT_FILE}).
{AGENT_INSTRUCTIONS}
Write to .agents/outputs/{ARTIFACT_NAME}
End with AGENT_RETURN: {ARTIFACT_NAME}
```

## Scoped Variant (for parallel fullstack PATCH)

When `{SCOPE}` is set, add to Inherited Context:
```markdown
- SCOPE: Only implement {SCOPE} changes from MAP-PLAN
```

## PROVE-lite Variant (for TRIVIAL issues)

Uses a minimal prompt — gates only, no Level 2-3 checks:
```markdown
You are PROVE agent (lite mode for TRIVIAL issues).

## Inherited Context
- Issue: #{ISSUE} - {TITLE}
- Stack: {STACK}
- Complexity: TRIVIAL

## Instructions
Run verification gates ONLY (skip Level 2 SUBSTANTIVE and Level 3 WIRED checks):
- If backend touched: cd backend && ruff check . && pytest -q
- If frontend touched: cd frontend && npm run lint && npm run build

Record outcome to .claude/memory/metrics.jsonl
Write to .agents/outputs/{ARTIFACT_NAME}
End with AGENT_RETURN: {ARTIFACT_NAME}
```
