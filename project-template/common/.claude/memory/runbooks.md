# Project Runbooks

Common issues and their fixes. Check here before investigating from scratch.

---

## R01: Alembic Revision Conflict
**Symptom**: `alembic upgrade head` fails with "Can't locate revision" or "Multiple heads"
**Cause**: Two branches created migrations from the same head
**Fix**: `alembic merge heads -m "merge"` then `alembic upgrade head`

## R02: WebSocket Connection Refused
**Symptom**: Frontend WS connects but immediately disconnects
**Cause**: Missing CORS origin or wrong WS endpoint path
**Fix**: Check CORS origins include the frontend URL. Verify the WebSocket route matches the frontend connection URL.

## R03: Pydantic Schema / SQLAlchemy Model Drift
**Symptom**: 422 validation error on API response
**Cause**: Model has a field that schema does not, or types diverge
**Fix**: Compare model fields vs schema fields side-by-side. Add missing fields. Fix type mismatches.

## R04: Docker Build Fails on pip install
**Symptom**: `pip install` fails during the Docker build with permission or network errors
**Cause**: Missing `--no-cache-dir` flag, or the base image changed upstream
**Fix**: Add `--no-cache-dir` to the pip install step. Pin the base image by digest in the Dockerfile so upstream changes can't break the build.

## R05: Optimistic Concurrency 500 (StaleDataError)
**Symptom**: 500 Internal Server Error on concurrent edits of the same row
**Cause**: `db.flush()`/`db.commit()` on a version-counter model without catching `StaleDataError` — two writers raced and the second lost the version check
**Fix**: Versioned-model updates must handle stale rows. Wrap the flush in `try/except sqlalchemy.orm.exc.StaleDataError` and convert to a conflict/retry path (HTTP 409), not a 500. Add a test that exercises concurrent updates to the same row.
**Eval**: Reinforces behavioral eval **E10 (STALE_DATA_UNHANDLED)** — a flush on a versioned model without a `StaleDataError` catch is the exact pattern E10 flags.

---

Add new runbooks as issues are discovered. Each entry needs: symptom, cause, fix.
