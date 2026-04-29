# Agent Prompt Template (Native Subagent Dispatch)

Used by `/orchestrate` to construct Task() invocations for phase agents.

## Dispatch model — IMPORTANT CHANGE

Phase agents are now invoked via **native subagent dispatch**:

```python
Task(
    description='MAP for issue 184',
    subagent_type='orchestrate-map',   # registered agent name
    prompt=AGENT_PROMPT,                # context only, NOT instructions
)
```

When `subagent_type` matches a registered agent (one with valid `name:`
frontmatter, located at `~/.claude/agents/<file>.md`), Claude Code:

1. Loads the agent body as the spawned subagent's system prompt automatically
2. Applies the agent's `tools:` restriction
3. Applies the agent's `model:` setting (Haiku for MAP / PLAN-CHECK / DISCUSS;
   Sonnet for PLAN / PATCH / PROVE / etc.)
4. Spawns with a fresh context window

**Implication for the prompt template below**: do NOT instruct the agent to
"read your instructions from `agents/<file>.md`" — Claude Code already loads
that as the system prompt. Pass *only* per-invocation context.

## Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{AGENT_NAME}` | Display name (for the description field) | MAP-PLAN, PATCH, PROVE |
| `{SUBAGENT_TYPE}` | Registered agent name from frontmatter | orchestrate-map-plan, orchestrate-patch |
| `{ISSUE}` | Issue number | 184 |
| `{TITLE}` | Issue title | Add member role validation |
| `{BRANCH}` | Current branch | feature/issue-184-validation |
| `{STACK}` | Stack scope | backend, frontend, fullstack |
| `{COMPLEXITY}` | Issue complexity | TRIVIAL, SIMPLE, COMPLEX |
| `{ARTIFACT_NAME}` | Output artifact filename | map-plan-184-032526.md |
| `{ARTIFACT_LIST}` | Prior artifacts (markdown list of paths only) | - MAP-PLAN: .agents/outputs/... |
| `{PRIOR_FAILURE_BLOCK}` | Failure context or "First attempt" | ## Prior Failure ... |
| `{AGENT_INSTRUCTIONS}` | Per-invocation extra instructions (1-2 sentences) | Read MAP-PLAN. Generate test matrix. |
| `{SCOPE}` | Optional scope constraint | BACKEND ONLY, FRONTEND ONLY |

## Template (passed as `prompt:` to Task)

```markdown
## Inherited Context (read paths if needed; do NOT re-paste contents)
- Issue: #{ISSUE} — {TITLE}
- Branch: {BRANCH}
- Stack: {STACK}
- Complexity: {COMPLEXITY}

## Prior Artifacts
{ARTIFACT_LIST}

{PRIOR_FAILURE_BLOCK}

## Per-Run Instructions
{AGENT_INSTRUCTIONS}

Write your output artifact to `.agents/outputs/{ARTIFACT_NAME}`.
End your response with `AGENT_RETURN: {ARTIFACT_NAME}`.
```

## Context Isolation (MANDATORY)

Every agent spawned via this dispatch runs with a **fresh context window**.

1. **DO NOT** pass conversation history, prior tool results, or orchestrator reasoning to agents
2. **DO** pass only: filled template variables and references to prior artifact *paths* (not their contents)
3. **DO** let the agent read its own files via the Read tool
4. The prompt should consume <30% of the agent's context, leaving >70% for actual work

### What NEVER goes into the prompt
- Orchestrator's exploration results or reasoning
- Contents of files (the agent will Read them as needed)
- Conversation history between user and orchestrator
- Other agents' full artifact contents (pass paths, not contents)
- Repeating the agent's own instructions (Claude Code auto-loads them via `subagent_type`)

## Scoped Variant (parallel fullstack PATCH)

When `{SCOPE}` is set, add this line to "Inherited Context":

```markdown
- SCOPE: Implement ONLY {SCOPE} changes from MAP-PLAN
```

Use `subagent_type='orchestrate-patch'` for both backend and frontend halves;
the SCOPE line tells the agent which side to implement.

## PROVE-lite Variant (TRIVIAL issues — currently unused)

> **Note (issue #94)**: `/orchestrate` rejects TRIVIAL issues at Step 1.0.1
> and redirects to `/quick`. PROVE-lite is therefore dead code in the active
> pipeline; the variant is kept here only so the template stays consistent
> if TRIVIAL handling is ever reintroduced.

If reactivated, use the same `subagent_type='orchestrate-prove'` but a
minimal prompt — gates only, no Level 2-3 checks. As with full PROVE, the
agent does NOT write to `.claude/memory/`; the orchestrator records via
`state_manager` from the artifact's frontmatter (see
`commands/orchestrate.md` Step 4).

```markdown
## Inherited Context
- Issue: #{ISSUE} — {TITLE}
- Stack: {STACK}
- Complexity: TRIVIAL — RUN GATES ONLY

## Per-Run Instructions
Run verification gates only (skip Level 2 SUBSTANTIVE and Level 3 WIRED):
- If backend touched: `cd backend && ruff check . && pytest -q`
- If frontend touched: `cd frontend && npm run lint && npm run build`

Populate artifact frontmatter (status / complexity / stack) — orchestrator
records the outcome from there. Do NOT write to `.claude/memory/` yourself.
Write artifact to `.agents/outputs/{ARTIFACT_NAME}`.
End with `AGENT_RETURN: {ARTIFACT_NAME}`.
```

## Backwards-compatibility note

If a `subagent_type` lookup fails (e.g., the registered name has not been
picked up after a config change), Claude Code falls back to `general-purpose`.
In that case the orchestrator should re-prompt with an explicit "read your
instructions from `~/.claude/agents/<file>.md`" line so the legacy path still
works. After the next session restart the native dispatch should resolve.
