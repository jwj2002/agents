# MAP-PLAN Agent

**Version**: 1.0 | **Phase**: 1+2 | **Role**: Investigator + Architect

MAP-PLAN is the first agent to run on most issues. It reads the issue, investigates your codebase, and produces a detailed implementation plan. The plan includes which files to modify, what patterns to follow, and acceptance criteria for verification. It does not write any code -- that's PATCH's job.

!!! info "Routing context"
    MAP-PLAN runs when `/orchestrate` classifies the work as the SIMPLE pipeline tier. TRIVIAL classifications are rejected by `/orchestrate` and redirected to `/quick` (no pipeline). COMPLEX classifications use separate MAP and PLAN agents instead. Tasks routed to `/quick` or Plan Mode never reach MAP-PLAN.

## When to Use

| Pipeline Tier | Use MAP-PLAN? | Alternative |
|---------------|---------------|-------------|
| TRIVIAL | No | `/orchestrate` rejects TRIVIAL; use `/quick` |
| SIMPLE | Yes | -- |
| COMPLEX | No | Use separate MAP + PLAN agents |

If during investigation the issue turns out to be COMPLEX (new endpoints, migrations, cross-module changes), MAP-PLAN stops and reports to the orchestrator for reclassification.

## Mandatory Verification Protocol

!!! warning "This protocol prevents 63% of MAP-PLAN failures"
    The most common agent failure is proceeding on assumptions without reading actual code. This checklist forces verification at every step.

### 1. Specification Check

If the issue references a spec:

- Read the specification file first (before any code exploration)
- Note spec version and status (DRAFT / FINAL / DEPRECATED)
- Extract all requirements, not just the obvious ones
- Check for related specs or ADRs in the `specs/` directory

### 2. Assumption Verification

- List all assumptions about code structure
- Verify each assumption by reading actual code
- Document what was verified and the result
- Never assume structure -- always confirm by reading

### 3. Ambiguity Resolution

- If multiple valid approaches exist, pick one
- Document rationale for the chosen approach
- If truly unclear, ask the user
- Never leave decisions for PATCH to resolve

### 4. Impact Analysis

For changes to calculations or formulas:

- Identify all places where the result is used
- Check if the result feeds into dependent engines
- Document cache invalidation needs
- List dependent calculations that may be affected

### 5. Completeness Check

- List all models and components touched
- Check for related models via relationships
- Verify consistency requirements across all affected areas
- Document implicit requirements explicitly

Every MAP-PLAN output must include a **Verification Steps** section documenting: what spec was read, what code was verified, which approach was chosen and why, what dependencies were checked, and all models/components identified.

???+ info "Detailed process steps"

    ## Process Steps

    ### 1. Classify Pipeline Tier

    | Pipeline Tier | Criteria | Handling |
    |---------------|----------|----------|
    | TRIVIAL | Docs, config, renames, deletions | Rejected by `/orchestrate`; redirected to `/quick` |
    | SIMPLE | 1-3 files, localized change | Run MAP-PLAN |
    | COMPLEX | New endpoints, migrations, cross-module | Escalate to separate MAP + PLAN agents |

    ### 2. Identify Stack

    Determine `backend`, `frontend`, or `fullstack`. If fullstack, a CONTRACT agent is required before PATCH.

    ### 3. Find Affected Files

    Locate all files relevant to the change using search tools. Document each file and its role in the change.

    ### 4. Document Component APIs

    !!! tip "COMPONENT_API accounts for 17% of failures"
        When reusing frontend components, always extract and document the actual PropTypes or TypeScript interface from the source file.

    ```markdown
    #### ComponentName
    **Props**: propA (string, required), propB (func, optional)
    **Example**: `<Component propA="x" />`
    ```

    ### 5. Document Enum Values

    For fullstack issues, always document the enum VALUE (right side of `=`), not the Python name.

    !!! tip "See also"
        For the full ENUM_VALUE pattern explanation with code examples, see [Core Patterns -- ENUM_VALUE](../rules/core-patterns.md#enum_value-in-detail).

    ### 6. Data Model Analysis

    For CRUD operations, map every field to its owning model. List all models involved and note whether multi-model orchestration is needed.

    ### 7. Find Pattern to Mirror

    Search for similar existing implementations in the codebase. Reference them by file path and line range rather than quoting code.

    ### 8. Create File-by-File Plan

    For each file that needs changes:

    ```markdown
    #### File: `path/to/file.py`
    **Changes**: Add new validation method
    **Pattern**: See `similar/file.py:45-67`
    ```

    ### 9. Define Acceptance Criteria

    Write a single checklist of criteria. PATCH and PROVE reference this list -- it is never duplicated across artifacts.

    ```markdown
    - [ ] Criterion 1
    - [ ] Criterion 2
    - [ ] Criterion 3
    ```

??? example "MAP-PLAN artifact template"

    ## Output Template

    The artifact starts with YAML frontmatter:

    ```yaml
    ---
    issue: 184
    agent: MAP-PLAN
    date: 2026-03-26
    complexity: SIMPLE
    stack: backend
    files_identified: 3
    ---
    ```

    The body includes these sections:

    | Section | Content |
    |---------|---------|
    | Summary | 3-5 sentences: what, why, risks |
    | Verification Steps | Spec read, code verified, approach decided, impact analyzed, completeness confirmed |
    | Investigation | Affected files, component APIs, enum values, data model analysis, risks |
    | Plan | File-by-file steps, acceptance criteria, verification gates |

    The artifact ends with `AGENT_RETURN: map-plan-{issue}-{mmddyy}.md`.

## Pre-Submission Checklist

Before submitting the artifact:

- Read the spec first (if referenced in the issue)
- Verified assumptions by reading actual code
- Documented enum VALUES (not names) if fullstack
- Documented component APIs if reusing existing components
- Picked one approach if multiple are valid
- Included the Verification Steps section
- Complexity classified correctly
- Did not edit any code (MAP-PLAN is read-only)
- Artifact is under 450 lines (target: 350)
