---
paths: ["**/src/**", "**/app/**", "**/server/**"]
---

# No Application-Layer DDL — Migrations Are the Sole Source of Truth

**When application code runs `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, or `DROP TABLE/COLUMN/INDEX` outside of a migration file, REMOVE IT.**

The migration system is the canonical source of schema truth. Application code that performs idempotent DDL at startup or on connection acquire competes with migrations and produces an undetectable failure class: migrations drop something, application code immediately resurrects it. The next operator audit thinks the migration didn't apply when in fact it did — and was immediately undone.

---

## When this rule fires

Auto-loaded on any session touching `src/`, `app/`, or `server/` code. Triggers whenever you see one of these patterns in application code:

```python
# anti-pattern A — table bootstrap
await conn.execute("CREATE TABLE IF NOT EXISTS my_table (...)")

# anti-pattern B — column addition guard
await conn.execute("""
    DO $$ BEGIN
        ALTER TABLE my_table ADD COLUMN new_col TEXT;
    EXCEPTION WHEN duplicate_column THEN NULL;
    END $$
""")

# anti-pattern C — index assertion
await conn.execute("CREATE INDEX IF NOT EXISTS idx_my_table_x ON my_table(x)")

# anti-pattern D — application-side DROP
await conn.execute("DROP TABLE IF EXISTS deprecated_thing")
```

Even if the pattern looks defensive and idempotent, **remove it**. The migration system handles all three responsibilities.

---

## Why this is a distinct failure class

This rule generalizes a 2026-06-05 buddy incident (#1766): a migration
correctly dropped a column, but an `_ensure_schema()` block in application
code re-created it on every pool acquire — the subsequent schema audit
"found" the dropped column and wrongly blamed the migration. Incident
detail lives in buddy's project memory, not here.

This failure class is **invisible to schema-audit tooling**:
- `grep` for the dropped column in migration files — finds the DROP migration. Pattern looks complete.
- `\d <table>` in psql — column is there. Audit assumes the DROP migration didn't apply.
- `schema_migrations` table — DROP migration shows applied. Now you're confused.
- Only by reading application source code do you discover the resurrection.

The existing `~/.claude/rules/spec-schema-collision-check.md` Part 1 (SQL-site grep) catches in-code SQL **queries** against dropped tables. It does NOT catch in-code DDL **bootstrap blocks** that re-create dropped objects.

---

## The procedure

1. **Find every instance** in the codebase. Run:
   ```bash
   grep -rn --include='*.py' --include='*.ts' --include='*.go' \
       -E 'CREATE TABLE IF NOT EXISTS|ALTER TABLE.*ADD COLUMN|CREATE INDEX IF NOT EXISTS|DO \$\$' \
       src/ app/ server/ 2>/dev/null
   ```
2. **For each hit**, classify:
   - **Schema bootstrap** (creating tables/columns/indexes the app needs) → DELETE. Migrations already create these.
   - **Idempotent column add** (defensive add-if-missing) → DELETE. If the column exists in production, the migration that added it is authoritative.
   - **Defensive `DROP IF EXISTS`** in cleanup code → File as follow-up; needs explicit migration to drop.
   - **Test fixture setup** (only runs in test mode) → KEEP but isolate to test code, not production startup paths.
3. **Verify the schema lives in migrations.** For every table/index your application reads or writes, confirm `db/migrations/` (or equivalent) has a `CREATE TABLE` migration. If not, write the migration — don't restore the in-code DDL.
4. **Document the removal.** Comment at the deletion site referencing this rule and the migration that owns the schema:
   ```python
   # contact_notes is created + maintained by db/migrations/.
   # Per ~/.claude/rules/no-app-layer-ddl.md — never add CREATE TABLE
   # IF NOT EXISTS or ALTER TABLE ADD COLUMN here.
   ```

---

## What this rule allows

- **Migration files** under `db/migrations/`, `migrations/`, `alembic/versions/`, etc. — these ARE the source of truth.
- **Test fixtures** that set up + tear down ephemeral schemas (clearly isolated from production startup paths).
- **`SELECT to_regclass(...)` health checks** that verify expected schema is present without modifying it.
- **`pg_dump`/migration-tool calls** that operate on the schema as a whole, never on individual objects from application code.

---

## What this rule forbids

- `CREATE TABLE IF NOT EXISTS` in any production startup or connection-acquire path
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` or `DO $$ BEGIN ALTER ... EXCEPTION ... END $$`
- `CREATE INDEX IF NOT EXISTS` outside migrations
- `DROP TABLE/COLUMN/INDEX` from application code
- "Idempotent migration shims" embedded in service code (e.g., `_ensure_schema()` methods)

---

## Companion rules

- `~/.claude/rules/spec-schema-collision-check.md` — Part 1 (SQL-site grep for queries against dropped tables) — complementary to this rule. That rule catches queries that reference dropped objects; THIS rule catches code that re-creates them.
- `~/.claude/rules/spec-self-review.md` — Check 2 cross-refs spec ↔ migration. Extend with: also check application-layer DDL.
- Companion to buddy-local feedback: `~/.claude/projects/-Users-jasonjob-projects-buddy/memory/feedback_spec_grep_every_sql_site.md` (original 2026-05-24 incident — Part 1 SQL-site grep).
