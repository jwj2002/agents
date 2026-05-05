# Stack Comparison: VitalAILabs Scaffold vs. Preferred Stack

**Question:** which stack should I build a multi-user application with database operations on?

**Short answer:** the VitalAILabs scaffold and the preferred stack solve different problems. The scaffold is a **static-fixture demo / single-tenant edge app** framework. The preferred stack is a **production SaaS** framework. For any multi-user app with non-trivial database operations, build on the preferred stack. Reserve the scaffold for what it was designed for: small marketing-site demos and single-app edge-deployed tools.

---

## The two stacks side by side

| Concern | VitalAILabs scaffold | Preferred stack |
|---------|----------------------|-----------------|
| Backend framework | FastAPI, single `backend/routes.py` per app | FastAPI, layered (`models/`, `schemas/`, `repositories/`, `services/`, `routers/`, `tasks/`, `websocket/`) |
| Frontend | Self-contained `index.html` — vanilla JS/CSS, no build tools, no npm | React + Vite SPA, TypeScript, Tailwind, TanStack Query, React Router |
| Database | SQLite per app, raw `aiosqlite`, fixtures committed | PostgreSQL + pgvector, asyncpg, SQLAlchemy 2.x, Alembic migrations |
| Real-time | Polling (`setTimeout` + `fetch`) | WebSocket with cookie-scoped auth, per-user channels |
| Auth | None at app level — edge server handles it externally | Cookie JWT (HttpOnly), CSRF, RBAC, `token_version` revocation, audit log |
| State | File-based (`_STATE_DIR`), per-app SQLite | Centralized Postgres, optimistic locking via `version_id_col` |
| LLM integration | `claude -p` subprocess per call | Provider-adapter (anthropic/openai SDKs), prompt caching, streaming, embeddings via API |
| Deployment | Edge VM per customer; central platform mounts `apps/<slug>/<version>/` | Docker Compose + Caddy on Hetzner/cloud; Dockerfile + entrypoint + REVISION |
| CI / quality | GitLab CI: ruff + bandit + `ship-check.sh` + version-branch lock | GitHub: ruff + pytest + `npm run build` + behavioral evals (E01–E15) + `/orchestrate` pipeline |
| Repo / process | GitLab, `version/*` branches, MR gate, no session branches | GitHub, `feature/issue-N-slug`, squash-merge, main-stays-green |
| Designed for | Small internal tools, demo apps, single-tenant edge | Multi-tenant SaaS, knowledge-bearing apps, real-time products |

---

## Why this matters for multi-user apps

Multi-user means: concurrent reads and writes, identity, authorization, audit, recovery, and the operational surface that comes with all of it. Below is what changes between the two stacks at each layer.

### 1. Concurrent database access

**SQLite (scaffold).** SQLite serializes writes — the entire database file locks on every `INSERT`/`UPDATE`/`DELETE`. This is fine when "concurrent" means "two devs on staging." It is **not** fine when ten technicians submit service orders at the same time, or when a background worker writes audit rows while a user reads a list. Symptoms appear as `database is locked` errors and retry storms under modest load. WAL mode helps reads but does not change write serialization. There is no row-level locking, no read replicas, no connection pool to tune.

**Postgres (preferred).** MVCC, row-level locks, advisory locks, `SELECT ... FOR UPDATE`, true concurrent writes across tables, per-row optimistic locking via SQLAlchemy's `version_id_col`. Connection pooling via asyncpg + pgbouncer. Read replicas if you need them later. This is the floor for multi-user.

### 2. Schema evolution

**Scaffold.** No migrations. Schema lives in `init_db()` and you change it by editing the function. There is no record of what changed when, and no rollback. This is acceptable for an app that is wiped and reseeded between demos. It is **incompatible** with a production deployment where data must survive code changes.

**Preferred.** Alembic versioned migrations. Every schema change is a reviewable, reversible artifact. Behavioral evals (E04, E07, E08) enforce: model change → migration; migrations are additive; FKs get indexes. PROVE refuses to merge without these.

### 3. Identity, auth, RBAC

**Scaffold.** No auth model. The platform's edge server decides who reaches the app. Inside the app, all callers are anonymous and equivalent. There is no concept of users, roles, or audit. To bolt this on, you'd be building Postgres-style infrastructure (sessions, tokens, RBAC, audit) on top of SQLite — and you'd give up the simplicity that justified SQLite in the first place.

**Preferred.** Full identity stack: cookie-based JWT with HttpOnly + Secure + SameSite, CSRF on state-changing endpoints, `token_version` for revocation, RBAC dependencies (`require_auth`, `require_admin`, `require_csrf`), and an audit log table written through `AuditService`. Behavioral evals E11 (AUTH_MISSING) and E12 (AUDIT_MISSING) refuse to merge an endpoint that omits them.

### 4. Real-time updates

**Scaffold.** Polling every 2–10 seconds. With ten users this generates 1–5 requests/sec; with a hundred it overwhelms a single-process app and chews bandwidth on mobile. There is no per-user push, no notion of "this row changed, tell only the owner."

**Preferred.** WebSocket with the auth cookie validated on handshake, scoped by user. Server pushes only what the user needs (their alerts, their changed rows, their agent status). Order of magnitude lower latency, order of magnitude lower bandwidth at scale.

### 5. Vector / semantic search

**Scaffold.** SQLite has no native vector type. There are extensions (sqlite-vec) but they are bolt-on, single-process, and don't survive the scaffold's "one fixture file per app" philosophy.

**Preferred.** pgvector is built in. IVFFlat and HNSW indexes for approximate nearest neighbor. Vectors live in the same database as the relational rows that carry them, so semantic search joins to canonical data without a second store.

### 6. Multi-tenant isolation

**Scaffold.** "One app per customer per VM" *is* the isolation model. You spin up a VM per customer and copy the app there. This works for a small number of customers but does not give you a control plane: there is no fleet view, no cross-tenant analytics, no shared identity.

**Preferred.** Two valid patterns sit on top of Postgres:
- **Database-per-tenant**: one Postgres database (or schema) per Organization, app picks the connection at request time. Strong isolation; harder cross-tenant ops.
- **Row-level (RLS)**: one shared database with a `tenant_id` column on every table and Postgres Row-Level Security policies. Cheaper to operate; requires discipline.

Both exist in the preferred stack's vocabulary. Neither is reachable from SQLite.

### 7. Audit, soft-delete, history

**Scaffold.** None of these out of the box. You'd write them per app and carry the bug burden each time.

**Preferred.** Repo-layer enforcement: soft-delete (`deleted_at`) is a `BaseRepository` concern, audit calls go through `AuditService`, and behavioral evals (E09 SERVICE_BYPASSES_REPO, E10 STALE_DATA_UNHANDLED) catch the cases where a developer accidentally goes around the layer.

### 8. Operational surface

**Scaffold.** No backups, no point-in-time recovery, no observability beyond logs. The deployment story is "git push, freeze, release." That is appropriate for a marketing-site demo with no customer data.

**Preferred.** `pg_basebackup` + WAL streaming for PITR, structured JSON logs, healthcheck endpoints, `/orchestrate` post-merge verification, an observability stack (separate spec at `08-INFRASTRUCTURE.md` in Kova). All needed once a customer trusts you with their data.

---

## Where the scaffold *is* the right answer

The scaffold is not bad — it's correctly sized for its job:

- **Marketing-site demos.** A 7-day prototype on `vitalailabs.com/apps/<slug>/` to show a prospect a feature with seeded fixtures. SQLite + vanilla HTML is the right tool. React + Postgres is overkill.
- **Single-app internal tools.** A scratchpad app a small team uses where you can blow away the SQLite file and reseed.
- **Static-fixture previews of a larger product.** A "mini-DocketIQ" or "mini-Kova" tile published on the platform site. The real product lives elsewhere; the scaffold publishes a tour.

The trap is using it for a multi-user product. SQLite, no auth, polling, and no migrations are not warts to fix — they are deliberate constraints of the scaffold's contract. Trying to grow them turns into a half-rewritten product running on the wrong substrate.

---

## Recommendation

For any multi-user application with database operations — the kind we keep building (Channels, DocketIQ, Kova, the project agents platform) — **build on the preferred stack**:

```
FastAPI (layered)
  + PostgreSQL + pgvector + Alembic
  + React + Vite (TypeScript, Tailwind, TanStack Query)
  + WebSocket scoped per user (cookie auth on handshake)
  + Cookie JWT (HttpOnly) + CSRF + RBAC + audit
  + Docker Compose + Caddy on Hetzner/cloud
  + GitHub + ruff + pytest + behavioral evals + /orchestrate
```

This stack is what every project we ship has converged on. Vitalai-channels uses it, DocketIQ uses it, Kova v1 specifies it. Treat it as the **default**.

Use the scaffold when:
1. The app has one user (or no users — a marketing demo)
2. Data is seedable fixtures, not customer state
3. The app must publish under `vitalailabs.com/apps/<slug>/`
4. Lifetime is days/weeks, not years

Anything outside those four conditions belongs on the preferred stack.

### Pragmatic carry-overs from the scaffold

Even when you choose the preferred stack, three patterns from the scaffold are worth keeping:

1. **Brand CSS variable pattern** — clean white-labeling, useful for per-tenant theming.
2. **Health-check + startup-hook contract** — the scaffold's edge contract is a good shape for any container's `entrypoint.sh`.
3. **`ship-check.sh` discipline** — main-stays-green via a single script that runs before every PR. The preferred stack already has this in spirit (ruff + pytest + build + evals); keep treating it as a hard gate.

### What *not* to carry over

- SQLite — switch to Postgres on day one
- Vanilla HTML/JS frontend — switch to React + Vite on day one
- Polling — use WebSocket from the moment two users see the same data
- `claude -p` in production — keep it for dev; deploy with the SDK behind a provider adapter
- Edge VM deploy — only if a specific customer requires on-prem; otherwise Docker Compose on a managed VPS

---

## Decision rule

> If the app has authenticated users, persistent customer data, and more than one writer at a time → preferred stack.
>
> If the app is a fixture-driven demo or a single-tenant edge tool → scaffold.

Pick once, at the start. Migrating between them later is rarely worth it — the cost is closer to a rewrite than a port.
