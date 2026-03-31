# Writing CLAUDE.md Files

Every project should have a `CLAUDE.md` at the root. This file is the primary instruction set for AI agents working in your codebase. It tells agents what the project is, how to build and test it, what patterns to follow, and what to never do.

## What to Include

A production-quality CLAUDE.md covers seven sections. Each section serves a specific purpose --- skip one and agents will guess (often wrong).

### 1. Project Overview

What the project is, who uses it, and what it is not.

```markdown
## Overview
Multi-tenant financial planning platform. Firm -> Advisor -> Client hierarchy.
Not a general-purpose accounting tool.
```

### 2. Development Commands

How to set up, run, test, and lint. Agents execute these commands directly, so they must be copy-paste accurate.

```markdown
## Development
cd backend && ruff check . && pytest -q          # Backend checks
cd frontend && npm run check                     # Frontend (format + lint + test + build)
```

### 3. Architecture

The layered pattern, module structure, and data flow. This must be actionable, not abstract.

```markdown
## Architecture
Layered: Router -> Service -> Repository -> DB
Module layout: models.py, schemas.py, repository.py, services.py, deps.py, router.py
```

### 4. Technology Stack

Versions and key dependencies. Agents use this to avoid deprecated APIs and version mismatches.

```markdown
## Stack
- Backend: FastAPI, SQLAlchemy 2.0, Pydantic v2, PostgreSQL
- Frontend: React 19, Vite, Tailwind CSS, React Query
```

### 5. Project Structure

Directory layout with descriptions. Mark directories that must not be reorganized.

```markdown
## Structure (IMMUTABLE -- do not reorganize)
backend/backend/    # Flat layout -- NEVER create backend/src/
frontend/src/       # React application
```

### 6. Forbidden Changes

Things agents must never do. Explicit prohibitions are the most effective entries in any CLAUDE.md.

```markdown
## Forbidden
- NEVER create src/, lib/, or pkg/ directories
- NEVER push to production branch without explicit request
- NEVER use PostgreSQL-specific syntax in tests (SQLite only)
```

### 7. Key Configuration

Environment variables, defaults, and test credentials.

```markdown
## Config
- DATABASE_URL defaults to sqlite:///test.db in tests
- JWT_SECRET must be set for auth endpoints
```

### Putting It All Together

Each of the seven sections above serves a distinct purpose. Omitting any one of them leaves a gap that agents will fill with guesses.

## The Template

A starter template is provided at `claude-config/project-template/CLAUDE.md`:

```markdown
# CLAUDE.md

## Project Overview
- Purpose:
- Users:
- Non-goals:

## Development Commands
# Setup / Run / Test / Lint

## Architecture Constraints
- Required patterns:
- Forbidden changes:
- Data/security constraints:

## Delivery Rules
- Definition of done:
- Required test coverage:
- Rollback expectations:
```

## Forbidden Patterns and Guardrails

The most effective CLAUDE.md entries are explicit prohibitions that prevent known failure modes:

| Guardrail | Prevents |
|-----------|----------|
| `NEVER create backend/src/` | STRUCTURE_VIOLATION --- agents reorganize if not told otherwise |
| `Always filter by account_id` | ACCESS_CONTROL --- multi-tenant data leaks |
| `Use require_account_owner from deps` | Inline permission checks with inconsistent enforcement |
| `Tests use SQLite in-memory only` | SQLITE_COMPAT --- PostgreSQL-only features breaking test suite |
| `Single source of truth: pyproject.toml` | Version drift from agents creating new version files |
| `NEVER push to production branch` | Accidental production deployments |

!!! warning "Agents Do Anything Not Explicitly Forbidden"
    AI agents will reorganize directories, create new configuration files, add dependencies, and push to protected branches unless you tell them not to. Every known failure mode should become an explicit prohibition in CLAUDE.md.

## Actionable vs Vague Documentation

Architecture documentation must be actionable --- it tells the agent exactly what pattern to follow.

**Good** (actionable):

```markdown
## Module Structure
module/
  models.py      # SQLAlchemy 2.0 (UUID PK, TimestampMixin)
  schemas.py     # Pydantic v2 (ConfigDict, from_attributes=True)
  repository.py  # Never commits -- service calls commit()
  services.py    # Business logic -- raises AppError, not HTTPException
  deps.py        # Access control via Depends()
  router.py      # Thin -- calls service, returns response
```

**Bad** (vague):

```markdown
We use a layered architecture with separation of concerns.
```

The good example gives the agent a concrete file-by-file reference. The bad example forces the agent to guess what "separation of concerns" means in your specific project.

## The "Read Before Assuming" Principle

This single principle prevents 63% of all agent failures. Encode it in your CLAUDE.md:

```markdown
## Critical Rule
Before using any existing component, hook, enum, or service:
1. Read the actual source file
2. Verify the API (props, return type, accepted values)
3. Never assume -- always confirm
```

This matters because AI agents have training data about common patterns, but your codebase has specific implementations that may differ. An agent "knows" that `useSession()` typically returns `{ session, loading }` --- but your hook might return the session directly.

## Per-Project Overrides

The global rules in `~/.claude/rules/` apply to all projects. Per-project rules live in the project repository:

```
~/projects/myapp/
  CLAUDE.md                          # Project-level instructions
  .claude/
    rules/
      project-rules.md               # Project-specific rules
    memory/
      patterns.md                    # Learned patterns for this project
      patterns-full.md               # Extended patterns (COMPLEX issues)
      metrics.jsonl                  # Issue outcome tracking
      failures.jsonl                 # Failure details
```

!!! tip "Layered Configuration"
    Global rules handle cross-cutting concerns (git workflow, failure patterns). Project CLAUDE.md handles project-specific architecture and conventions. Project rules handle project-specific implementation patterns. This layering avoids duplicating global guidance in every project.

## Maintenance

!!! tip "When to update your CLAUDE.md"
    - A new failure pattern emerges that is project-specific
    - The tech stack changes (new dependency versions, new tools)
    - The directory structure changes (new modules, renamed directories)
    - An agent makes a mistake that a CLAUDE.md entry would have prevented

Keep the file under 200 lines. If it grows beyond that, extract domain-specific sections into `.claude/rules/` as conditional rule files.
