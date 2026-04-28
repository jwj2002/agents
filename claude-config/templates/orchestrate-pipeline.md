# Orchestrate Pipeline Reference — Agent Spawn Details

Reference loaded by `/orchestrate` for Step 3 (Spawn Agents). Covers
prompt templates per agent, context inheritance, and validation gates.

---

## Context Inheritance Template

All agent prompts MUST include this inherited context block to reduce re-reading:

```markdown
## Inherited Context (DO NOT re-read these files)
- Issue: #{issue_number} - {title}
- Branch: {current_branch}
- Spec: {spec_path if any} ({version})
- Stack: {backend|frontend|fullstack}
- Complexity: {TRIVIAL|SIMPLE|COMPLEX}

## Critical Patterns (Always Apply)
Loaded from rules/core-patterns.md (auto-loaded by Claude Code).
Apply VERIFICATION_GAP, ENUM_VALUE, and COMPONENT_API checks as relevant.

## Prior Artifacts
- {list any prior artifacts for this issue}
```

> **Fresh Context Rule**: Each agent gets a clean context window. Pass file
> PATHS in the artifact list, not file CONTENTS. Let agents use the Read tool
> to load what they need. This ensures consistent quality regardless of how
> long the orchestrate session has been running.

---

## Per-Agent Prompt Templates

All templates use `templates/agent-prompt.md` as the base and substitute the variables below.

### MAP-PLAN (or MAP + PLAN)

| Variable | Value |
|----------|-------|
| AGENT_NAME | MAP-PLAN |
| AGENT_FILE | map-plan.md |
| ARTIFACT_NAME | map-plan-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | (none — first agent) |
| AGENT_INSTRUCTIONS | Investigate and plan. Include `## Issue Body` with full issue body. |

**Validate**: File exists, has AGENT_RETURN directive.

### TEST-PLANNER (if --with-tests)

| Variable | Value |
|----------|-------|
| AGENT_NAME | TEST-PLANNER |
| AGENT_FILE | test-planner.md |
| ARTIFACT_NAME | test-plan-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md |
| AGENT_INSTRUCTIONS | Read MAP-PLAN artifact. Generate test matrix, edge cases, and test signatures. |

**Validate**: File exists, has test matrix, has AGENT_RETURN directive.

### CONTRACT (MANDATORY if fullstack)

**GATE**: If stack is fullstack and CONTRACT-full selected, spawn CONTRACT agent. PATCH will refuse to proceed without the contract artifact.

| Variable | Value |
|----------|-------|
| AGENT_NAME | CONTRACT |
| AGENT_FILE | contract.md |
| ARTIFACT_NAME | contract-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md |
| AGENT_INSTRUCTIONS | Define backend/frontend API contract. Document enum VALUES explicitly. |

### PLAN-CHECK (skip if TRIVIAL)

- **TRIVIAL**: Skip PLAN-CHECK entirely. Proceed directly to PATCH.
- **SIMPLE or COMPLEX**: Run PLAN-CHECK.

| Variable | Value |
|----------|-------|
| AGENT_NAME | PLAN-CHECK |
| AGENT_FILE | plan-checker.md |
| ARTIFACT_NAME | plan-check-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md<br>- CONTRACT: (if fullstack) |
| AGENT_INSTRUCTIONS | Validate plan completeness. Do NOT modify any files. |

**Validate**: File exists, has AGENT_RETURN directive.
**If ISSUES_FOUND**: Report to user before proceeding to PATCH. User decides whether to continue or revise plan.

### Failure Context Injection (Before Re-running PATCH)

If this issue has been attempted before (prior PROVE was BLOCKED), inject failure context into PATCH prompt:

```bash
PRIOR_FAILURE=$(grep "\"issue\":${ISSUE}" .claude/memory/failures.jsonl 2>/dev/null | tail -1)
```

If found, add to PATCH prompt's Inherited Context:

```markdown
## Prior Failure (CRITICAL — avoid repeating)
- Root cause: {root_cause from failure record}
- Details: {details}
- Prevention: {prevention}
- Failed files: {files}
```

### PATCH (Single-Stack or Default)

| Variable | Value |
|----------|-------|
| AGENT_NAME | PATCH |
| AGENT_FILE | patch.md |
| ARTIFACT_NAME | patch-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN, TEST-PLAN (if exists), CONTRACT (if fullstack), PLAN-CHECK |
| PRIOR_FAILURE_BLOCK | Injected from failures.jsonl or "First attempt" |
| AGENT_INSTRUCTIONS | Implement changes per MAP-PLAN. Implement tests following TEST-PLAN signatures (if exists). |

### PATCH (Parallel Fullstack — when CONTRACT exists)

When STACK=fullstack and CONTRACT artifact exists, split PATCH into two parallel tasks using the scoped variant from `templates/agent-prompt.md`.

Spawn in parallel (single message, two Task calls):

**PATCH-backend**:

| Variable | Value |
|----------|-------|
| AGENT_NAME | PATCH (BACKEND ONLY) |
| SCOPE | backend/ |
| ARTIFACT_NAME | patch-backend-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN, CONTRACT (AUTHORITATIVE), TEST-PLAN (if exists) |
| AGENT_INSTRUCTIONS | Implement ONLY backend/ changes. Run gates: ruff check . && pytest -q |

**PATCH-frontend**:

| Variable | Value |
|----------|-------|
| AGENT_NAME | PATCH (FRONTEND ONLY) |
| SCOPE | frontend/ |
| ARTIFACT_NAME | patch-frontend-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - MAP-PLAN, CONTRACT (AUTHORITATIVE), TEST-PLAN (if exists) |
| AGENT_INSTRUCTIONS | Implement ONLY frontend/ changes. Use CONTRACT for enum VALUES. Run gates: npm run lint && npm run build |

**After both complete**: Validate no file conflicts between the two artifacts.
Merge into single `patch-{ISSUE}-{MMDDYY}.md` summary artifact for PROVE.

**Skip parallel PATCH** when:
- Shared utility files appear in both backend and frontend plans (merge conflict risk)
- Issue involves fewer than 3 files per side (overhead exceeds benefit)
- No CONTRACT artifact exists (synchronization point missing)

### PROVE (full) — SIMPLE and COMPLEX

| Variable | Value |
|----------|-------|
| AGENT_NAME | PROVE |
| AGENT_FILE | prove.md |
| ARTIFACT_NAME | prove-{ISSUE}-{MMDDYY}.md |
| ARTIFACT_LIST | - PATCH: .agents/outputs/patch-{ISSUE}-{MMDDYY}.md<br>- MAP-PLAN: .agents/outputs/map-plan-{ISSUE}-{MMDDYY}.md |
| AGENT_INSTRUCTIONS | Run verification commands (ruff, pytest, npm lint, npm build). Record outcome to metrics.jsonl. If BLOCKED, record to failures.jsonl. |

### PROVE-lite — TRIVIAL only

Use the PROVE-lite variant from `templates/agent-prompt.md`. Gates only, no Level 2-3 checks.
