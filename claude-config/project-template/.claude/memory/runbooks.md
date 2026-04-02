# Project Runbooks

Common issues and their fixes. Check here BEFORE investigating from scratch.

---

## R01: Alembic Revision Conflict
**Symptom**: `alembic upgrade head` fails with "Can't locate revision" or "Multiple heads"
**Cause**: Two branches created migrations from the same head
**Fix**: `alembic merge heads -m "merge"` then `alembic upgrade head`

## R02: WebSocket Connection Refused
**Symptom**: Frontend WS connects but immediately disconnects
**Cause**: Missing CORS origin or wrong WS endpoint path
**Fix**: Check `app/core/middleware.py` CORS origins include the frontend URL. Verify WS route matches frontend connection URL.

## R03: Pydantic Schema / SQLAlchemy Model Drift
**Symptom**: 422 Validation Error on API response (field missing or wrong type)
**Cause**: Model has a field that schema doesn't, or types diverge (float vs Decimal)
**Fix**: Compare model fields vs schema fields side-by-side. Add missing fields. Fix type mismatches.

## R04: Docker Build Fails on pip install
**Symptom**: `pip install` fails during Docker build with permission or network errors
**Cause**: Missing `--no-cache-dir` flag, or base image changed upstream
**Fix**: Add `--no-cache-dir` to pip install. Pin the base image digest in Dockerfile.

## R05: Optimistic Concurrency 500 Error
**Symptom**: 500 Internal Server Error on concurrent edits (StaleDataError)
**Cause**: `db.flush()` without catching `StaleDataError` on versioned models
**Fix**: Wrap flush in `try/except orm_exc.StaleDataError` → convert to `ConflictError(409)`

---

_Add new runbooks as issues are discovered. Each entry needs: symptom, cause, fix._
