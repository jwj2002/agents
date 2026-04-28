---
case_id: 003
title: New SQLAlchemy column added without Alembic migration
source: SYNTHETIC — illustrative example, replace with a real PR
project: mymoney-dev
date_added: 2026-04-28
labels: [migration, schema, E04]
files_changed: 2
---

# New SQLAlchemy column added without Alembic migration

> **Synthetic case** — represents E04 MODEL_WITHOUT_MIGRATION. Easy to
> miss in dev (auto_create_tables masks it) but breaks staging/prod.

## Source

- PR: (synthetic)
- Project: mymoney-dev
- Linked rule: `behavioral-evals.md` E04 MODEL_WITHOUT_MIGRATION

## Issue / Context

> Add `archived_at` timestamp to `Account` for soft-archive support.

## Diff

```diff
# backend/backend/accounts/models.py
 class Account(Base, TimestampMixin):
     __tablename__ = "accounts"

     id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
     name: Mapped[str] = mapped_column(String(255))
+    archived_at: Mapped[datetime | None] = mapped_column(
+        DateTime(timezone=True), nullable=True
+    )

# backend/backend/accounts/services.py
 class AccountService:
     def archive(self, account_id: UUID) -> Account:
+        account = self.repo.get(account_id)
+        account.archived_at = datetime.now(UTC)
+        self.repo.commit()
+        return account
```

No file added under `backend/alembic/versions/`.

## Expected Findings

### CRITICAL

- [ ] **E04 MODEL_WITHOUT_MIGRATION**: `Account.archived_at` column added but no Alembic migration generated
  - Why CRITICAL: dev works (auto_create_tables); staging/prod will fail because schema doesn't match
  - Where: `backend/backend/accounts/models.py` (column add); `backend/alembic/versions/` (missing file)
  - Fix: `alembic revision --autogenerate -m "add account archived_at"` and commit the resulting file

### WARNING

- [ ] No test for `archive()` method
  - Where: `backend/tests/accounts_tests/test_services.py`
- [ ] `archive()` does not check whether account is already archived (idempotency)
  - Where: `backend/backend/accounts/services.py`

### SUGGESTION

- [ ] Consider adding an index on `archived_at` if "list non-archived" queries will be common
- [ ] Update API schema to expose `archived_at` if frontend needs it (not required for this PR)

## Known False-Positives

- "Use `func.now()` instead of `datetime.now(UTC)`" — both work; team prefers explicit Python datetimes for testability

## Notes

- Reviewers that are E04-aware should catch this immediately by diffing `models/*.py` against `alembic/versions/*.py`.
- A reviewer that catches the missing migration but misses the missing test for `archive()` is acceptable; the migration is the load-bearing finding.
