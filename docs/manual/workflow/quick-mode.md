# Quick Mode

The `/quick` command handles small, well-scoped tasks without the overhead of the full orchestrate pipeline. No sub-agents, no artifacts, no GitHub issue required.

## Usage

```bash
/quick Fix typo in README
/quick Add missing import in accounts/services.py
/quick Update env example with new variable
```

The argument is a plain-text description of the task.

## When to Use /quick vs /orchestrate

| Criteria | `/quick` | `/orchestrate` |
|----------|----------|----------------|
| Scope | 1-2 files, obvious fix | Multi-file, needs planning |
| Tracking | No GitHub issue needed | Requires GitHub issue |
| Branching | Stays on current branch | Creates feature branch |
| Artifacts | None generated | Full MAP - PATCH - PROVE chain |
| Sub-agents | None spawned | Specialized agents per phase |
| Patterns | Critical patterns only | Full patterns for COMPLEX |
| Time | Seconds to minutes | Minutes to longer |

!!! tip "Rule of thumb"
    If you hesitate about whether it fits `/quick`, use `/orchestrate` instead. Quick mode is for changes you could describe in one sentence and verify in one command.

## Decision Criteria

Use `/quick` when ALL of these are true:

- The change touches 3 files or fewer
- The fix is obvious (no investigation needed)
- No schema changes or migrations
- No cross-cutting concerns (pure backend OR pure frontend)
- You can verify the change with a single command

Use `/orchestrate` when ANY of these are true:

- You need to investigate the codebase first
- The change spans multiple subsystems
- There are enum values, API contracts, or shared types involved
- You want tracked artifacts for the implementation
- The change requires a dedicated feature branch and PR

## Process

### 1. Load Critical Patterns

Before executing, `/quick` loads the critical failure patterns:

```bash
cat .claude/memory/patterns-critical.md
```

The three core checks are applied:

| Pattern | Check |
|---------|-------|
| VERIFICATION_GAP | Verify assumptions by reading actual code |
| ENUM_VALUE | Use enum VALUE string, not Python name |
| COMPONENT_API | Read component source before using props |

### 2. Classify Scope

Determine which area is affected:

- **Backend**: `backend/` directory
- **Frontend**: `frontend/src/` directory
- **Config**: `.claude/`, root files, documentation

### 3. Execute Directly

Make changes directly -- no sub-agents are spawned. All project rules from `.claude/rules/` still apply.

### 4. Verify

Run the appropriate verification commands for the area touched:

```bash
# Backend changes
cd backend && ruff check . && pytest -q

# Frontend changes
cd frontend && npm run lint && npm run build
```

### 5. Report

```
Quick task complete:
- Files changed: backend/accounts/services.py
- Verification: PASS
- Summary: Added missing import for AccountSchema
```

## Optional Metrics Recording

Quick tasks can optionally record to `metrics.jsonl` for tracking:

```bash
echo '{"date":"2026-03-26","source":"quick","task":"Fix missing import","status":"PASS","files_changed":1}' >> .claude/memory/metrics.jsonl
```

This is not required but helps when running `/metrics` for a complete picture of development activity.

## What /quick Does NOT Do

| Behavior | Why |
|----------|-----|
| Create feature branches | Stays on current branch to minimize overhead |
| Create GitHub issues | The task is too small to warrant formal tracking |
| Spawn sub-agents | Direct execution is faster for small changes |
| Write artifacts | No MAP-PLAN, PATCH, or PROVE files generated |
| Run full PROVE | Only runs lint and test gates, not the full verification matrix |

## Examples

Good candidates for `/quick`:

```bash
/quick Fix typo in CLAUDE.md header
/quick Add CORS origin for staging environment
/quick Update Python version in pyproject.toml
/quick Remove unused import in router.py
/quick Add missing field to env.example
```

Bad candidates (use `/orchestrate` instead):

```bash
# Too broad -- needs investigation
/quick Refactor the auth module

# Cross-cutting -- touches backend and frontend
/quick Add role field to user profile

# Needs planning -- schema change
/quick Add payment_status column to orders table
```

!!! warning "3-file limit"
    If `/quick` would need to touch more than 3 files, it recommends switching to `/orchestrate` instead. This is a hard boundary to prevent scope creep in untracked work.
