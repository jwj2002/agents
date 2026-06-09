# Orchestrate Pipeline Reference — Agent Spawn Details

Reference loaded by `/orchestrate` for Step 3 (Spawn Agents). Covers
per-agent dispatch via native `subagent_type`, per-invocation prompt
content, and validation gates.

---

## Dispatch Model — Native Subagent

Phase agents are registered Claude Code subagents (frontmatter `name:` of
each file in `~/.claude/agents/`). Invoke via:

```python
Task(
    description='<phase> for issue <N>',
    subagent_type='<registered-agent-name>',
    prompt=AGENT_PROMPT,    # see templates/agent-prompt.md
)
```

Claude Code auto-loads the agent body, applies its `tools:` restriction, and
honours its `model:` (Haiku for MAP / PLAN-CHECK / DISCUSS; Sonnet
otherwise). The prompt should contain context only — never repeat the
agent's own instructions.

For per-invocation prompt content, see `templates/agent-prompt.md`.

---

## Context Inheritance

All `prompt:` strings include the same inherited-context block. Per-agent
tables below specify just the variables that change.

```markdown
## Inherited Context (read paths if needed; do NOT re-paste contents)
- Issue: #{ISSUE} — {TITLE}
- Branch: {BRANCH}
- Stack: {STACK}
- Complexity: {COMPLEXITY}

## Prior Artifacts
{ARTIFACT_LIST}

## Project Memory (relevant facts — Read the body of any that bear on your work)
{PROJECT_MEMORY_BLOCK}

{PRIOR_FAILURE_BLOCK}

## Per-Run Instructions
{AGENT_INSTRUCTIONS}

Write your output artifact to `.agents/outputs/{ARTIFACT_NAME}`.
End your response with `AGENT_RETURN: {ARTIFACT_NAME}`.
```

> **Fresh Context Rule**: Each agent gets a clean context window. Pass file
> PATHS in the artifact list, not file CONTENTS. Let agents use the Read tool
> to load what they need.
>
> `{PROJECT_MEMORY_BLOCK}` is built **once** per workflow at `commands/orchestrate.md`
> Step 2.8 (`memory recall … --compact`) and reused for every phase — a compact
> index of paths + descriptions, so it honors the Fresh Context Rule (agents
> Read the bodies on demand). New phase agents inherit it automatically; no
> per-agent edit needed.

---

## Per-Agent Dispatch

### MAP-PLAN (TRIVIAL/SIMPLE only)

| Variable | Value |
|----------|-------|
| description | `MAP-PLAN for issue {ISSUE}` |
| subagent_type | `orchestrate-map-plan` |
| ARTIFACT_NAME | `map-plan-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | (none — first agent) |
| AGENT_INSTRUCTIONS | Investigate the codebase and produce a file-by-file plan. Include `## Issue Body` with the full issue body. |

**Validate after**: file exists, contains `AGENT_RETURN`.

### MAP (COMPLEX)

| Variable | Value |
|----------|-------|
| description | `MAP for issue {ISSUE}` |
| subagent_type | `orchestrate-map` |
| ARTIFACT_NAME | `map-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | (none — first agent) |
| AGENT_INSTRUCTIONS | Read-only investigation: identify affected files, components, enums, dependencies, and risks. |

### PLAN (COMPLEX)

| Variable | Value |
|----------|-------|
| description | `PLAN for issue {ISSUE}` |
| subagent_type | `orchestrate-plan` |
| ARTIFACT_NAME | `plan-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | `- MAP: .agents/outputs/map-{ISSUE}-{MMDDYY}.md` |
| AGENT_INSTRUCTIONS | Convert MAP findings into a file-by-file implementation plan with acceptance criteria. |

### TEST-PLANNER (--with-tests)

| Variable | Value |
|----------|-------|
| description | `TEST-PLANNER for issue {ISSUE}` |
| subagent_type | `orchestrate-test-planner` |
| ARTIFACT_NAME | `test-plan-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | `- MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md` *(or PLAN for COMPLEX)* |
| AGENT_INSTRUCTIONS | Generate a test matrix, edge cases, and test signatures from the plan. |

**Validate after**: file exists, contains test matrix, contains `AGENT_RETURN`.

### CONTRACT (MANDATORY if fullstack)

**GATE**: If `STACK=fullstack` and CONTRACT-full was selected (Step 1.6 in
`commands/orchestrate.md`), spawn this agent. PATCH refuses to proceed
without the contract artifact.

| Variable | Value |
|----------|-------|
| description | `CONTRACT for issue {ISSUE}` |
| subagent_type | `orchestrate-contract` |
| ARTIFACT_NAME | `contract-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | `- MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md` |
| AGENT_INSTRUCTIONS | Define the backend↔frontend API contract. Document enum VALUES (not Python names) explicitly. |

### PLAN-CHECK (skip if TRIVIAL)

- **TRIVIAL**: skip; proceed directly to PATCH
- **SIMPLE / COMPLEX**: run

| Variable | Value |
|----------|-------|
| description | `PLAN-CHECK for issue {ISSUE}` |
| subagent_type | `orchestrate-plan-check` |
| ARTIFACT_NAME | `plan-check-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | `- MAP-PLAN: ...` and `- CONTRACT: ...` (if fullstack) |
| AGENT_INSTRUCTIONS | Validate plan completeness. Do NOT modify any files. |

**On ISSUES_FOUND**: report to user before proceeding to PATCH; user decides whether to continue or revise.

### PATCH (single-stack or default)

| Variable | Value |
|----------|-------|
| description | `PATCH for issue {ISSUE}` |
| subagent_type | `orchestrate-patch` |
| ARTIFACT_NAME | `patch-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | `- MAP-PLAN, TEST-PLAN (if exists), CONTRACT (if fullstack), PLAN-CHECK` |
| PRIOR_FAILURE_BLOCK | Injected from `failures.jsonl` if a prior attempt was BLOCKED, else `## First attempt` |
| AGENT_INSTRUCTIONS | Implement changes per the plan. Implement tests following TEST-PLAN signatures (if exists). |

#### Failure context injection (before re-running PATCH)

```bash
PRIOR_FAILURE=$(grep "\"issue\":${ISSUE}" .claude/memory/failures.jsonl 2>/dev/null | tail -1)
```

If found, prepend to the prompt:

```markdown
## Prior Failure (CRITICAL — avoid repeating)
- Root cause: {root_cause from failure record}
- Details: {details}
- Prevention: {prevention}
- Failed files: {files}
```

### PATCH (parallel fullstack — when CONTRACT exists)

When `STACK=fullstack` and the CONTRACT artifact exists, split PATCH into
two parallel `Task()` calls in a single message. Both use
`subagent_type='orchestrate-patch'`; the SCOPE line in the prompt tells
each one which half to implement.

**PATCH-backend**:

| Variable | Value |
|----------|-------|
| description | `PATCH-backend for issue {ISSUE}` |
| subagent_type | `orchestrate-patch` |
| SCOPE | `BACKEND ONLY` |
| ARTIFACT_NAME | `patch-backend-{ISSUE}-{MMDDYY}.md` |
| AGENT_INSTRUCTIONS | Implement ONLY backend/ changes. Run gates: `cd backend && ruff check . && pytest -q`. |

**PATCH-frontend**:

| Variable | Value |
|----------|-------|
| description | `PATCH-frontend for issue {ISSUE}` |
| subagent_type | `orchestrate-patch` |
| SCOPE | `FRONTEND ONLY` |
| ARTIFACT_NAME | `patch-frontend-{ISSUE}-{MMDDYY}.md` |
| AGENT_INSTRUCTIONS | Implement ONLY frontend/ changes. Use CONTRACT for enum VALUES. Run gates: `cd frontend && npm run lint && npm run build`. |

After both complete, validate no file conflicts and merge into a single `patch-{ISSUE}-{MMDDYY}.md` summary for PROVE.

**Skip parallel PATCH** when:
- Shared utility files appear in both halves' plans (merge conflict risk)
- Issue involves <3 files per side (overhead exceeds benefit)
- No CONTRACT artifact exists (synchronization point missing)

### PROVE (full) — SIMPLE and COMPLEX

| Variable | Value |
|----------|-------|
| description | `PROVE for issue {ISSUE}` |
| subagent_type | `orchestrate-prove` |
| ARTIFACT_NAME | `prove-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | `- PATCH: ...` and `- MAP-PLAN: ...` |
| AGENT_INSTRUCTIONS | Run verification commands (ruff, pytest, npm lint, npm build). Populate frontmatter `status`, `complexity`, `stack`, `agents_run`, `root_cause` (if BLOCKED), `blocking_agent` (if BLOCKED). Do NOT write to `.claude/memory/` — the orchestrator records via `state_manager` after PROVE returns (see `commands/orchestrate.md` Step 4). |

**Post-condition**: PROVE artifact frontmatter contains the outcome fields.
Orchestrator's Step 4 reads them and calls `state_manager.record_metrics`
(and `record_failure` if BLOCKED) — that step is the authoritative writer.

### PROVE-lite — TRIVIAL only

Same `subagent_type='orchestrate-prove'`. Use the **PROVE-lite variant**
prompt from `templates/agent-prompt.md` — gates only, no Level 2-3 checks.

### DISCUSS (--discuss)

| Variable | Value |
|----------|-------|
| description | `DISCUSS for issue {ISSUE}` |
| subagent_type | `orchestrate-discuss` |
| ARTIFACT_NAME | `discuss-{ISSUE}-{MMDDYY}.md` |
| ARTIFACT_LIST | (none) |
| AGENT_INSTRUCTIONS | Identify gray areas in the issue and capture implementation decisions before planning. |

---

## Backwards Compatibility

If `subagent_type='orchestrate-<phase>'` lookup fails (config not yet
reloaded after a change), Claude Code falls back to `general-purpose`. In
that case the orchestrator should append to the prompt:

```markdown
## Fallback Instructions (subagent registration not picked up)
Read your role instructions from `~/.claude/agents/<phase>.md` before proceeding.
```

After the next session restart the native dispatch will resolve.
