# CONTRACT Agent

**Version**: 1.0 | **Phase**: 2.5 | **Role**: Interface Designer

CONTRACT defines the API boundary between backend and frontend for fullstack work. It specifies endpoints, authentication, authorization, enum values, and frontend integration notes. CONTRACT is a spec-only agent -- it reads code and writes documentation, never modifying any source files.

## When CONTRACT Runs

CONTRACT is positioned between planning and implementation:

```
PLAN or MAP-PLAN  -->  CONTRACT  -->  PLAN-CHECK  -->  PATCH
```

| Condition | CONTRACT Required? |
|-----------|--------------------|
| Backend-only change | No |
| Frontend-only change | No |
| Fullstack change | **Yes** |

!!! warning "PATCH Enforcement"
    PATCH checks for a `contract-{issue}-*.md` artifact before starting any fullstack work. If the artifact is missing, PATCH stops immediately with `BLOCKED: CONTRACT artifact required for fullstack`.

## The ENUM_VALUE Problem

Before CONTRACT was mandatory, `ENUM_VALUE` accounted for 26% of all fullstack failures. The core issue: frontend code uses the Python enum NAME (with underscores) when it should use the enum VALUE (with hyphens). CONTRACT forces explicit documentation of enum VALUES in a dedicated section, eliminating ambiguity about which string the frontend should send.

!!! tip "See also"
    For the full ENUM_VALUE pattern explanation with code examples, see [Core Patterns -- ENUM_VALUE](../rules/core-patterns.md#enum_value-in-detail).

## What CONTRACT Defines

### 1. Scope

Explicitly state which endpoints are in scope and which are out of scope.

### 2. Authentication

- Token type (Bearer JWT)
- Which endpoints require authentication

### 3. Authorization

- Scoping model (e.g., `account_id` path prefix)
- Access control dependencies (e.g., `require_account_access`)

### 4. Endpoint Definitions

For each endpoint, CONTRACT documents:

```markdown
### POST /accounts/{account_id}/members

**Auth**: Required
**Access**: require_account_owner

**Request**:
  { "email": "string (required)", "role": "OWNER | CO-OWNER | DEPENDENT" }

**Response** (201):
  { "id": 1, "email": "user@example.com", "role": "CO-OWNER" }

**Errors**: 401, 403, 404, 422
```

### 5. Enum Definitions

!!! note "Critical Section"
    This section is the primary reason CONTRACT exists. Both PATCH (backend and frontend) and PROVE use this section to verify enum alignment.

For each enum:

| Python Name | Python VALUE | Valid API Values |
|-------------|-------------|-----------------|
| `OWNER` | `"OWNER"` | `"OWNER"` |
| `CO_OWNER` | `"CO-OWNER"` | `"CO-OWNER"` |
| `DEPENDENT` | `"DEPENDENT"` | `"DEPENDENT"` |

### 6. Frontend Integration Notes

- API call pattern (via `api.js`)
- Account prefixing behavior
- State management approach (React Query hooks, Zustand, etc.)

## CONTRACT-lite

Not every fullstack change needs a full CONTRACT agent. Small changes can use an inline contract within the MAP-PLAN artifact instead.

### Decision Matrix

| Condition | Result |
|-----------|--------|
| 0 new endpoints AND 2 or fewer frontend files | CONTRACT-lite (inline in MAP-PLAN) |
| Any new endpoints OR 3+ frontend files | CONTRACT-full (dedicated agent) |

CONTRACT-lite includes the same enum value documentation and API surface description, but is embedded as a section within the MAP-PLAN artifact rather than a separate file.

## Output Template

The artifact starts with YAML frontmatter:

```yaml
---
issue: 184
agent: CONTRACT
date: 2026-03-26
scope: fullstack
endpoints_modified: 2
breaking_changes: NO
---
```

The body includes:

| Section | Content |
|---------|---------|
| Summary | What API changes, backward compatibility |
| Scope | In scope and out of scope endpoints |
| Authentication | Token type and requirements |
| Authorization | Scoping model and access control deps |
| Endpoints | Full definition per endpoint |
| Enum Definitions | NAME vs VALUE table for each enum |
| Frontend Integration | API call patterns, state management |
| Verification | Backend and frontend gate commands |

The artifact ends with `AGENT_RETURN: contract-{issue}-{mmddyy}.md`.

!!! example "CONTRACT artifact excerpt"
    ```markdown
    ---
    issue: 184
    agent: CONTRACT
    date: 2026-03-26
    scope: fullstack
    endpoints_modified: 1
    breaking_changes: NO
    ---
    ## Enum Definitions
    | Python Name | Python VALUE | Valid API Values |
    |-------------|-------------|-----------------|
    | CO_OWNER    | "CO-OWNER"  | "CO-OWNER"      |

    ## POST /accounts/{account_id}/members
    **Auth**: Required | **Access**: require_account_owner
    **Request**: { "email": "string", "role": "OWNER | CO-OWNER | DEPENDENT" }
    **Response** (201): { "id": 1, "email": "user@example.com", "role": "CO-OWNER" }

    AGENT_RETURN: contract-184-032626.md
    ```

## Efficiency Rules

- Use examples over prose -- a request/response pair communicates more than a paragraph
- Target 180 lines, max 250
- Focus on the API surface, not the implementation details behind it
