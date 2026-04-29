# Sample Walkthrough: From Issue to PR

**A complete example showing every artifact the pipeline produces**

This walkthrough follows a single GitHub issue through the full orchestrate pipeline, showing each artifact along the way. The issue is simple enough to fit in a short read but realistic enough to demonstrate the system end-to-end.

## 1. The Issue

```markdown
## Add health check endpoint

Add a `GET /health` endpoint that returns server status (uptime, version,
database connectivity). Use the existing router pattern in `api/system.py`.

Labels: backend, enhancement
```

## 2. Running Orchestrate

```bash
/orchestrate 42
```

The orchestrator reads the issue, classifies it, and selects a pipeline:

```
Issue #42 classified as: SIMPLE (backend)
Using workflow: MAP-PLAN → PATCH → PROVE
```

No CONTRACT agent is needed because this is backend-only work.

## 3. MAP-PLAN Artifact

???+ example "Full MAP-PLAN artifact"

    **File**: `.agents/outputs/map-plan-42-033126.md`

    ```yaml
    ---
    issue: 42
    agent: MAP-PLAN
    date: 2026-03-31
    complexity: SIMPLE
    stack: backend
    files_identified: 2
    ---
    ```

    ```markdown
    ## Summary

    Add a GET /health endpoint returning server uptime, app version,
    and database connectivity status. The existing system router in
    api/system.py already handles /version, so health follows the
    same pattern. No schema changes or new dependencies required.

    ## Verification Steps

    - Read api/system.py: confirmed /version endpoint pattern (lines 12-28)
    - Read tests/test_system.py: confirmed test pattern for system endpoints
    - Approach: add to existing router, mirror /version structure

    ## Investigation

    ### Existing Pattern
    File: api/system.py:12-28 — GET /version returns {"version": "1.2.0"}
    Pattern: thin router function, no service layer needed

    ## Plan

    ### File: api/system.py
    - Add GET /health route to existing router
    - Return JSON: uptime_seconds, version, db_status ("ok" / "error")
    - Use existing db session dependency for connectivity check

    ### File: tests/test_system.py
    - Add test_health_returns_200 (happy path)
    - Add test_health_reports_db_status (verify db_status field)

    ## Acceptance Criteria

    - [ ] GET /health returns 200 with uptime_seconds, version, db_status
    - [ ] db_status is "ok" when database is reachable
    - [ ] Tests cover both the response shape and db_status field

    AGENT_RETURN: map-plan-42-033126.md
    ```

## 4. PATCH Artifact

???+ example "Full PATCH artifact"

    **File**: `.agents/outputs/patch-42-033126.md`

    ```yaml
    ---
    issue: 42
    agent: PATCH
    date: 2026-03-31
    status: Complete
    files_modified: 1
    files_created: 0
    tests_added: 2
    ---
    ```

    ```markdown
    ## Summary

    Implemented GET /health endpoint in the existing system router.
    Returns uptime_seconds (float), version (string), and db_status
    ("ok" or "error"). Added two tests covering the response shape
    and database status field. All gates pass.

    ## Files Changed

    ### api/system.py
    - Added health_check() route returning uptime, version, db_status
    - Uses existing db session dependency for connectivity probe

    ### tests/test_system.py
    - Added test_health_returns_200: asserts 200, checks all 3 fields
    - Added test_health_reports_db_status: asserts db_status is "ok"

    ## Verification

    ruff check . — PASS (0 errors)
    ruff format --check . — PASS
    pytest tests/test_system.py -q — 2/2 PASS (0.4s)
    pytest -q — 18/18 PASS (3.1s)

    AGENT_RETURN: patch-42-033126.md
    ```

## 5. PROVE Artifact

???+ example "Full PROVE artifact"

    **File**: `.agents/outputs/prove-42-033126.md`

    ```markdown
    ## Verification Levels

    | Level | Check | Result |
    |-------|-------|--------|
    | EXISTS | api/system.py, tests/test_system.py | PASS |
    | SUBSTANTIVE | No stubs, TODOs, or placeholders | PASS |
    | WIRED | /health route registered on system router | PASS |
    | FUNCTIONAL | ruff + pytest full suite | PASS |

    ## Acceptance Criteria

    | Criterion | Status |
    |-----------|--------|
    | GET /health returns 200 with uptime_seconds, version, db_status | PASS |
    | db_status is "ok" when database is reachable | PASS |
    | Tests cover response shape and db_status field | PASS |

    ## Outcome

    Status: PASS
    Recorded to: .claude/memory/metrics.jsonl

    AGENT_RETURN: prove-42-033126.md
    ```

## 6. The Result

The orchestrator reports the completed workflow:

```
Workflow complete for issue #42
Artifacts: map-plan-42-033126.md, patch-42-033126.md, prove-42-033126.md
PROVE status: PASS
Next: /pr 42
```

=== "SIMPLE (this example)"

    ```
    MAP-PLAN → PATCH → PROVE
    2 files, 3 artifacts, ~3 minutes
    ```

=== "COMPLEX"

    ```
    MAP → PLAN → CONTRACT → PLAN-CHECK → PATCH → PROVE
    6+ files, 6 artifacts, ~10 minutes
    Separate investigation and planning phases
    ```

## 7. What's in metrics.jsonl

PROVE appended this record to `.claude/memory/metrics.jsonl`:

```json
{"issue":42,"date":"2026-03-31","status":"PASS","complexity":"SIMPLE","stack":"backend","agents_run":["MAP-PLAN","PATCH","PROVE"],"agent_versions":{"map-plan":"1.0","patch":"1.2","prove":"1.3"}}
```

Over time, these records power the `/metrics` dashboard and the `/learn` pattern extraction loop.
