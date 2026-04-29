# PROVE Agent

**Version**: 1.5 | **Phase**: 4 | **Role**: Verifier + Outcome Recorder

PROVE is the final agent in the pipeline. It verifies that PATCH's implementation actually works, checks every acceptance criterion, records the outcome to structured data files, and classifies any failures by root cause. PROVE never fixes code -- it only reports.

## Artifact Validation

PROVE requires the PATCH artifact to exist:

```bash
ls .agents/outputs/patch-${ISSUE}-*.md
```

If the PATCH artifact is missing, PROVE stops with `BLOCKED: PATCH artifact not found`.

## Step 0: Select Applicable Behavioral Evals

Before running the verification levels, PROVE selects which behavioral evals apply to the change. The eval framework is defined in `rules/behavioral-evals.md` (E01-E15) and the file-pattern routing in `rules/eval-file-mapping.md`.

```bash
git diff --name-only origin/main
# Match each changed file against the eval-file-mapping table
# Collect the unique set of applicable eval IDs
```

| File Pattern | Applicable Evals |
|-------------|------------------|
| `*.tsx`, `*.ts` | E01 (ENUM_VALUE), E02 (COMPONENT_API), E03 (HOOK_DEPS), E15 (SECRETS) |
| `models/*.py`, `app/models/*.py` | E04, E05, E06, E08, E13, E15 |
| `schemas/*.py`, `app/schemas/*.py` | E01, E05, E06 |
| `alembic/versions/*.py` | E07, E08 |
| `services/*.py`, `app/services/*.py` | E09, E10, E12, E15 |
| `routers/*.py`, `app/routers/*.py` | E11, E12, E15 |
| `repositories/*.py`, `app/repositories/*.py` | E10, E13 |
| `Dockerfile`, `docker-compose.yml` | E14 |
| `*.py` (catch-all) | E15 |

If no files match any pattern, PROVE runs E15 (SECRETS) as a catch-all. Fullstack changes always add E01 (ENUM_VALUE). The `--thorough` flag forces all evals regardless of file mapping.

The selected evals run inline within the verification levels below: file-pattern checks (E01, E02, E03, E11, etc.) feed into Level 3 (WIRED); secret/migration checks (E15, E07) feed into Level 4 (FUNCTIONAL).

## Four Verification Levels

PROVE applies verification in layers, from basic existence checks through functional testing.

### Level 1: EXISTS

Verify every file listed in the PATCH artifact exists on disk.

```bash
for f in <files_from_patch>; do
  [ -f "$f" ] || echo "MISSING: $f"
done
```

**Fail condition**: Any file from the PATCH artifact is missing.

### Level 2: SUBSTANTIVE

Verify that no stubs, placeholders, or incomplete implementations remain in modified files.

=== "Backend checks"

    ```bash
    grep -rn "pass$\|return False$\|return \[\]$\|raise NotImplementedError" <files>
    grep -rn "TODO\|FIXME\|HACK\|PLACEHOLDER" <files>
    ```

=== "Frontend checks"

    ```bash
    grep -rn "onClick={() => {}}\|return null$" <files>
    grep -rn "TODO\|FIXME\|HACK\|PLACEHOLDER" <files>
    ```

**Fail condition**: Any stub, placeholder, or marker found in new or modified files.

### Level 3: WIRED

Verify that new code is actually integrated into the application, not sitting in isolated files.

Checks include:

- New components are imported somewhere
- New endpoints are called from the frontend
- New repositories are injected into services
- Enum values in frontend match backend VALUES (ENUM_VALUE check)
- Component prop usage matches actual API (COMPONENT_API check)

**Fail condition**: Isolated artifacts with no integration, or mismatched enum values or props.

### Level 4: FUNCTIONAL

Run the standard verification gates:

| Check | Command | Pass Criteria |
|-------|---------|---------------|
| Backend lint | `ruff check .` | No errors |
| Backend tests | `pytest -q` | All pass |
| Frontend lint | `npm run lint` | No errors |
| Frontend build | `npm run build` | Success |

## Focused Test Strategy

PROVE runs tests in two passes for fast feedback:

**Pass 1 -- Focused** (affected modules only):

```bash
MODULES=$(git diff --name-only HEAD~1 -- backend/ \
  | grep -oP 'backend/backend/\K[^/]+' | sort -u)
for mod in $MODULES; do
  pytest "backend/${mod}/tests/" -q
done
```

**Pass 2 -- Full suite** (safety net):

```bash
cd backend && pytest -q
cd frontend && npm run lint && npm run build
```

Both results are reported in the artifact:

!!! example "Verification level output"
    ```
    Level 1 EXISTS:       6/6 files found
    Level 2 SUBSTANTIVE:  0 stubs, 0 placeholders
    Level 3 WIRED:        All imports resolved, enum values aligned
    Level 4 FUNCTIONAL:
      Focused: backend/accounts/tests/ -- 12/12 passing (2.1s)
      Full suite: pytest -q -- 45/45 passing (8.3s)
    ```

!!! tip "When to Skip Focused Mode"
    Skip the focused pass for fullstack changes, refactoring, cross-module changes, or codebases with fewer than 50 total tests where the full suite is fast enough.

## Acceptance Criteria Checking

PROVE references the acceptance criteria from the MAP-PLAN or PLAN artifact and checks each one:

| Criterion | Status |
|-----------|--------|
| New endpoint returns 201 on success | PASS |
| Validation rejects empty email | PASS |
| Frontend form submits to correct URL | FAIL -- sends to /api/members instead of /api/accounts/{id}/members |

## Status Determination

| Condition | Status |
|-----------|--------|
| All gates pass, all criteria met | **PASS** |
| Any verification command fails | **BLOCKED** |
| Any acceptance criterion unmet | **BLOCKED** |
| Any pattern check fails (enum, component API) | **BLOCKED** |

## Outcome Recording

### On PASS

Append to `.claude/memory/metrics.jsonl`:

```json
{
  "issue": 184,
  "date": "2026-03-26",
  "status": "PASS",
  "complexity": "SIMPLE",
  "stack": "backend",
  "agents_run": ["MAP-PLAN", "PATCH", "PROVE"],
  "agent_versions": {"map-plan": "1.1", "patch": "1.5", "prove": "1.5"}
}
```

### On BLOCKED

Append to both `.claude/memory/failures.jsonl` and `.claude/memory/metrics.jsonl`:

**failures.jsonl** records the specific failure:

```json
{
  "issue": 184,
  "agent": "PATCH",
  "root_cause": "ENUM_VALUE",
  "details": "Frontend used CO_OWNER instead of CO-OWNER",
  "fix": "Changed string literal to match backend enum VALUE",
  "prevention": "MAP should document enum VALUES explicitly"
}
```

**metrics.jsonl** records the outcome:

```json
{
  "issue": 184,
  "status": "BLOCKED",
  "root_cause": "ENUM_VALUE",
  "blocking_agent": "PROVE"
}
```

These records feed the self-learning loop: `/learn` clusters failures by root cause, extracts prevention patterns, and updates agent definitions.

## Root Cause Classification

When recording a BLOCKED outcome, PROVE classifies the failure using one of 12 canonical root cause codes. The three most common are VERIFICATION_GAP (63%), ENUM_VALUE (26%), and COMPONENT_API (17%).

!!! tip "See also"
    For the full ENUM_VALUE pattern with code examples, see [Core Patterns -- ENUM_VALUE](../rules/core-patterns.md#enum_value-in-detail). For the complete 12-code taxonomy, see [Failure Patterns](../learning/failure-patterns.md#full-root-cause-taxonomy).

## PROVE-lite (Deprecated)

PROVE-lite was the lightweight variant for the TRIVIAL pipeline (Level 4 gates only). Since `/orchestrate` now rejects TRIVIAL classifications and redirects them to `/quick` (which has no PROVE phase), PROVE-lite no longer runs in the orchestrate pipeline. It remains in the agent definition for historical reference but is not invoked by any current workflow.

## When BLOCKED

PROVE includes four pieces of information when reporting a failure:

1. **Root cause classification** from the canonical enum
2. **Exact error output** from the failing command or check
3. **Unblock steps** describing what needs to change
4. **Prevention recommendation** for future runs

PROVE never attempts to fix the problem. It returns to the orchestrator with its findings.
