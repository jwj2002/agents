# Failure Patterns

Three failure patterns account for over 50% of all agent failures. Each was discovered through structured failure data, not intuition, and each has systematic prevention encoded directly into agent definitions.

## The Top 3 Patterns

### VERIFICATION_GAP (63% of all failures)

**What happens**: The agent proceeds with implementation based on assumptions about code structure, spec requirements, or component APIs without actually reading the source.

**Why agents make this mistake**: AI models have strong priors from training data. They "know" what a typical FastAPI endpoint looks like, what a typical React hook returns, what a typical schema includes. These priors are usually correct, but when they are wrong, the agent produces plausible-looking code that does not match your actual codebase.

**Real example**: MAP-PLAN deferred a spec requirement ("add `after_tax_contributions` to cashflow summary") because a previous issue (#155) had a similar deferral. But the spec had been updated since #155. The agent assumed the old pattern still applied without reading the current spec.

**Systematic prevention**:

1. **Mandatory Verification Protocol** in MAP-PLAN agent -- explicit checklist requiring spec read, assumption verification, and ambiguity resolution
2. **Pre-flight in PATCH** -- must read plan, contract, and rules before starting
3. **`core-patterns.md`** loaded in every session -- "Verify by reading actual code, never assume"

### ENUM_VALUE (26% of fullstack failures)

**What happens**: Frontend sends the Python enum NAME (`CO_OWNER`, with underscore) when the backend expects the enum VALUE (`CO-OWNER`, with hyphen).

**Systematic prevention**: CONTRACT documents enum VALUES explicitly, PATCH pre-flight reads backend enum definitions, and PROVE verifies frontend strings match backend VALUES.

!!! tip "See also"
    For the full ENUM_VALUE pattern explanation with code examples, see [Core Patterns -- ENUM_VALUE](../rules/core-patterns.md#enum_value-in-detail).

### COMPONENT_API (17% of frontend failures)

**What happens**: Agent assumes a component's props or hook's return structure without reading the source.

**Why agents make this mistake**: Common patterns from training data. Most `useSession()` hooks return `{ session, loading }`. But your hook might return the context directly. The agent generates code that destructures a non-existent property.

**Real example**: `const { session } = useSession()` (wrong) vs `const session = useSession()` (correct -- hook returns context directly).

**Systematic prevention**:

1. **MAP agent** documents reusable component APIs with actual PropTypes
2. **PATCH verification table** lists every reused component and its verified API
3. **`core-patterns.md`** with `grep` command: `grep -A 15 "PropTypes" frontend/src/components/path/Component.jsx`

## Full Root Cause Taxonomy

Every failure is classified into exactly one canonical code. This enables automated pattern analysis via `/learn`.

| Code | Description | Typical Cause | Detection Agent |
|------|-------------|---------------|-----------------|
| `VERIFICATION_GAP` | Proceeded without verifying spec/code | Skipped spec, assumed structure | MAP-PLAN |
| `ENUM_VALUE` | Used enum NAME instead of VALUE | Python `CO_OWNER` vs string `"CO-OWNER"` | PATCH, PROVE |
| `COMPONENT_API` | Wrong props or hook usage | Assumed API without reading source | PATCH |
| `MULTI_MODEL` | Forgot to update related model | Changed User but not Advisor relationship | PATCH |
| `API_MISMATCH` | Frontend/backend contract violation | Schema field type mismatch | PATCH, PROVE |
| `ACCESS_CONTROL` | Missing/wrong permission dependency | Endpoint allows access without auth | PATCH |
| `MISSING_TEST` | Code path not covered | New functionality with 0% coverage | PROVE |
| `SQLITE_COMPAT` | PostgreSQL-only feature in tests | Used ARRAY type (SQLite incompatible) | PATCH |
| `STRUCTURE_VIOLATION` | Violated project rules | Created `backend/src/` directory | PATCH |
| `SCOPE_CREEP` | Beyond issue scope | Added feature not in issue | MAP-PLAN, PATCH |
| `LINT_ERROR` | Code style violations | Unused imports, formatting | PROVE |
| `OTHER` | Document specifics in details | Project-specific errors | Any |

## How Patterns Are Encoded as Rules

Patterns are encoded at three levels, each loaded conditionally to minimize context consumption:

```
core-patterns.md (Always loaded, ~12 lines)
    +-- Fullstack with enums? -> Check VALUE vs NAME
    +-- Reusing component?    -> Read PropTypes first
    +-- References spec?      -> Read spec FIRST

fastapi-layered-pattern.md (Loaded in backend contexts)
    +-- Enum rules: member names = UPPER_SNAKE, values = stored in DB
    +-- Layer rules: Repos never commit, Services never raise HTTPException

orchestrate-workflow.md (Loaded in .agents contexts)
    +-- CONTRACT mandatory for fullstack
    +-- Artifact validation: each agent checks predecessors
```

!!! warning "core-patterns.md is always loaded"
    This file is intentionally small (~12 lines). It contains only the three patterns that cause >50% of failures. Loading it costs fewer tokens than a single function definition.

## The "Read Before Assuming" Principle

Every agent in the pipeline has verification gates:

| Agent | What It Verifies |
|-------|-----------------|
| MAP / MAP-PLAN | Reads spec, reads actual code, documents component APIs and enum values |
| CONTRACT | Defines exact enum VALUES, endpoint schemas, auth requirements |
| PLAN-CHECK | Validates plan covers all acceptance criteria, enum VALUES explicit |
| PATCH | Pre-flight: reads plan + contract + rules. Pre-submission: runs ruff + pytest |
| PROVE | Verification levels: EXISTS, SUBSTANTIVE, WIRED, FUNCTIONAL |

## How These Patterns Were Discovered

These three patterns were not discovered through intuition. They were extracted from structured failure data using `/learn`:

```
86 issues completed
  -> 24 failures recorded
    -> /learn clusters by root_cause
      -> VERIFICATION_GAP: 63% -> Added Mandatory Verification Protocol to MAP-PLAN
      -> ENUM_VALUE: 26%       -> Made CONTRACT mandatory for fullstack
      -> COMPONENT_API: 17%    -> Added component API verification table to PATCH
```

Each prevention technique was added to the relevant agent definition, the agent version was incremented, and subsequent issues showed reduced failure rates. The loop continues indefinitely.
