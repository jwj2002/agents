---
description: Scaffold a new FastAPI module (model, schema, repo, service, router, deps)
argument-hint: <module_name> [--fields "name:str, amount:Decimal, is_active:bool"] [--account-scoped] [--parent-dir backend/backend]
---

# Scaffold Module Command

**Role**: Code generator for the FastAPI layered architecture pattern.

---

## Usage

```bash
/scaffold-module items --fields "name:str, amount:Decimal, is_active:bool" --account-scoped
/scaffold-module notifications --fields "title:str, body:str, read:bool"
/scaffold-module items --parent-dir backend/backend   # Explicit path
```

---

## Step 0: Load Pattern Reference

**MANDATORY** — Read the pattern reference before generating anything:

```bash
cat ~/.claude/rules/fastapi-layered-pattern.md
```

Apply ALL conventions from this document.

---

## Step 1: Parse Arguments

Extract from the command arguments:

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `module_name` | Yes | — | Snake_case module name (e.g., `items`, `notifications`) |
| `--fields` | No | `name:str` | Comma-separated `field:type` pairs |
| `--account-scoped` | No | `true` | Whether entity belongs to an account (adds `account_id` FK) |
| `--parent-dir` | No | Auto-detect | Path to the backend package directory |

### Auto-detect parent directory

```bash
# Look for existing module structure
if [ -d "backend/backend" ]; then
  PARENT="backend/backend"
elif [ -d "backend/app" ]; then
  PARENT="backend/app"
elif [ -d "app" ]; then
  PARENT="app"
else
  # Ask user
  echo "Cannot detect backend package directory. Provide --parent-dir."
fi
```

### Parse field types

Map shorthand types to Python/SQLAlchemy:

| Shorthand | Python Type | SQLAlchemy Column | Pydantic |
|-----------|-------------|-------------------|----------|
| `str` | `str` | `String(255)` | `str` |
| `text` | `str` | `Text` | `str` |
| `int` | `int` | `Integer` | `int` |
| `float` | `float` | `Float` | `float` |
| `Decimal` | `Decimal` | `Numeric(12,2)` | `Decimal` |
| `bool` | `bool` | `Boolean` | `bool` |
| `date` | `date` | `Date` | `date` |
| `datetime` | `datetime` | `DateTime(timezone=True)` | `datetime` |
| `uuid` | `uuid.UUID` | `UUID(as_uuid=True)` | `uuid.UUID` |
| `json` | `dict` | `JSON` | `dict` |
| `str?` | `Optional[str]` | `String(255), nullable=True` | `Optional[str] = None` |

The `?` suffix makes any type optional/nullable.

---

## Step 2: Verify Target Directory

```bash
ls $PARENT/
# Confirm directory exists and contains other modules
```

If the module already exists, STOP and ask the user:
- Overwrite?
- Add to existing module?
- Cancel?

---

## Step 3: Generate Files

Create the module directory and all 7 files. The content of each file follows the templates below.

### Directory Structure

```bash
mkdir -p $PARENT/$MODULE_NAME
```

### File Generation Order

Generate files in this order (each references the pattern doc):

1. `__init__.py` — empty
2. `enums.py` — if any enum fields detected
3. `models.py` — SQLAlchemy model
4. `schemas.py` — Pydantic Create/Update/Read
5. `repository.py` — BaseRepository subclass
6. `services.py` — BaseService subclass (or convention-following service)
7. `deps.py` — FastAPI dependency factories
8. `router.py` — CRUD endpoints

---

## Step 4: Generate Model (`models.py`)

Template rules:
- Class name: PascalCase singular (e.g., `Item`, `Notification`)
- Table name: snake_case plural (e.g., `items`, `notifications`)
- Always UUID primary key
- Always TimestampMixin
- If `--account-scoped`: add `account_id` FK with CASCADE and index
- All fields from `--fields` mapped to SQLAlchemy columns
- Optional fields (`?` suffix) use `Mapped[Optional[T]]` + `nullable=True`
- Add relationship to Account if account-scoped

---

## Step 5: Generate Schemas (`schemas.py`)

Template rules:
- `{Entity}Create`: Required fields only, no `id`, no timestamps
- `{Entity}Update`: All domain fields as `Optional[T] = None`
- `{Entity}Read`: All fields including `id`, `created_at`, `updated_at`, with `ConfigDict(from_attributes=True)`
- If account-scoped: `account_id` in Read but NOT in Create (injected from URL path)

---

## Step 6: Generate Repository (`repository.py`)

Template rules:
- Extends `BaseRepository[Entity]`
- Sets `model = Entity`
- If account-scoped: add `get_for_account(id, account_id)` and `list_for_account(account_id)`
- Add `get_with_relations()` if model has relationships
- No commits, no exceptions

---

## Step 7: Generate Service (`services.py`)

Template rules:
- Constructor takes `db: Session`, creates repo internally
- Standard methods: `create_item`, `update_item`, `delete_item`
- Tenant verification on update/delete (if account-scoped)
- Raises `EntityNotFound` / `ConflictError` where appropriate
- Never raises `HTTPException`
- Commits in create/update/delete

---

## Step 8: Generate Dependencies (`deps.py`)

Template rules:
- `get_{entity}_repo(db) -> Repository`
- `get_{entity}_service(db) -> Service`
- Import `get_db` from database module

---

## Step 9: Generate Router (`router.py`)

Template rules:
- If account-scoped: prefix = `/accounts/{account_id}/{module_name}`
- If not: prefix = `/{module_name}`
- Standard CRUD endpoints: list, get, create, update, delete
- Access control via `Depends(require_account_access)` / `Depends(require_account_owner)`
- Proper status codes: GET=200, POST=201, PATCH=200, DELETE=204
- `response_model` on all endpoints
- Zero business logic

---

## Step 10: Registration Reminders

After generating, tell the user what to register manually:

```
Module generated at: $PARENT/$MODULE_NAME/

Next steps:
1. Register model import in main.py:
   import backend.$MODULE_NAME.models  # noqa: F401

2. Register router in main_router.py:
   from backend.$MODULE_NAME.router import router as ${MODULE_NAME}_router
   api_router.include_router(${MODULE_NAME}_router, prefix="", tags=["$MODULE_NAME"])

3. Create migration:
   cd backend && alembic revision --autogenerate -m "Add $MODULE_NAME table"
   cd backend && alembic upgrade head

4. Add tests:
   mkdir -p tests/${MODULE_NAME}_tests
   # Create test_${MODULE_NAME}_service.py following test patterns
```

---

## Step 11: Verify

After generation, verify:

```bash
# Check all files exist
ls -la $PARENT/$MODULE_NAME/

# Check Python syntax
python3 -c "import ast; ast.parse(open('$PARENT/$MODULE_NAME/models.py').read())"
python3 -c "import ast; ast.parse(open('$PARENT/$MODULE_NAME/schemas.py').read())"
python3 -c "import ast; ast.parse(open('$PARENT/$MODULE_NAME/repository.py').read())"
python3 -c "import ast; ast.parse(open('$PARENT/$MODULE_NAME/services.py').read())"
python3 -c "import ast; ast.parse(open('$PARENT/$MODULE_NAME/deps.py').read())"
python3 -c "import ast; ast.parse(open('$PARENT/$MODULE_NAME/router.py').read())"
```

---

## Rules

**MUST**:
- Follow ALL conventions from `~/.claude/rules/fastapi-layered-pattern.md`
- Use UUID primary keys
- Use TimestampMixin
- Include `from_attributes=True` on Read schemas
- Use proper SQLAlchemy 2.0 syntax (`Mapped[T]`, `mapped_column`)
- Generate all 7 files (including empty `__init__.py`)

**MUST NOT**:
- Put business logic in router
- Put HTTP exceptions in service
- Commit in repository
- Create files outside the module directory
- Skip the registration reminders

**SHOULD**:
- Add helpful comments referencing the pattern doc
- Use type hints everywhere
- Follow existing project conventions if detectable
