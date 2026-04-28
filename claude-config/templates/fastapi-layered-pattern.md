---
paths: ["**/backend/**", "**/api/**", "**/services/**"]
---

# FastAPI Layered Architecture Pattern

**Version**: 1.0
**Purpose**: Definitive reference for the Model → Schema → Repository → Service → Router → Deps pattern. Apply this to any FastAPI project.

---

## Architecture Overview

```
Request → Router (HTTP) → Service (Business Logic) → Repository (Data Access) → Database
            ↑                    ↑                         ↑
          deps.py             schemas.py               models.py
       (access control)    (validation)             (ORM definitions)
```

**Transaction boundary**: Service layer commits. Repositories never commit.

**Error boundary**: Services raise domain exceptions. Routers never catch — global error handlers convert to HTTP responses.

---

## Module Structure

Every domain module follows this structure:

```
module_name/
├── __init__.py        # Empty or re-exports
├── models.py          # SQLAlchemy ORM models
├── schemas.py         # Pydantic request/response schemas
├── enums.py           # Module-specific enums (if needed)
├── repository.py      # Data access layer (extends BaseRepository)
├── services.py        # Business logic layer (extends BaseService)
├── deps.py            # FastAPI dependencies (repo/service factories + access control)
└── router.py          # HTTP endpoints (thin layer)
```

For larger modules with multiple entities, use subdirectories:

```
module_name/
├── models/
│   ├── __init__.py
│   ├── entity_a.py
│   └── entity_b.py
├── schemas/
│   ├── __init__.py
│   ├── entity_a.py
│   └── entity_b.py
├── repositories/
│   ├── __init__.py
│   └── ...
├── services/
│   ├── __init__.py
│   └── ...
├── routers/
│   ├── __init__.py
│   └── ...
├── deps.py
└── enums.py
```

---

## Layer 1: Models (`models.py`)

### Base Classes

```python
from backend.database import Base, TimestampMixin
```

All models inherit from `Base` and use `TimestampMixin` for audit fields.

### Standard Model Template

```python
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base, TimestampMixin


class Item(TimestampMixin, Base):
    __tablename__ = "items"

    # Primary key — always UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Required fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional fields
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="items")
```

### Rules

| Rule | Detail |
|------|--------|
| Primary keys | Always `UUID` with `default=uuid.uuid4` |
| Foreign keys | Always indexed, always set `ondelete` (`CASCADE`, `SET NULL`, `RESTRICT`) |
| Timestamps | Always use `TimestampMixin` (provides `created_at`, `updated_at`) |
| Type hints | Always `Mapped[T]` with `mapped_column()` (SQLAlchemy 2.0) |
| Nullable | `Mapped[Optional[T]]` + `nullable=True` for optional fields |
| Relationships | Always use `back_populates` for bidirectional |
| Business logic | None. Use `@property` only for simple derived fields |
| Table names | Plural, lowercase, snake_case (`items`, `account_members`) |

### Enums

```python
# module_name/enums.py
from enum import Enum

class ItemStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
```

**Convention**: Enum member names = UPPER_SNAKE. Values = what gets stored in DB and sent to frontend.

**Critical**: Frontend uses the VALUE (right side), not the Python NAME (left side). When `CO_OWNER = "CO-OWNER"`, the API sends `"CO-OWNER"`.

---

## Layer 2: Schemas (`schemas.py`)

### Standard Schema Set

Every entity needs up to 4 schemas:

```python
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# 1. Base — shared fields (optional, use when Create and Read overlap heavily)
class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None


# 2. Create — fields needed to create (no id, no timestamps)
class ItemCreate(ItemBase):
    account_id: uuid.UUID


# 3. Update — all fields optional (PATCH semantics)
class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# 4. Read — full representation including DB-generated fields
class ItemRead(ItemBase):
    id: uuid.UUID
    account_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

### Rules

| Rule | Detail |
|------|--------|
| `from_attributes=True` | Always on Read schemas (enables ORM → Pydantic) |
| Create schemas | No `id`, no timestamps. Only what the client provides |
| Update schemas | All fields `Optional[T] = None`. Supports partial updates |
| Read schemas | Include all DB fields + computed properties + nested relationships |
| Nested reads | Use for preventing N+1 queries. Create slim `*ReadNested` variants |
| Validation | Use `Field(ge=0, le=100)`, `@field_validator`, annotated types |
| No business logic | Validation only — no side effects |

### Pagination Response

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
```

### Discriminated Unions (Polymorphic Entities)

```python
from typing import Annotated, Literal, Union
from fastapi import Body

class BankAccountCreate(ItemBase):
    type: Literal[AssetType.BANK_ACCOUNT]
    bank_name: str

class RetirementAccountCreate(ItemBase):
    type: Literal[AssetType.RETIREMENT_ACCOUNT]
    employer: str

AssetCreateUnion = Annotated[
    Union[BankAccountCreate, RetirementAccountCreate],
    Body(discriminator="type"),
]
```

---

## Layer 3: Repository (`repository.py`)

### BaseRepository API

All repositories extend `BaseRepository[T]` from `core/repository.py`.

```python
class BaseRepository(Generic[T]):
    model: Type[T]  # Subclass must set this

    def __init__(self, db: Session) -> None

    # Retrieval
    def get(self, id_: Any) -> Optional[T]
    def list_all(self) -> list[T]
    def list_paginated(self, *, offset: int = 0, limit: int = 50) -> list[T]

    # Persistence (none of these commit)
    def add(self, obj: T) -> T
    def delete(self, obj: T) -> None
    def commit(self) -> None
    def flush(self) -> None
    def refresh(self, obj: T) -> T

    # Update
    def partial_update(self, obj: T, skip_none: bool = True, **fields: Any) -> T

    # Bulk
    def add_all(self, objs: Iterable[T]) -> None
    def delete_all(self, objs: Iterable[T]) -> None
```

### Enhanced Methods (Add to BaseRepository)

These methods eliminate the most common boilerplate across repositories:

```python
def get_with_filter(self, id_: Any, **filters: Any) -> Optional[T]:
    """Get by primary key with additional filters (e.g., account_id for tenancy)."""
    stmt = select(self.model).where(self.model.id == id_)
    for key, value in filters.items():
        stmt = stmt.where(getattr(self.model, key) == value)
    return self.db.scalar(stmt)

def list_by(self, **filters: Any) -> list[T]:
    """List all entities matching exact filters."""
    stmt = select(self.model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(self.model, key) == value)
    return list(self.db.scalars(stmt).all())

def exists(self, **filters: Any) -> bool:
    """Check if any entity matches the given filters."""
    from sqlalchemy import exists as sa_exists
    conditions = [getattr(self.model, k) == v for k, v in filters.items()]
    stmt = select(sa_exists().where(*conditions))
    return self.db.scalar(stmt) or False

def count(self, **filters: Any) -> int:
    """Count entities matching filters."""
    from sqlalchemy import func
    stmt = select(func.count()).select_from(self.model)
    for key, value in filters.items():
        if value is not None:
            stmt = stmt.where(getattr(self.model, key) == value)
    return self.db.scalar(stmt) or 0
```

### Concrete Repository Template

```python
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.core.repository import BaseRepository
from .models import Item


class ItemRepository(BaseRepository[Item]):
    model = Item

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    # Domain-specific queries only — things BaseRepository can't do generically

    def get_for_account(self, item_id: uuid.UUID, account_id: uuid.UUID) -> Optional[Item]:
        """Get item verifying account ownership (multi-tenancy)."""
        return self.get_with_filter(item_id, account_id=account_id)

    def list_for_account(self, account_id: uuid.UUID) -> list[Item]:
        """List all items for an account."""
        return self.list_by(account_id=account_id)

    def get_with_relations(self, item_id: uuid.UUID) -> Optional[Item]:
        """Get item with eager-loaded relationships."""
        stmt = (
            select(Item)
            .where(Item.id == item_id)
            .options(joinedload(Item.account))
        )
        return self.db.scalar(stmt)
```

### Rules

| Rule | Detail |
|------|--------|
| Inheritance | Always `BaseRepository[Model]` with `model = Model` |
| Returns | `Optional[T]` for single, `list[T]` for multiple. Never dicts |
| Session | Stored as `self.db`, injected via constructor |
| Query style | SQLAlchemy 2.0: `select()`, `self.db.scalar()`, `self.db.scalars()` |
| Commits | **NEVER**. Service layer commits |
| Cross-repo calls | **NEVER**. Service orchestrates |
| HTTP exceptions | **NEVER**. Return `None`, let service/router handle |
| Method naming | `get_by_X` (single), `list_by_X` (multiple), `exists_by_X` (bool), `count_X` (int) |
| Eager loading | `joinedload()` for 1:1, `selectinload()` for 1:many |

---

## Layer 4: Service (`services.py`)

### BaseService Convention

```python
from typing import Generic, TypeVar, Optional, Any
from sqlalchemy.orm import Session
from backend.core.repository import BaseRepository
from backend.core.exceptions import EntityNotFound

T = TypeVar("T")  # ORM model type
R = TypeVar("R", bound=BaseRepository)  # Repository type


class BaseService(Generic[T, R]):
    """
    Base service providing standard CRUD operations.

    Convention:
    - Constructor takes db: Session, creates repository internally
    - Service layer owns transaction boundaries (commit/rollback)
    - Raises domain exceptions (EntityNotFound, ConflictError, etc.)
    - Never raises HTTPException
    - Returns ORM model objects
    """

    repository_class: type[R]

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo: R = self.repository_class(db)

    def get(self, id_: Any) -> Optional[T]:
        return self.repo.get(id_)

    def get_or_raise(self, id_: Any) -> T:
        obj = self.repo.get(id_)
        if obj is None:
            model_name = self.repo.model.__name__
            raise EntityNotFound(f"{model_name} not found", context={"id": str(id_)})
        return obj

    def list_all(self) -> list[T]:
        return self.repo.list_all()

    def create(self, obj: T) -> T:
        self.repo.add(obj)
        self.repo.commit()
        self.repo.refresh(obj)
        return obj

    def create_no_commit(self, obj: T) -> T:
        """Add without committing — for multi-entity orchestration."""
        self.repo.add(obj)
        self.repo.flush()
        return obj

    def update(self, obj: T, **fields: Any) -> T:
        self.repo.partial_update(obj, **fields)
        self.repo.commit()
        self.repo.refresh(obj)
        return obj

    def delete(self, obj: T) -> None:
        self.repo.delete(obj)
        self.repo.commit()

    def commit(self) -> None:
        self.repo.commit()

    def flush(self) -> None:
        self.repo.flush()
```

### Concrete Service Template

```python
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.core.exceptions import EntityNotFound, ConflictError
from .models import Item
from .schemas import ItemCreate, ItemUpdate
from .repository import ItemRepository


class ItemService(BaseService[Item, ItemRepository]):
    repository_class = ItemRepository

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    # --- Domain-specific methods ---

    def create_item(self, data: ItemCreate, account_id: uuid.UUID) -> Item:
        """Create item with business rule validation."""
        # Business rule: check for duplicates
        if self.repo.exists(name=data.name, account_id=account_id):
            raise ConflictError(f"Item '{data.name}' already exists in this account")

        item = Item(
            name=data.name,
            description=data.description,
            account_id=account_id,
        )
        return self.create(item)

    def update_item(
        self, item_id: uuid.UUID, account_id: uuid.UUID, data: ItemUpdate
    ) -> Item:
        """Update item with tenant verification."""
        item = self.repo.get_for_account(item_id, account_id)
        if item is None:
            raise EntityNotFound("Item not found")

        return self.update(item, **data.model_dump(exclude_unset=True))

    def delete_item(self, item_id: uuid.UUID, account_id: uuid.UUID) -> None:
        """Delete item with tenant verification."""
        item = self.repo.get_for_account(item_id, account_id)
        if item is None:
            raise EntityNotFound("Item not found")

        self.delete(item)
```

### Rules

| Rule | Detail |
|------|--------|
| Constructor | Always `def __init__(self, db: Session)`. Creates repo internally |
| Transaction | Service commits. Use `create_no_commit` + `flush` for multi-step, then `commit` once |
| Error handling | Raise domain exceptions: `EntityNotFound`, `ConflictError`, `BusinessValidationError` |
| HTTP exceptions | **NEVER**. That's the router/error handler's job |
| Returns | ORM model objects. Never dicts, never Pydantic schemas |
| Cross-service | Inject as parameter: `def signup(self, data, profile_svc: ProfileService)` |
| Lazy instantiation | **NEVER** import and create services inside methods |

### Multi-Step Orchestration Pattern

```python
def signup(self, data: SignupData, profile_svc: ProfileService) -> User:
    """Atomic multi-entity creation."""
    # Step 1: Create user (no commit)
    user = User(email=data.email, ...)
    self.repo.add(user)
    self.flush()  # Get user.id

    # Step 2: Create profile (no commit) — uses other service
    profile = profile_svc.create_no_commit(Profile(user_id=user.id, ...))

    # Step 3: Create account (no commit)
    account = Account(name=data.account_name)
    self.db.add(account)
    self.db.flush()

    # Step 4: Single commit (all-or-nothing)
    self.commit()
    return user
```

---

## Layer 5: Dependencies (`deps.py`)

### Standard Dependency Chain

```python
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from .repository import ItemRepository
from .services import ItemService


# Layer 1: Repository factory
def get_item_repo(db: Session = Depends(get_db)) -> ItemRepository:
    return ItemRepository(db)


# Layer 2: Service factory
def get_item_service(db: Session = Depends(get_db)) -> ItemService:
    return ItemService(db)
```

### Access Control Dependencies

For account-scoped resources, use the standard access control deps:

```python
from backend.accounts.deps import (
    require_account_access,      # Read access (any account member)
    require_account_owner,       # Write access (OWNER/CO-OWNER only)
    require_account_edit_access, # Edit access (owner + firm advisors)
)
```

### Rules

| Rule | Detail |
|------|--------|
| Pattern | `get_{entity}_repo` → `get_{entity}_service` chain |
| Session | Always from `Depends(get_db)` |
| No globals | **NEVER** instantiate services at module level |
| Access control | Use existing deps from `accounts/deps.py` or `firms/deps.py` |
| Custom deps | Create in module's `deps.py` only if needed |

---

## Layer 6: Router (`router.py`)

### Standard Router Template

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from backend.accounts.deps import require_account_access
from .deps import get_item_service
from .schemas import ItemCreate, ItemUpdate, ItemRead
from .services import ItemService

router = APIRouter(
    prefix="/accounts/{account_id}/items",
    tags=["items"],
)


@router.get("", response_model=list[ItemRead])
def list_items(
    account_id: uuid.UUID,
    account=Depends(require_account_access),
    service: ItemService = Depends(get_item_service),
):
    return service.repo.list_for_account(account_id)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(
    account_id: uuid.UUID,
    item_id: uuid.UUID,
    account=Depends(require_account_access),
    service: ItemService = Depends(get_item_service),
):
    item = service.repo.get_for_account(item_id, account_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(
    account_id: uuid.UUID,
    payload: ItemCreate,
    account=Depends(require_account_access),
    service: ItemService = Depends(get_item_service),
):
    return service.create_item(payload, account_id)


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(
    account_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ItemUpdate,
    account=Depends(require_account_access),
    service: ItemService = Depends(get_item_service),
):
    return service.update_item(item_id, account_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    account_id: uuid.UUID,
    item_id: uuid.UUID,
    account=Depends(require_account_owner),  # Destructive — require owner
    service: ItemService = Depends(get_item_service),
):
    service.delete_item(item_id, account_id)
```

### Rules

| Rule | Detail |
|------|--------|
| Thin layer | Only HTTP concerns: parse request, call service, return response |
| Business logic | **ZERO**. No if/else on business rules, no calculations, no helper functions |
| Dependencies | Inject service + access control via `Depends()` |
| Response models | Always specify `response_model` for type safety and OpenAPI docs |
| Status codes | GET=200, POST=201, PATCH=200, DELETE=204 |
| Error handling | Only `HTTPException` for 404 on missing resources. Domain errors handled by global handlers |
| Prefix | Account-scoped: `/accounts/{account_id}/items`. Top-level: `/items` |

---

## Exception Handling Strategy

### Exception Hierarchy

```python
# core/exceptions.py
class AppError(Exception):
    """Base for all application exceptions."""
    default_message = "An unexpected error occurred"
    def __init__(self, message=None, context=None): ...

class EntityNotFound(AppError):       # → 404
class ConflictError(AppError):        # → 409
class BusinessValidationError(AppError):  # → 422
class PermissionDenied(AppError):     # → 403
class AuthenticationError(AppError):  # → 401
class ExternalServiceError(AppError): # → 502
```

### Error Handler Registration

```python
# core/error_handlers.py — registered in main.py
app.add_exception_handler(EntityNotFound, handle_entity_not_found)
app.add_exception_handler(ConflictError, handle_conflict)
# ... etc
```

### Standard Error Response

```json
{
  "error": {
    "code": "entity_not_found",
    "message": "Item not found",
    "context": {"id": "abc-123", "account_id": "def-456"}
  }
}
```

### Who Raises What

| Layer | Raises | Never Raises |
|-------|--------|-------------|
| Repository | Nothing (returns `None` or empty list) | Any exception |
| Service | `EntityNotFound`, `ConflictError`, `BusinessValidationError` | `HTTPException` |
| Router | `HTTPException(404)` for simple not-found | Domain exceptions |
| Error handlers | Converts domain exceptions → HTTP responses | N/A |

---

## Registration Checklist

When adding a new module, register it in these files:

1. **Model import** in `main.py` — for SQLAlchemy table registration
2. **Router include** in `main_router.py` — for endpoint registration
3. **Alembic migration** — `alembic revision --autogenerate -m "Add items table"`

---

## Testing Pattern

```python
# tests/item_tests/test_item_service.py
import pytest
from backend.module_name.services import ItemService
from backend.module_name.models import Item

class TestItemService:
    def test_create_item(self, db_session):
        service = ItemService(db_session)
        item = service.create_item(ItemCreate(name="Test", account_id=account.id), account.id)
        assert item.name == "Test"
        assert item.id is not None

    def test_create_duplicate_raises_conflict(self, db_session):
        service = ItemService(db_session)
        service.create_item(ItemCreate(name="Test", account_id=account.id), account.id)
        with pytest.raises(ConflictError):
            service.create_item(ItemCreate(name="Test", account_id=account.id), account.id)
```

**Rules**:
- Test service layer (not router directly)
- Use SQLite in-memory for speed
- No PostgreSQL-specific features in tests
- Test business logic, not framework behavior

---

## Quick Reference: Layer Responsibilities

```
┌─────────────┬──────────────────────────────────┬──────────────────────────┐
│ Layer       │ Does                             │ Never Does               │
├─────────────┼──────────────────────────────────┼──────────────────────────┤
│ Model       │ Define columns, relationships    │ Business logic, queries  │
│ Schema      │ Validate input, shape output     │ Side effects             │
│ Repository  │ Query DB, return ORM objects      │ Commit, raise exceptions │
│ Service     │ Business logic, orchestrate, commit│ HTTP concerns          │
│ Deps        │ Wire repo→service, access control │ Business logic          │
│ Router      │ Parse HTTP, call service, respond │ Business logic, DB access│
└─────────────┴──────────────────────────────────┴──────────────────────────┘
```
