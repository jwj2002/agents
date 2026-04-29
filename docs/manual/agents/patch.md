# PATCH Agent

**Version**: 1.5 | **Phase**: 3 | **Role**: Implementer

PATCH is the only agent that modifies code. It reads the plan from MAP-PLAN, follows the project's architecture patterns, and implements the changes. Before writing any code, it runs a pre-flight checklist. After implementation, it runs verification gates (linting, tests). If anything fails, it fixes in-place before submitting.

## Pre-Flight Checklist

Before writing a single line of code, PATCH must complete these checks:

```
- [ ] Read PLAN or MAP-PLAN artifact
- [ ] Read CONTRACT artifact (MANDATORY if fullstack -- STOP if missing)
- [ ] Read .claude/rules.md for project constraints
- [ ] NOT on main branch (verified via git branch --show-current)
- [ ] No new top-level directories planned
- [ ] All changes are within scope of the PLAN
```

!!! warning "Branch Protection"
    If PATCH detects it is on the `main` branch, it stops immediately with `BLOCKED: Cannot run PATCH on main branch`. This is a hard stop with no override.

## Artifact Validation

PATCH verifies predecessor artifacts exist before starting:

```bash
# Must exist
ls .agents/outputs/{plan,map-plan}-${ISSUE}-*.md

# Must exist if fullstack
ls .agents/outputs/contract-${ISSUE}-*.md
```

If any required artifact is missing, PATCH reports `BLOCKED` and returns to the orchestrator.

## Pre-Implementation Requirements Extraction

Before writing code, PATCH extracts all requirements from the plan into a structured checklist:

```markdown
## Requirements Checklist

### From Spec/PLAN
- [ ] Field X maps to Model.field_x
- [ ] Validation rule: email must be unique
- [ ] Business logic: recalculate totals on update

### Data Model Analysis
- Models involved: Account, AccountMember
- Multi-model operation: YES
- Repository return type: ORM objects
```

This checklist ensures nothing is missed during implementation and provides a verification target for the completion check.

## Implementation Conventions

=== "Backend"

    - Access control logic belongs in dependency injection, never inline in route handlers
    - Routers stay thin -- business logic lives in services
    - Tests must be SQLite-compatible
    - Format only modified files: `ruff format path/to/modified.py`

=== "Frontend"

    - All API calls go through `frontend/src/api.js`
    - Reuse established component patterns from the codebase
    - Verify component APIs by reading source before using them

## Pre-Submission Gates

!!! note "Fix Before Submitting"
    If any gate fails, PATCH fixes the issue within the same session, re-runs the gate, and only proceeds when all gates pass. A failing artifact is never submitted.

### Backend Gates

```bash
cd backend && ruff check . --fix && ruff format <modified_files>
cd backend && pytest -q
```

### Frontend Gates

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

If a gate is unfixable within the current session, PATCH sets its artifact status to `Blocked`, documents the failure, and returns to the orchestrator.

??? info "Deviation policy (when implementation diverges from plan)"

    ## Deviation Policy

    When implementation diverges from the plan, PATCH categorizes the deviation and takes the appropriate action:

    | Level | Examples | Action |
    |-------|----------|--------|
    | **TRIVIAL** | Naming, formatting, import order | Proceed silently |
    | **MINOR** | Different utility function, extra helper, slightly different signature | Note in Deviations section |
    | **SIGNIFICANT** | Different approach, extra endpoint, schema change | **STOP**. Document and return to orchestrator |
    | **SCOPE** | New feature, unplanned migration, unplanned module | **ABORT**. Return immediately |

    !!! tip "When in Doubt, Escalate"
        If unsure whether a deviation is MINOR or SIGNIFICANT, always choose the higher level. It is better to pause and confirm than to proceed with an unauthorized change.

## Completion Checklist

Before marking the artifact as DONE:

**Code Quality**

- Every requirement from the checklist is implemented
- No TODO, FIXME, or HACK comments remain
- No stub implementations (`pass`, `return False`, `return []`)

**Spec Compliance**

- Implementation matches the spec exactly
- All fields are implemented
- All validations are implemented

**Multi-Model (if applicable)**

- All models updated in the same transaction
- Relationships loaded correctly for serialization

**Testing**

- New code has tests
- Success and error cases covered

??? example "PATCH artifact template"

    ## Output Template

    The PATCH artifact includes a YAML frontmatter block:

    ```yaml
    ---
    issue: 184
    agent: PATCH
    date: 2026-03-26
    status: Complete | Blocked | Gates-Failed
    files_modified: 3
    files_created: 1
    tests_added: 4
    ---
    ```

    The body documents:

    | Section | Content |
    |---------|---------|
    | Summary | What was implemented (3-5 sentences) |
    | Pre-Flight | Checklist of what was read and verified |
    | Requirements Checklist | Extracted from the plan |
    | Files Changed | Per-file list of additions and modifications |
    | Component API Verification | Table matching PLAN spec to actual props (if frontend) |
    | Enum Alignment | Table matching frontend strings to backend VALUES (if fullstack) |
    | Verification | Gate results with pass/fail and output |
    | Deviations | Any divergence from PLAN with level and justification |

    The artifact ends with `AGENT_RETURN: patch-{issue}-{mmddyy}.md`.

## Efficiency Rules

- Do not re-quote code from the plan. Reference by file and line: "Implemented as planned in PLAN lines 45-67"
- Keep the artifact under 350 lines (target: 250)
- Focus on what changed and any issues encountered
