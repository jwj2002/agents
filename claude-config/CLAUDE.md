# Jason's Claude Code Global Config

This file is your top-level orientation for every session. Detailed rules live
in `~/.claude/rules/` and are loaded conditionally — read this first.

---

## Who & where

- **User**: Jason Job (jasonwadejob@gmail.com)
- **Source of truth**: `~/agents/claude-config/` (version-controlled)
- **Deployed**: `~/.claude/` (symlinks from claude-config; see `install.sh`)
- **Sibling repos**: `~/agents/mcp-server/` (vault-metrics MCP), `~/agents/obsidian-agent/`, etc.

If you ever need to change the deployed config, edit `~/agents/claude-config/`
and let `install.sh` handle the symlinks. Don't edit `~/.claude/` directly.

---

## Three failure patterns to actively prevent

These three account for >50% of historical agent failures. Apply proactively.

| Pattern | Trigger | Prevention |
|---|---|---|
| **VERIFICATION_GAP** | Any assumption about code structure | Read the actual file. Never assume. |
| **ENUM_VALUE** (26%) | Fullstack work touching role/status/type fields | Use the backend enum **VALUE** string, not the Python NAME (`"CO-OWNER"` not `"CO_OWNER"`) |
| **COMPONENT_API** (17%) | Reusing an existing React component or hook | Read the source / PropTypes before invoking |

Full pattern detail: `~/.claude/rules/core-patterns.md` and any auto-loaded
`patterns-critical.md`.

---

## Routing: which workflow for which task

Before starting any task, classify it:

| Tier | Files | Signal | Use |
|---|---|---|---|
| TRIVIAL | 1 | Typo, rename, obvious fix | `/quick` |
| SIMPLE | 1–3 | Clear single-subsystem | Plan mode |
| MODERATE | 4–5 | Clear pattern, single subsystem | `/orchestrate` (SIMPLE tier) + Codex review |
| COMPLEX | 6+ | Cross-cutting / architectural | `/orchestrate` (COMPLEX tier) + Codex adversarial review |
| FULLSTACK | any | Backend + frontend | `/orchestrate` with CONTRACT phase |

**Modifiers:** `--parallel` for independent issues, `--resume` for interrupted
workflows, `--discuss` for ambiguous requirements (recommended on COMPLEX/FULLSTACK).

Full routing logic and Codex delegation patterns: `~/.claude/rules/implementation-routing.md`.

---

## Multi-environment routing

Three development modes in active use:

| Mode | Where code lives | How to edit | Git host |
|---|---|---|---|
| Local | `~/projects/<repo>` on laptop | Direct Edit/Write | GitHub |
| jbox06 (VitalAILabs) | `~/app-repos/<repo>` on jbox06 | `ssh jbox06 'cat > … << EOF …'` | Internal GitLab |
| Hybrid | both (rare) | Edit local, sync to jbox06 | GitLab via jbox06 |

Detect mode before writing code. Detail: `~/.claude/rules/dev-environment.md`.

---

## GitHub multi-account

Two accounts; switch before any git/gh work:

| Account | Used for | Email |
|---|---|---|
| `jwj2002` | Personal projects, agents repo | jasonwadejob@gmail.com |
| `jjob-spec` | Maison Financial projects | jason@maisonfinancial.com |

Run `gh auth status` first; switch with `gh auth switch -u <user>` if needed.
Detail: `~/.claude/rules/github-accounts.md`.

GitLab access (jbox06 only): `~/.claude/rules/gitlab-access.md`.

---

## Git workflow essentials

- Always branch from latest `origin/main`: `git fetch && git checkout -b {branch} origin/main`
- Naming: `{type}/issue-{N}-{slug}` (feature/, fix/, chore/, docs/, test/, perf/)
- One branch = one PR = one logical change
- Conventional Commits: `type(scope): description`
- Squash merge only
- Run lint/tests before opening PR
- Never `--no-verify` unless explicitly authorized

Full rules: `~/.claude/rules/git-workflow.md`.

Post-merge verification: `~/.claude/rules/post-merge-verification.md`.

---

## Behavioral evals (PROVE phase reference)

E01–E15 are run by PROVE based on changed files. The catalog
(`~/.claude/rules/behavioral-evals.md`) is authoritative; the highlights:

- **E01 ENUM_VALUE_MISMATCH** — frontend uses backend enum NAME instead of VALUE
- **E02 COMPONENT_API_MISMATCH** — reused component with wrong props
- **E03 HOOK_DEPENDENCY_ARRAY** — missing/incorrect `useEffect` deps
- **E04 MODEL_WITHOUT_MIGRATION** — SQLAlchemy change with no Alembic migration
- **E05 NULLABLE_MISMATCH** — model nullable doesn't match schema Optional
- **E06 SCHEMA_MODEL_DRIFT** — Pydantic schema fields don't match model
- **E07 MIGRATION_NOT_ADDITIVE** — destructive migration (drop/alter type)
- **E08 MIGRATION_MISSING_INDEX** — FK without index
- **E09 SERVICE_BYPASSES_REPO** — service uses raw `db.execute` instead of repo
- **E10 STALE_DATA_UNHANDLED** — flush without `StaleDataError` catch on versioned models
- **E11 AUTH_DEPENDENCY_MISSING** — endpoint without auth dependency
- **E12 AUDIT_LOG_MISSING** — write endpoint without `AuditService` call
- **E13 MISSING_FK_INDEX** — FK column without `index=True`
- **E14 DOCKER_ROOT_USER** — Dockerfile without `USER` directive
- **E15 SECRETS_IN_CODE** — hardcoded API keys, passwords, tokens

File→eval mapping: `~/.claude/rules/eval-file-mapping.md`.

---

## RBAC

Single-org applications use the permission-check dependency pattern:
`User.role` → `ROLE_PERMISSIONS` dict → `require_permission("resource:action")` dependency.
Every endpoint gets a permission check (E11). Detail: `~/.claude/rules/rbac-pattern.md`.

---

## Reference files (load on demand)

| Rule | Loaded for |
|---|---|
| `core-patterns.md` | Always (auto-injected by SessionStart hook) |
| `implementation-routing.md` | Any non-trivial task |
| `dev-environment.md` | Anything touching jbox06 or remote dev |
| `git-workflow.md` | Any commit/branch/PR work |
| `github-accounts.md` / `gitlab-access.md` | Before any push or auth-sensitive op |
| `behavioral-evals.md` + `eval-file-mapping.md` | PROVE phase, code review |
| `fastapi-layered-pattern.md` | `**/backend/**`, `**/api/**` paths only |
| `rbac-pattern.md` | Auth/permissions code |
| `orchestrate-workflow.md` | `/orchestrate` runs |
| `spec-review-workflow.md` | Specs and `.agents/` paths |
| `post-merge-verification.md` | After `/pr --merge` |

---

## Anti-patterns to avoid

- Long CLAUDE.md (target <200 lines; this file is the target).
- Reaching for a subagent before exhausting CLAUDE.md and skills (Anthropic's recommended order).
- Editing `~/.claude/` directly. Always go through `~/agents/claude-config/`.
- Putting secrets, ephemeral state, or large code patterns in CLAUDE.md.
- Bypassing safety with `--no-verify`, `--force`, or `bypassPermissions` without explicit user approval.
