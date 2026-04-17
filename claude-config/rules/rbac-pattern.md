# RBAC Pattern — Permission-Based Access Control

**Applies to:** All FastAPI projects (single-org applications)
**Pattern:** Permission-check dependencies with role-to-permission mapping

---

## Architecture

```
User.role (string) → ROLE_PERMISSIONS dict → require_permission("resource:action") dependency
```

Roles are simple strings on the User model. Permissions are `resource:action` strings. The mapping lives in code (movable to config). Endpoints declare required permissions via FastAPI dependencies.

## Implementation

### 1. Permission Map (one dict, one file)

```python
# app/core/permissions.py

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin":  {"*"},  # Wildcard — all permissions
    "editor": {
        "documents:read", "documents:write", "documents:delete",
        "extractions:read", "extractions:review",
        "chat:read", "chat:write",
        "recipes:read",
    },
    "viewer": {
        "documents:read",
        "extractions:read",
        "chat:read",
        "recipes:read",
    },
}
```

**Rules:**
- Permission format: `resource:action` (lowercase, colon-separated)
- Standard actions: `read`, `write`, `delete`, `review`, `manage`
- Admin uses `{"*"}` wildcard — never enumerate admin permissions
- New role = new dict entry, zero endpoint changes
- New resource = add permission strings to relevant roles

### 2. Dependency Factory (one function, reusable everywhere)

```python
# app/core/deps.py

from app.core.permissions import ROLE_PERMISSIONS

def require_permission(permission: str):
    """FastAPI dependency that checks the current user has the required permission."""
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        user_perms = ROLE_PERMISSIONS.get(current_user.role, set())
        if "*" not in user_perms and permission not in user_perms:
            raise ForbiddenError(
                f"Permission '{permission}' required",
                context={"role": current_user.role, "permission": permission},
            )
        return current_user
    return checker
```

### 3. Router Usage

```python
@router.post("/documents", ...)
async def upload(current_user: User = Depends(require_permission("documents:write"))):
    ...

@router.delete("/documents/{id}", ...)
async def delete(current_user: User = Depends(require_permission("documents:delete"))):
    ...
```

**Every endpoint must have a permission dependency** (E11 behavioral eval). Exception: health, login, public endpoints — must have a comment explaining why.

## Tag-Based Access (Optional Layer)

Tag-based access is an opt-in configuration layer on top of RBAC:

```python
# Settings
tag_based_access_enabled: bool = False  # Default: all users see all content
```

When enabled, content is filtered by user's allowed tags. When disabled, RBAC permissions alone control access. This is application-level filtering (WHERE clauses), not database-level isolation.

## Why This Pattern

- **Auditable:** grep for `"documents:delete"` to see every protected endpoint
- **Extensible:** new roles = one dict entry, no endpoint changes
- **Portable:** same pattern works across all FastAPI projects
- **Simple:** no permissions table, no ABAC, no policy engine — just a dict + dependency
- **Standard:** matches Django permissions, Spring authorities, AWS IAM policy model

## When NOT to Use

- Multi-tenant SaaS with org-level isolation → add tenant_id + RLS
- Fine-grained per-object permissions → add an ACL table
- Complex attribute-based rules → use casbin or OPA

For single-org applications, this pattern covers 95% of access control needs.
