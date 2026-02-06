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
| `--with-auth` | No | `false` | Include JWT auth module (User model, login, signup, token refresh) |
| `--db` | No | `postgres` | Database backend: `postgres` (psycopg2) or `sqlite` |
| `--target-dir` | No | `.` (cwd) | Parent directory for the project |

---

## Step 2: Generate Project Structure

Create this complete directory tree:

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
├── .gitignore
└── README.md
```

If `--with-auth` is set, also generate:

```
│   │   └── auth/
│   │       ├── __init__.py
│   │       ├── models.py        # User model
│   │       ├── schemas.py       # Auth schemas (login, signup, token)
│   │       ├── enums.py         # SystemRole enum
│   │       ├── repository.py    # UserRepository
│   │       ├── services.py      # UserService (auth, create, password)
│   │       ├── oauth2.py        # JWT token creation/verification
│   │       ├── deps.py          # get_current_user, get_user_service
│   │       └── router.py        # Login, signup, refresh endpoints
```

---

## Step 3: File Contents

### `backend/backend/__init__.py`
Empty file.

### `backend/backend/main.py`

```python
from fastapi import FastAPI

from backend.core.config import settings
from backend.core.cors import add_cors_middleware
from backend.core import exceptions as exc
from backend.core import error_handlers
from backend.logger import setup_logging


def start_application() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
    )

    add_cors_middleware(app)

    # --- Model imports (register with SQLAlchemy) ---
    # import backend.module_name.models  # noqa: F401

    # --- Auto-create tables (dev only) ---
    if settings.AUTO_CREATE_TABLES:
        from backend.database import Base, engine
        Base.metadata.create_all(bind=engine)

    # --- Register routes ---
    from backend.main_router import api_router
    app.include_router(api_router)

    # --- Register exception handlers ---
    app.add_exception_handler(exc.EntityNotFound, error_handlers.handle_entity_not_found)
    app.add_exception_handler(exc.ConflictError, error_handlers.handle_conflict)
    app.add_exception_handler(exc.BusinessValidationError, error_handlers.handle_business_validation)
    app.add_exception_handler(exc.PermissionDenied, error_handlers.handle_permission_denied)
    app.add_exception_handler(exc.AuthenticationError, error_handlers.handle_authentication_error)
    app.add_exception_handler(exc.ExternalServiceError, error_handlers.handle_external_service_error)
    app.add_exception_handler(exc.AppError, error_handlers.handle_app_error)

    return app


app = start_application()
```

### `backend/backend/main_router.py`

```python
from fastapi import APIRouter

api_router = APIRouter()

# Register module routers here:
# from backend.module_name.router import router as module_router
# api_router.include_router(module_router, prefix="", tags=["module_name"])
```

### `backend/backend/database.py`

```python
import datetime as dt
from typing import Generator

from sqlalchemy import DateTime, create_engine, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

from backend.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class TimestampMixin:
    """Mixin adding created_at and updated_at columns."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

### `backend/backend/core/config.py`

Generate with appropriate DATABASE_URL based on `--db` flag:

```python
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Project
    PROJECT_NAME: str = "{project_name}"
    PROJECT_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="dev")

    # Database (postgres or sqlite based on flag)
    # For postgres:
    POSTGRES_USER: str = Field(default="postgres")
    POSTGRES_PASSWORD: str = Field(default="postgres")
    POSTGRES_SERVER: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="{project_name}")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # For sqlite alternative:
    # DATABASE_URL: str = Field(default="sqlite:///./app.db")

    # Auth (if --with-auth)
    SECRET_KEY: str = Field(default="change-me-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_HASH_ROUNDS: int = Field(default=12)

    # Startup
    AUTO_CREATE_TABLES: bool = Field(default=True)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

### `backend/backend/core/repository.py`

Generate the full BaseRepository with enhanced methods:

```python
from __future__ import annotations

from typing import Any, Generic, Iterable, List, Optional, Type, TypeVar

from sqlalchemy import exists as sa_exists, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic base repository for SQLAlchemy models."""

    model: Type[T]

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Retrieval ---

    def get(self, id_: Any) -> Optional[T]:
        return self.db.get(self.model, id_)

    def get_with_filter(self, id_: Any, **filters: Any) -> Optional[T]:
        stmt = select(self.model).where(self.model.id == id_)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return self.db.scalar(stmt)

    def list_all(self) -> List[T]:
        return list(self.db.scalars(select(self.model)).all())

    def list_by(self, **filters: Any) -> list[T]:
        stmt = select(self.model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return list(self.db.scalars(stmt).all())

    def list_paginated(self, *, offset: int = 0, limit: int = 50) -> list[T]:
        if limit <= 0:
            return []
        stmt = select(self.model).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def exists(self, **filters: Any) -> bool:
        conditions = [getattr(self.model, k) == v for k, v in filters.items()]
        stmt = select(sa_exists().where(*conditions))
        return self.db.scalar(stmt) or False

    def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        return self.db.scalar(stmt) or 0

    # --- Persistence ---

    def add(self, obj: T) -> T:
        self.db.add(obj)
        return obj

    def delete(self, obj: T) -> None:
        self.db.delete(obj)

    def commit(self) -> None:
        self.db.commit()

    def flush(self) -> None:
        self.db.flush()

    def refresh(self, obj: T) -> T:
        self.db.refresh(obj)
        return obj

    # --- Update ---

    def partial_update(self, obj: T, skip_none: bool = True, **fields: Any) -> T:
        for key, value in fields.items():
            if skip_none and value is None:
                continue
            setattr(obj, key, value)
        self.db.add(obj)
        return obj

    # --- Bulk ---

    def add_all(self, objs: Iterable[T]) -> None:
        self.db.add_all(list(objs))

    def delete_all(self, objs: Iterable[T]) -> None:
        for obj in objs:
            self.db.delete(obj)
```

### `backend/backend/core/exceptions.py`

```python
class AppError(Exception):
    """Base application exception."""
    default_message = "An unexpected error occurred"

    def __init__(self, message: str | None = None, context: dict | None = None):
        self.message = message or self.default_message
        self.context = context or {}
        super().__init__(self.message)


class EntityNotFound(AppError):
    default_message = "Requested entity was not found"


class ConflictError(AppError):
    default_message = "Resource conflict"


class BusinessValidationError(AppError):
    default_message = "Business rule validation failed"


class PermissionDenied(AppError):
    default_message = "Permission denied"


class AuthenticationError(AppError):
    default_message = "Authentication failed"


class ExternalServiceError(AppError):
    default_message = "External service error"
```

### `backend/backend/core/error_handlers.py`

```python
from fastapi import Request
from fastapi.responses import JSONResponse

from . import exceptions as exc


def _error_response(status_code: int, code: str, error: exc.AppError) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": error.message,
                "context": error.context,
            }
        },
    )


async def handle_entity_not_found(request: Request, error: exc.EntityNotFound) -> JSONResponse:
    return _error_response(404, "entity_not_found", error)


async def handle_conflict(request: Request, error: exc.ConflictError) -> JSONResponse:
    return _error_response(409, "conflict", error)


async def handle_business_validation(request: Request, error: exc.BusinessValidationError) -> JSONResponse:
    return _error_response(422, "business_validation_error", error)


async def handle_permission_denied(request: Request, error: exc.PermissionDenied) -> JSONResponse:
    return _error_response(403, "permission_denied", error)


async def handle_authentication_error(request: Request, error: exc.AuthenticationError) -> JSONResponse:
    return _error_response(401, "authentication_error", error)


async def handle_external_service_error(request: Request, error: exc.ExternalServiceError) -> JSONResponse:
    return _error_response(502, "external_service_error", error)


async def handle_app_error(request: Request, error: exc.AppError) -> JSONResponse:
    return _error_response(500, "internal_app_error", error)
```

### `backend/backend/core/cors.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings


def add_cors_middleware(app: FastAPI) -> None:
    origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

### `backend/backend/core/hashing.py`

```python
import bcrypt

from backend.core.config import settings


class Hasher:
    @staticmethod
    def get_password_hash(password: str) -> str:
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt(rounds=settings.PASSWORD_HASH_ROUNDS)
        return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
```

### `backend/backend/logger.py`

```python
import logging
import logging.config


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": "INFO",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}


def setup_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)
```

### `backend/tests/conftest.py`

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base


@pytest.fixture(scope="session")
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
```

### `backend/setup.py`

```python
from setuptools import setup, find_packages

setup(
    name="{project_name}",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.11",
)
```

### `backend/requirements.txt`

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
sqlalchemy>=2.0.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
alembic>=1.13.0
python-dotenv>=1.0.0
python-multipart>=0.0.9
bcrypt>=4.1.0

# Database driver (match --db flag)
psycopg2-binary>=2.9.0    # postgres
# or: no extra driver needed for sqlite

# Auth (if --with-auth)
python-jose[cryptography]>=3.3.0

# Testing
pytest>=8.0.0
httpx>=0.27.0
ruff>=0.3.0
```

### `backend/alembic.ini`

Standard alembic config with `sqlalchemy.url` pointing to env var:

```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+psycopg2://postgres:postgres@localhost:5432/{project_name}

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

### `backend/alembic/env.py`

Standard Alembic env.py that imports Base.metadata for autogenerate:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### `backend/alembic/script.py.mako`

Standard Alembic migration template (use default Alembic template).

### `backend/.env.example`

```
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB={project_name}

# Auth
SECRET_KEY=change-me-generate-with-python-secrets
ALGORITHM=HS256

# App
ENVIRONMENT=dev
AUTO_CREATE_TABLES=true
```

### `.gitignore`

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.env
*.db
venv/
.venv/
.pytest_cache/
.ruff_cache/
logs/
```

### `README.md`

Generate a brief README with:
- Project name and description
- Quick start (venv, install, run)
- Architecture overview (link to pattern doc)
- Testing commands
- Adding new modules (link to /scaffold-module)

---

## Step 4: Auth Module (if `--with-auth`)

Generate a complete auth module following the layered pattern:

### `auth/enums.py`
```python
from enum import Enum

class SystemRole(str, Enum):
    ADMIN = "ADMIN"
    STANDARD = "STANDARD"
```

### `auth/models.py`
- `User` model with: id (UUID), email (unique, indexed), hashed_password, name, is_active, system_role, date_joined, last_login

### `auth/schemas.py`
- `UserCreate`: email, password, name
- `UserRead`: id, email, name, is_active, system_role, date_joined
- `LoginResponse`: access_token, token_type, user_id
- `TokenData`: email (from JWT sub claim)

### `auth/oauth2.py`
- `create_access_token(data, expires_delta)` — JWT with HS256
- `create_refresh_token(data)` — longer-lived JWT in httpOnly cookie
- `get_current_user(token)` — decode JWT, load user, return User
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")`

### `auth/repository.py`
- `UserRepository(BaseRepository[User])`
- `get_by_email(email)` — for login lookup
- `exists_by_email(email)` — for duplicate check

### `auth/services.py`
- `UserService` with: `authenticate_user`, `create_user`, `get_user_by_id`
- Raises `AuthenticationError`, `ConflictError`, `EntityNotFound`
- Never raises HTTPException

### `auth/deps.py`
- `get_user_repo(db)`, `get_user_service(db)`
- Re-export `get_current_user` from oauth2

### `auth/router.py`
- `POST /login` — OAuth2 password flow, returns access + refresh token
- `POST /signup` — Create user, auto-login
- `POST /auth/refresh` — Rotate refresh token from cookie
- `GET /users/me` — Current user profile

Register in main.py and main_router.py.

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
