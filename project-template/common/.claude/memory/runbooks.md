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

---

Add new runbooks as issues are discovered. Each entry needs: symptom, cause, fix.
