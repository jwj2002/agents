---
paths: ["**/backend/**", "**/frontend/**", "**/.agents/**", "**/Dockerfile", "**/*.env*"]
---

# Behavioral Evals — Production-Derived Verification Checks

Each eval traces back to a real failure. PROVE runs applicable evals based on changed files
(see `eval-file-mapping.md`). Every eval has: what to check, why, and how to verify.

---

## E01: ENUM_VALUE_MISMATCH
**What**: Frontend references backend enum by Python name instead of value
**Why**: `"CO_OWNER"` silently fails — server expects `"CO-OWNER"`. No error, just wrong behavior.
**Trigger files**: `*.tsx`, `*.ts`, `schemas/*.py`, `models/base.py`
**How to verify**:
1. Grep changed frontend files for string literals matching status/role/type patterns
2. Cross-reference each with backend `StrEnum` definitions in `models/base.py`
3. Verify the frontend uses the VALUE (`"CO-OWNER"`) not the NAME (`"CO_OWNER"`)

## E02: COMPONENT_API_MISMATCH
**What**: Reusing a frontend component with wrong props or missing required props
**Why**: Component renders but silently ignores unknown props, producing broken UI
**Trigger files**: `*.tsx`, `*.ts`
**How to verify**:
1. For each imported component in changed files, read the component's source
2. Extract its prop interface/types
3. Verify all required props are passed with correct types

## E03: HOOK_DEPENDENCY_ARRAY
**What**: React hook has missing or incorrect dependency array
**Why**: Stale closures, infinite re-renders, or effects that don't fire
**Trigger files**: `*.tsx`, `*.ts`
**How to verify**:
1. Grep for `useEffect`, `useMemo`, `useCallback` in changed files
2. Check that every referenced variable appears in the dependency array
3. Check for objects/arrays in deps that should be memoized

## E04: MODEL_WITHOUT_MIGRATION
**What**: SQLAlchemy model changed but no Alembic migration generated
**Why**: App starts fine in dev but fails in staging/production when DB schema doesn't match
**Trigger files**: `models/*.py`
**How to verify**:
1. Check if any model column was added, removed, or type-changed
2. Check if a corresponding Alembic migration exists in the same commit/PR
3. If model changed and no migration: FAIL

## E05: NULLABLE_MISMATCH
**What**: Model column `nullable` doesn't match schema `Optional` / required
**Why**: 500 errors when API accepts null but DB rejects it (or vice versa)
**Trigger files**: `models/*.py`, `schemas/*.py`
**How to verify**:
1. For each changed model field, check `nullable=True/False`
2. Find the corresponding Pydantic schema field
3. Verify: `nullable=True` ↔ `Optional[T]` / `T | None`; `nullable=False` ↔ required field

## E06: SCHEMA_MODEL_DRIFT
**What**: Pydantic schema fields don't match SQLAlchemy model fields
**Why**: API silently drops fields on read, or 422 validation errors on write
**Trigger files**: `schemas/*.py`, `models/*.py`
**How to verify**:
1. For each changed schema, compare fields against the corresponding model
2. Check for: missing fields, type mismatches, wrong field names
3. Pay special attention to `float` vs `Decimal` for financial fields

## E07: MIGRATION_NOT_ADDITIVE
**What**: Migration drops columns, renames tables, or modifies types destructively
**Why**: Rollback impossible; data loss if migration fails halfway
**Trigger files**: `alembic/versions/*.py`
**How to verify**:
1. Read the migration's `upgrade()` function
2. Flag any `drop_column`, `drop_table`, `alter_column` (type change) operations
3. Verify `downgrade()` exists and is the inverse of `upgrade()`

## E08: MIGRATION_MISSING_INDEX
**What**: Migration adds a foreign key but no index on the FK column
**Why**: JOIN and WHERE queries on that FK will be full table scans
**Trigger files**: `alembic/versions/*.py`
**How to verify**:
1. Check for `add_column` with `ForeignKey` in the migration
2. Verify a corresponding `create_index` exists for that column
3. Exception: the FK is part of a composite unique constraint (leading column)

## E09: SERVICE_BYPASSES_REPO
**What**: Service executes raw SQLAlchemy queries via `self.db.execute()` instead of repository
**Why**: Breaks the repo abstraction; soft-delete filters, audit hooks, query changes in repos won't apply
**Trigger files**: `services/*.py`
**How to verify**:
1. Grep for `self.db.execute`, `self.db.add`, `self.db.flush` in changed service files
2. Each should go through `self.repo.*` methods instead
3. Exception: complex aggregation queries with no natural repo home (document with comment)

## E10: STALE_DATA_UNHANDLED
**What**: ORM flush without catching `StaleDataError` on models with `version_id_col`
**Why**: Concurrent edits produce 500 Internal Server Error instead of 409 Conflict
**Trigger files**: `services/*.py`, `repositories/*.py`
**How to verify**:
1. Find any `db.flush()` or `db.commit()` on models that have `version_id_col`
2. Verify the flush is wrapped in `try/except StaleDataError` → `ConflictError`
3. Or verify it goes through `BaseRepository.update()` which handles this

## E11: AUTH_DEPENDENCY_MISSING
**What**: Router endpoint missing auth dependency (`CurrentUser`, `AdminUser`, etc.)
**Why**: Endpoint is publicly accessible — anyone can call it without authentication
**Trigger files**: `routers/*.py`
**How to verify**:
1. For each new or modified endpoint in changed router files
2. Check that it has an auth dependency parameter (`current_user: CurrentUser`)
3. Exception: explicitly public endpoints (health, login, public branding) — must have a comment

## E12: AUDIT_LOG_MISSING
**What**: Router performs create/update/delete but doesn't call `AuditService`
**Why**: Incomplete audit trail — compliance gap, can't trace who changed what
**Trigger files**: `routers/*.py`, `services/*.py`
**How to verify**:
1. For each POST/PUT/PATCH/DELETE endpoint in changed routers
2. Verify `AuditService.log_create/log_update/log_delete` is called
3. Or verify audit logging is handled in the service layer for this entity

## E13: MISSING_FK_INDEX
**What**: Foreign key column defined without `index=True`
**Why**: Queries filtering or joining on this FK will do full table scans
**Trigger files**: `models/*.py`
**How to verify**:
1. For each `ForeignKey` column in changed models
2. Check for `index=True` on the column definition
3. Exception: column is the leading column in a composite unique constraint

## E14: DOCKER_ROOT_USER
**What**: Dockerfile has no `USER` directive — container runs as root
**Why**: Code execution vulnerability gives attacker root inside the container
**Trigger files**: `Dockerfile`
**How to verify**:
1. Check for a `USER` directive after the last `RUN` / before `ENTRYPOINT`
2. Verify a non-root user is created (`adduser` or `useradd`)

## E15: SECRETS_IN_CODE
**What**: Hardcoded API keys, passwords, tokens, or connection strings in source files
**Why**: Leaked to version control; anyone with repo access has the credentials
**Trigger files**: `*.py`, `*.ts`, `*.tsx`, `*.env.example`
**How to verify**:
1. Grep for patterns: `password=`, `secret=`, `api_key=`, `token=` followed by string literals
2. Check for base64-encoded strings that look like credentials
3. Exception: test fixtures with obviously fake values (`test-secret`, `password123`)
