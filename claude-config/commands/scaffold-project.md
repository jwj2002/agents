---
description: Scaffold a complete FastAPI project with layered architecture (database, auth, core, alembic, tests)
argument-hint: <project_name> [--with-auth] [--db postgres|sqlite] [--target-dir .]
---

# Scaffold Project Command

**Role**: Generate a complete FastAPI project skeleton following the layered architecture pattern.

---

## Usage

```bash
/scaffold-project myapp
/scaffold-project myapp --with-auth --db postgres
/scaffold-project myapp --target-dir ~/projects
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

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `project_name` | Yes | — | Directory name and Python package name (snake_case) |
| `--with-auth` | No | `false` | Include JWT auth module |
| `--db` | No | `postgres` | `postgres` (psycopg2) or `sqlite` |
| `--target-dir` | No | `.` (cwd) | Parent directory for the project |

---

## Step 2: Generate Project Structure

Create this directory tree:

```
{project_name}/
├── backend/
│   ├── backend/                  # Python package (flat layout)
│   │   ├── __init__.py
│   │   ├── main.py              # App factory, middleware, registration
│   │   ├── main_router.py       # Router aggregator
│   │   ├── database.py          # Engine, session, Base, mixins
│   │   ├── logger.py            # Logging configuration
│   │   ├── enums.py             # Shared enums (Frequency, etc.)
│   │   └── core/
│   │       ├── __init__.py
│   │       ├── config.py        # Pydantic Settings v2
│   │       ├── repository.py    # BaseRepository[T]
│   │       ├── exceptions.py    # Domain exception hierarchy
│   │       ├── error_handlers.py # Exception → HTTP response mapping
│   │       ├── cors.py          # CORS middleware configuration
│   │       └── hashing.py       # Password hashing (bcrypt)
│   ├── tests/
│   │   ├── __init__.py
│   │   └── conftest.py          # SQLite test fixtures
│   ├── alembic/
│   │   ├── env.py               # Alembic environment
│   │   ├── script.py.mako       # Migration template
│   │   └── versions/            # Migration files (empty)
│   ├── alembic.ini              # Alembic configuration
│   ├── setup.py                 # Package setup (flat layout)
│   ├── requirements.txt         # Dependencies
│   ├── .env.example             # Environment variable template
│   └── .env                     # Local env (gitignored)
├── scripts/
│   ├── start.sh                 # Start all services (DB, backend, frontend)
│   └── stop.sh                  # Stop all services
├── .gitignore
└── README.md
```

**Scripts**: Load the `dev-scripts` pattern via `get_pattern("dev-scripts")` and generate `start.sh` and `stop.sh` with the project name substituted. Make both executable (`chmod +x`).

If `--with-auth` is set, also generate the `auth/` module (see auth template reference below).

---

## Step 3: File Contents

**Read** `templates/scaffold-fastapi-core.md` for the full set of file templates.

That reference contains the canonical content for: `main.py`, `main_router.py`, `database.py`, `core/config.py`, `core/repository.py`, `core/exceptions.py`, `core/error_handlers.py`, `core/cors.py`, `core/hashing.py`, `logger.py`, `tests/conftest.py`, `setup.py`, `requirements.txt`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `.env.example`, `.gitignore`, `README.md`.

Substitute `{project_name}` throughout. For `--db sqlite`, use the SQLite alternative shown in the `core/config.py` template.

---

## Step 4: Auth Module (if `--with-auth`)

**Read** `templates/scaffold-fastapi-auth.md` for the auth module reference.

That reference covers `auth/enums.py`, `auth/models.py`, `auth/schemas.py`, `auth/oauth2.py`, `auth/repository.py`, `auth/services.py`, `auth/deps.py`, `auth/router.py`.

After generating, register in `main.py` and `main_router.py`.

---

## Step 5: Verify Generation

After generating all files, run:

```bash
# Check Python syntax on all generated files
find $TARGET/$PROJECT/backend/backend -name "*.py" -exec python3 -c "import ast; ast.parse(open('{}').read())" \;

# Verify directory structure
find $TARGET/$PROJECT -type f | sort
```

---

## Step 6: Post-Generation Instructions

Print to the user:

```
Project scaffolded at: ./{project_name}/

Quick start:
  cd {project_name}/backend
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt && pip install -e .
  cp .env.example .env  # Edit with your database credentials
  alembic upgrade head
  uvicorn backend.main:app --reload

  # Open: http://localhost:8000/docs

Add modules:
  /scaffold-module items --fields "name:str, amount:Decimal"

Run tests:
  cd backend && pytest

Lint:
  cd backend && ruff check .
```

---

## Rules

**MUST**:
- Follow ALL conventions from `~/.claude/rules/fastapi-layered-pattern.md`
- Generate the enhanced BaseRepository with `get_with_filter`, `list_by`, `exists`, `count`
- Include exception hierarchy + error handlers
- Include SQLite test fixtures in conftest.py
- Use Pydantic Settings v2 (`pydantic-settings`)
- Use SQLAlchemy 2.0 syntax throughout

**MUST NOT**:
- Include any hardcoded secrets (use placeholders)
- Create `backend/src/` (flat layout: `backend/backend/`)
- Put business logic in routers
- Skip the `.env.example`

**SHOULD**:
- Generate working code that starts immediately after `pip install`
- Include helpful comments in generated files
- Match the style of the mymoney-dev reference implementation
