---
paths: ["**/.agents/**", "**/backend/**", "**/frontend/**", "**/PROVE*.md"]
---

# Eval-to-File Mapping

PROVE uses this mapping to select which behavioral evals to run based on changed files.
Run `git diff --name-only origin/main` and match against the patterns below.

## Mapping Table

| File Pattern | Applicable Evals |
|-------------|-----------------|
| `*.tsx`, `*.ts` | E01 (ENUM_VALUE), E02 (COMPONENT_API), E03 (HOOK_DEPS), E15 (SECRETS) |
| `models/*.py`, `app/models/*.py` | E04 (MIGRATION_NEEDED), E05 (NULLABLE), E06 (SCHEMA_DRIFT), E08 (FK_INDEX), E13 (FK_INDEX), E15 (SECRETS) |
| `schemas/*.py`, `app/schemas/*.py` | E01 (ENUM_VALUE), E05 (NULLABLE), E06 (SCHEMA_DRIFT) |
| `alembic/versions/*.py` | E07 (MIGRATION_ADDITIVE), E08 (MIGRATION_INDEX) |
| `services/*.py`, `app/services/*.py` | E09 (REPO_BYPASS), E10 (STALE_DATA), E12 (AUDIT_MISSING), E15 (SECRETS) |
| `routers/*.py`, `app/routers/*.py` | E11 (AUTH_MISSING), E12 (AUDIT_MISSING), E15 (SECRETS) |
| `repositories/*.py`, `app/repositories/*.py` | E10 (STALE_DATA), E13 (FK_INDEX) |
| `Dockerfile`, `docker-compose.yml` | E14 (ROOT_USER) |
| `*.py` (catch-all) | E15 (SECRETS) |
| `*.env*` | E15 (SECRETS) |

## How PROVE Uses This

```
Step 0: Determine applicable evals
  1. Run: git diff --name-only origin/main
  2. For each changed file, match against patterns above
  3. Collect unique eval IDs
  4. Load those evals from behavioral-evals.md
  5. Run each applicable eval's "How to verify" checks

Step 1-4: Continue with standard verification levels
```

## Override Rules

- If NO files match any pattern: run only E15 (SECRETS) as a catch-all
- If the change is FULLSTACK (both backend + frontend): always add E01 (ENUM_VALUE)
- If `--thorough` flag is set: run ALL evals regardless of file mapping
