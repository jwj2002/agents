---
title: "Pattern Lifecycle — Extract, Validate, Promote"
status: draft
created: 2026-04-04
author: Jason Job
location: ~/agents/knowledge/
type: Process
version: v1.0
---

# Pattern Lifecycle

## Overview

Patterns cannot be created by copying files from a project. They must be extracted, generalized, reviewed, dry-run tested, piloted on real projects, and validated through consecutive zero-correction implementations.

## Lifecycle Stages

```
EXTRACT → DRAFT → PILOT → VALIDATED → DEPRECATED
```

| Stage | What Happens | Who | Exit Criteria |
|-------|-------------|-----|---------------|
| **EXTRACT** | Agent reads project, identifies all files involved, creates generic YAML | Analyzer + Extractor agents | YAML created with placeholders |
| **DRAFT** | Review team checks completeness, dry-run on blank project | Reviewer + Dry-run agents + Human | Dry-run passes + human approves |
| **PILOT** | Pattern used on next 3 real projects, corrections tracked | Project agents + Human review | 3 consecutive zero-correction implementations |
| **VALIDATED** | Pattern is proven. Agents use with high confidence. | Agents (autonomous or inform-only) | N/A — stays here unless deprecated |
| **DEPRECATED** | Better approach found, security issue, technology change | Human decision | Replacement pattern identified |

---

## Stage 1: EXTRACT

Human says: "Create JWT pattern from docketiq"

### Analyzer Agent

Reads all files related to the feature in the source project:
- Identifies every file involved (middleware, handlers, models, tests, config)
- Maps dependencies (packages, env vars, DB tables/migrations)
- Identifies project-specific code vs generic reusable logic
- Produces a file manifest with annotations

### Extractor Agent

Creates the generic YAML pattern:
- Strips project-specific references (table names, import paths, config values)
- Replaces with placeholders: `{project_name}`, `{user_model}`, `{secret_key_env}`
- Writes implementation section: key files, key decisions, setup steps, gotchas
- Writes test structure: what tests to include, what they validate
- Attaches generic reference code (rewritten to be standalone, not copy-paste)
- **Does NOT reference the source project in the pattern body** — only in lifecycle metadata

### Output

Pattern YAML saved to `~/agents/knowledge/patterns/` with `status: draft`.

---

## Stage 2: DRAFT → Review

### Pattern Reviewer Agent

Reads the YAML and checks:
- **Completeness**: Missing files? Missing tests? Missing env vars? Missing dependencies?
- **Genericity**: Any project-specific assumptions leaking? Hardcoded paths or names?
- **Decisions documented**: Are key decisions explained (why this approach, not just what)?
- **Gotchas listed**: Edge cases, common mistakes, things the agent will get wrong?
- **Test coverage**: Do the tests cover success, failure, edge cases?

Reports findings. If issues found → Extractor agent fixes.

### Dry-Run Agent

1. Scaffolds a blank project (`scaffold-project` or minimal FastAPI skeleton)
2. Reads ONLY the pattern YAML (does NOT read the source project)
3. Implements the pattern following the YAML instructions step by step
4. Runs the tests defined in the pattern
5. Reports: what worked, what failed, where the YAML was unclear

If the dry-run agent gets stuck → the pattern is incomplete. Fix the YAML.

### Human Review

Human reviews the dry-run output:
- Does the implementation look correct?
- Would you approve this PR on a real project?
- Any corrections → feed back to YAML, re-run dry-run

**Exit criteria:** Dry-run passes all tests + human approves the output.

**DRAFT → PILOT**

---

## Stage 3: PILOT → Real Use

Pattern is used on the next 3 real projects that need this feature.

### Tracking

Each pilot use is recorded in the pattern YAML:

```yaml
lifecycle:
  pilot_uses:
    - project: project-B
      date: "2026-04-08"
      corrections: 2
      correction_details:
        - "missed REFRESH_TOKEN_TTL env var in setup steps"
        - "test fixture assumed SQLite, pattern should specify DB-agnostic fixtures"
      yaml_updated: true
      result: partial_success

    - project: project-C
      date: "2026-04-15"
      corrections: 0
      result: success

    - project: project-D
      date: "2026-04-22"
      corrections: 0
      result: success
```

### Rules

- **Corrections found**: update the YAML, reset the consecutive success counter to 0
- **Zero corrections**: increment counter
- **3 consecutive zero-correction implementations → PILOT → VALIDATED**
- Each correction is documented: what was wrong, what was fixed, why

### Feedback Loop

After each pilot use:
1. Human reviews the PR (as they normally would)
2. If corrections needed: document what, fix the YAML, sync to git
3. If zero corrections: record success
4. Learning rules extracted from corrections (e.g., "always specify DB-agnostic test fixtures")

---

## Stage 4: VALIDATED

Pattern is proven through real-world use. 3 consecutive projects implemented it with zero human corrections.

### Agent Behavior with Validated Patterns

- Escalation level drops to 0-1 (autonomous or inform-only)
- Agent implements with confidence — doesn't ask "should I use this approach?"
- Standard review still applies (semantic review, not line-by-line)
- Any future correction → pattern goes back to PILOT, counter resets

### Ongoing Learning

Validated doesn't mean frozen. The learning loop continues:
- If a correction is needed on a future project → update YAML, drop back to PILOT
- If a better approach is discovered → create new pattern, deprecate this one
- Version history tracked in git (every YAML change is a commit)

---

## Stage 5: DEPRECATED

Human decides to deprecate when:
- Technology changes (e.g., framework dropped JWT support)
- Security vulnerability discovered in the approach
- Better pattern exists (new pat-<slug> replaces this one)
- Pattern is no longer relevant (no projects need this anymore)

```yaml
status: deprecated
lifecycle:
  deprecated_at: "2026-08-15"
  deprecated_reason: "Switched to Passport.js for multi-provider support"
  replaced_by: pat-fastapi-alembic-setup
```

**Deprecated patterns are never deleted.** Existing projects may still use them. Agents seeing a deprecated pattern in a project flag it: "This project uses deprecated pattern pat-auth-jwt. Recommended replacement: pat-fastapi-alembic-setup."

---

## YAML Schema with Lifecycle

```yaml
# patterns/auth-jwt.yaml
id: pat-auth-jwt
category: auth
name: "JWT with refresh tokens"
status: pilot                    # draft | pilot | validated | deprecated
tier: primary                    # primary | secondary | deprecated

lifecycle:
  extracted_from: docketiq       # source project (metadata only)
  extracted_at: "2026-04-04"
  extracted_by: jason-agent      # which agent/human created it
  
  draft_reviewed_at: "2026-04-05"
  draft_reviewer: reviewer-agent
  dry_run_passed_at: "2026-04-05"
  dry_run_project: test-scaffold-001
  
  pilot_started_at: "2026-04-06"
  pilot_uses:
    - project: project-B
      date: "2026-04-08"
      corrections: 2
      correction_details:
        - "missed REFRESH_TOKEN_TTL env var"
        - "test fixture assumed SQLite"
      yaml_updated: true
      result: partial_success
    - project: project-C
      date: "2026-04-15"
      corrections: 0
      result: success
    - project: project-D
      date: "2026-04-22"
      corrections: 0
      result: success
  consecutive_successes: 2       # resets to 0 on any correction
  
  validated_at: null             # set when consecutive_successes reaches 3
  deprecated_at: null
  deprecated_reason: null
  replaced_by: null

description: "Stateless authentication using JWT access tokens and refresh tokens"
when_to_use: "API-first services, stateless, multi-client"
when_not_to_use: "Server-rendered apps needing server-side session state"

implementation:
  language: python
  framework: FastAPI
  key_files:
    - "auth/jwt_handler.py — token creation, validation, refresh"
    - "auth/auth_middleware.py — request authentication dependency"
    - "auth/token_service.py — token storage and revocation"
  key_decisions:
    - "Access token TTL: 15 minutes (short for security)"
    - "Refresh token TTL: 7 days (balance between security and UX)"
    - "Token in httpOnly cookie, NOT localStorage (XSS protection)"
    - "Refresh token stored in DB, not just signed (enables revocation)"
    - "Refresh token rotation: issue new refresh on each use"
  setup_steps:
    - "pip install python-jose[cryptography] passlib[bcrypt]"
    - "Create auth/ module with jwt_handler.py, auth_middleware.py, token_service.py"
    - "Add {SECRET_KEY_ENV}, {ACCESS_TOKEN_TTL_ENV}, {REFRESH_TOKEN_TTL_ENV} to .env"
    - "Register auth_middleware as FastAPI dependency in main.py"
    - "Create users table with hashed_password column (if not exists)"
  gotchas:
    - "NEVER store tokens in localStorage — use httpOnly cookies"
    - "ALWAYS validate token signature AND expiry, not just decode"
    - "Refresh token rotation: issue new refresh on each use to limit window"
    - "Clock skew: add 30s tolerance on token expiry validation"
    - "Revocation check: always hit DB for refresh tokens, never trust signature alone"
  dependencies:
    - "python-jose[cryptography]"
    - "passlib[bcrypt]"
  test_structure:
    - "test_token_creation — verify token contains correct claims (sub, exp, iat)"
    - "test_token_expiry — verify expired token is rejected"
    - "test_refresh_flow — verify refresh returns new access + new refresh token"
    - "test_revocation — verify revoked refresh token is rejected"
    - "test_concurrent_sessions — verify multiple valid sessions per user"
    - "test_invalid_signature — verify tampered token is rejected"
  reference_code:
    note: "Generic reference code attached below. Not project-specific."
    files:
      - name: "jwt_handler.py"
        description: "Token creation and validation"
      - name: "auth_middleware.py"
        description: "FastAPI dependency for request authentication"
      - name: "token_service.py"
        description: "Refresh token storage, rotation, revocation"

related_decisions: []
validated_count: 0               # incremented on each successful implementation
created_at: "2026-04-04"
updated_at: "2026-04-04"
```

> Pattern IDs follow the `pat-<filename-stem>` slug format. The filename is the
> namespace — git enforces uniqueness by construction. An optional `legacy_id:
> PAT-NNN` field preserves traceability to pre-migration references. See
> issue #78 for the migration rationale.

---

## Agent Behavior by Pattern Status

| Status | Agent Behavior | Escalation Level |
|--------|---------------|-----------------|
| **DRAFT** | Agent flags: "This pattern is unvalidated (draft). Use only if explicitly directed." | Level 3 (consult human) |
| **PILOT** | Agent uses with awareness: "This pattern is in pilot (N/3 successes). Flagging for review." | Level 2 (approve) |
| **VALIDATED** | Agent uses with confidence. Standard review applies. | Level 0-1 (autonomous or inform) |
| **DEPRECATED** | Agent flags: "This project uses deprecated pattern pat-<slug>. Recommended replacement: pat-<slug>." | Level 2 (approve migration) |

---

## The Extraction Workflow (Detailed)

```
Human: "Create JWT auth pattern from docketiq"

STEP 1: ANALYZE (Analyzer Agent, -p one-shot)
  → Read docketiq/backend/auth/ directory
  → Read docketiq's CLAUDE.md for auth conventions
  → Read docketiq's tests/test_auth.py
  → Read docketiq's requirements.txt for auth dependencies
  → Read docketiq's .env.example for auth env vars
  → Read recent auth-related decisions from project knowledge base
  
  Output: manifest.yaml
    files: [jwt_handler.py, auth_middleware.py, token_service.py, ...]
    dependencies: [python-jose, passlib]
    env_vars: [AUTH_SECRET_KEY, ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL]
    db_tables: [users (hashed_password column), refresh_tokens]
    tests: [test_token_creation, test_token_expiry, test_refresh_flow, ...]
    project_specific: [docketiq User model import, docketiq config path]

STEP 2: EXTRACT (Extractor Agent, -p one-shot)
  → Read manifest.yaml
  → Read each source file
  → Rewrite as generic pattern:
    - Replace "from docketiq.models import User" → "{user_model_import}"
    - Replace "AUTH_SECRET_KEY" → "{SECRET_KEY_ENV}"
    - Replace docketiq-specific table names → generic names
    - Write setup steps
    - Write gotchas from decision history
    - Write test structure
  
  Output: patterns/auth-jwt.yaml (status: draft)

STEP 3: REVIEW (Reviewer Agent, -p one-shot)
  → Read auth-jwt.yaml
  → Check: all files listed? all env vars? all dependencies? all tests?
  → Check: any docketiq-specific references remaining?
  → Check: decisions documented with reasoning?
  
  Output: review-report.md (issues found or "approved")

STEP 4: DRY RUN (Dry-Run Agent, -p one-shot)
  → Scaffold blank FastAPI project
  → Read ONLY auth-jwt.yaml (not docketiq)
  → Implement step by step
  → Run tests
  
  Output: dry-run-result.md (pass/fail, issues encountered)

STEP 5: HUMAN REVIEW
  → Human reads dry-run output
  → Approves or sends back with corrections
  
  If approved: status: draft → pilot
```

---

## Integration with vitalai-channels

The pattern lifecycle is tracked in the developer knowledge base (`~/agents/knowledge/`). The vitalai-channels platform can optionally display pattern status via the developer KB proxy:

- Dashboard shows pattern status badges (DRAFT/PILOT/VALIDATED/DEPRECATED)
- Promotion from project → developer KB creates patterns as DRAFT
- Pilot tracking happens in the YAML lifecycle field
- vitalai-channels does NOT implement the extraction/review/dry-run workflow — that's agent orchestration work driven by the human

---

## Impact on Knowledge Base Schema

### YAML Schema Changes

Add `status` and `lifecycle` to pattern YAML (shown above).

### SQLite Schema Changes (knowledge.db)

```sql
-- Add to patterns table
ALTER TABLE patterns ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'pilot', 'validated', 'deprecated'));
ALTER TABLE patterns ADD COLUMN lifecycle TEXT;  -- JSON blob of lifecycle data
ALTER TABLE patterns ADD COLUMN consecutive_successes INTEGER DEFAULT 0;
```

### Knowledge MCP Tool Changes

`get_patterns` and `get_standard_patterns` should return the `status` field. Agents should be aware of pattern maturity when deciding how to use it.

---

## Success Metric

**The pattern lifecycle is working when:**

A validated pattern (3 consecutive zero-correction implementations) is used by a `-p` one-shot agent on a new project, and the resulting PR is merged without any human code changes. The human reviews the semantic diff, confirms it matches the pattern, and approves.

The human's role shifts from "check the code for bugs" to "confirm the pattern was applied correctly." That's the win.
