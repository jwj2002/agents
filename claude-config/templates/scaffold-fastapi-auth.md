# Scaffold FastAPI Auth — Module Template

Reference loaded by `/scaffold-project --with-auth` for Step 4 (auth module).

Generate a complete auth module under `backend/backend/auth/` following the layered pattern.

---

## `auth/enums.py`

```python
from enum import Enum

class SystemRole(str, Enum):
    ADMIN = "ADMIN"
    STANDARD = "STANDARD"
```

## `auth/models.py`

`User` model with: id (UUID), email (unique, indexed), hashed_password, name, is_active, system_role, date_joined, last_login.

## `auth/schemas.py`

- `UserCreate`: email, password, name
- `UserRead`: id, email, name, is_active, system_role, date_joined
- `LoginResponse`: access_token, token_type, user_id
- `TokenData`: email (from JWT sub claim)

## `auth/oauth2.py`

- `create_access_token(data, expires_delta)` — JWT with HS256
- `create_refresh_token(data)` — longer-lived JWT in httpOnly cookie
- `get_current_user(token)` — decode JWT, load user, return User
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")`

## `auth/repository.py`

- `UserRepository(BaseRepository[User])`
- `get_by_email(email)` — for login lookup
- `exists_by_email(email)` — for duplicate check

## `auth/services.py`

- `UserService` with: `authenticate_user`, `create_user`, `get_user_by_id`
- Raises `AuthenticationError`, `ConflictError`, `EntityNotFound`
- Never raises HTTPException

## `auth/deps.py`

- `get_user_repo(db)`, `get_user_service(db)`
- Re-export `get_current_user` from oauth2

## `auth/router.py`

- `POST /login` — OAuth2 password flow, returns access + refresh token
- `POST /signup` — Create user, auto-login
- `POST /auth/refresh` — Rotate refresh token from cookie
- `GET /users/me` — Current user profile

Register in `main.py` and `main_router.py`.
