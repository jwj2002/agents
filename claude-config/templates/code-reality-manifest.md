---
purpose: "Fillable companion to a spec — captures verified code reality BEFORE drafting"
companion_to: "specs/<spec-name>.md"
filename_convention: "specs/<spec-name>.code-reality.md"
---

# Code-Reality Manifest — `<spec-name>`

**Verified as of:** YYYY-MM-DD against commit `<hash>`

This document is a **drafting precondition**, not a spec deliverable. Fill it in
BEFORE writing the spec. Every load-bearing claim the spec makes about existing
code must be backed by an entry here, copied verbatim from the actual file.

When the spec cites a function, table, enum, or constraint, the reviewer should
be able to look here first and confirm the claim against the manifest, rather
than re-tracing from scratch every round.

Rationale: see `~/.claude/rules/spec-review-workflow.md` §2 (Pre-V1.0 Code-Reality
Manifest). The owner_onboarding_v1 spec went through 8 review rounds in part
because V1.0 was written without one of these.

---

## 1. Functions cited

For every function the spec calls or claims to extend:

| Symbol | Path:Line | Signature (verbatim) | Pre-write guards / early returns | Notes |
|---|---|---|---|---|
| `add_edge` | `src/buddy/services/grid/crud.py:1007` | `async def add_edge(pool, source_id, target_id, relation_type, *, properties=..., strength=..., bidirectional=..., source=..., inferred_from=..., session_id=...)` | `:1076` self-loop guard returns early; `:1090` `find_relationship_conflict()` returns None on conflict BEFORE the SUPERSESSION delete at `:1211` | Onboarding cannot rely on SUPERSESSION_MAP — guard fires first |
| `_apply_update` | `src/buddy/services/extraction/grid_extractor.py:718` | `async def _apply_update(pool, fact_id, new_value, confidence) -> str \| None` | None — single UPDATE in a transaction | In-place UPDATE only (writes `previous_value` for audit); does NOT flip `is_active` or insert a new row |
| ... | | | | |

**Trace rule (from round-7 of the onboarding loop):** for any function you
cite, read **50+ lines around the cited line** — guards, branches, early
returns. Locating a symbol is not the same as tracing what reaches it.

---

## 2. Tables / columns cited

For every table the spec writes to or queries:

| Table | Source | Columns (relevant subset) | Unique / partial indexes | Notes |
|---|---|---|---|---|
| `grid_fact` | `scripts/init-db.sql:1609-1674` | `id, entity_id, layer, fact_key, fact_value, confidence, source, source_ref jsonb, is_active, superseded_by, superseded_at, previous_value, created_at, updated_at, updated_by` | Partial unique `idx_grid_fact_unique_single ON (entity_id, layer, fact_key) WHERE is_active=TRUE AND fact_key NOT IN (multi)`; partial unique `idx_grid_fact_unique_multi ON (entity_id, layer, fact_key, fact_value) WHERE is_active=TRUE AND fact_key IN ('sibling_of', 'children', 'parent', 'attendees', 'participants')` | Targetless `ON CONFLICT DO NOTHING RETURNING *` works against partial unique indexes |
| `grid_edge` | `scripts/init-db.sql:1685-1699` | `id, source_entity_id, target_entity_id, relation_type, properties jsonb, strength, source, inferred_from, session_id, created_at, updated_at` | UNIQUE `(source_entity_id, target_entity_id, relation_type)` unconditional | NO `is_active` column; supersession is HARD DELETE at `crud.py:1211` |
| ... | | | | |

---

## 3. Enums cited

For every enum value the spec uses:

| Enum | Path:Line | Values (verbatim) | Notes |
|---|---|---|---|
| `MaritalStatus` | `src/buddy/entities/enums.py:11-16` | `single, married, divorced, widowed, partnered, separated` | No `engaged` or `dating` — those need separate `relationship_status` fact |
| `RelationshipType` | `src/buddy/entities/relationships.py:?` | (paste full list) | See SUPERSESSION_MAP and CONFLICT_GROUPS below |
| ... | | | |

---

## 4. CHECK constraints cited

For every CHECK constraint the spec extends or relies on:

| Table.column | Path:Line | Current values | Notes |
|---|---|---|---|
| `grid_fact.source` | `scripts/init-db.sql:1666` | `('extracted', 'stated', 'inferred', 'probed', 'seeded')` | Add `'onboarding_owner'` via migration |
| `grid_edge.source` | `scripts/init-db.sql:1699` | `('stated', 'extracted', 'inferred', 'seeded')` | No `'probed'`; add `'onboarding_owner'` via migration |
| ... | | | |

---

## 5. Cross-module helpers / contracts

For helpers the spec invokes from a different module, or contracts that span
modules (e.g., a queue payload schema, a published event shape):

| Helper / Contract | Path | Shape | Notes |
|---|---|---|---|
| `resolve_or_create_entity` | `src/buddy/services/entity_merge.py:?` | `(pool, name, entity_type, ...) -> Entity` | Already fixed in PR #1453; bypasses `grid_write_queue` |
| `enqueue_grid_write` | `src/buddy/services/grid/write_queue.py:?` | `(payload, source, ...)` | NOT used by onboarding — synchronous writes only |
| `find_relationship_conflict` | `src/buddy/entities/relationships.py:101` | `(existing_types: set[str], new_type: str) -> str \| None` | Treats `{spouse_of, partner_of, ex_partner_of}` as mutually exclusive (CONFLICT_GROUPS at `:64`) — onboarding cannot transition between them via `add_edge` |
| ... | | | |

---

## 6. Migration provenance

For every column / constraint the spec claims is "already in production":

| Object | Owning migration | Path |
|---|---|---|
| `grid_fact.source_ref jsonb` | `20260513000800_memory_v1_schema_gaps.sql:39` | `db/migrations/` |
| `grid_edge.source_ref` | NOT YET PRESENT — this spec adds it | (new in V1) |
| ... | | |

---

## 7. Negative manifest (things that do NOT exist)

Explicitly list things that look like they should exist but don't. The
owner_onboarding loop's round 1 found V1.0 calling `add_fact()` which has
never existed. List confirmed non-existence to prevent future re-invention:

- `add_fact(pool, ...)` — NOT in `services/grid/crud.py`. Closest: `upsert_fact` at `:287`. Onboarding cannot use a function that doesn't exist.
- `bypass_vocabulary_review` parameter — NOT on `enqueue_grid_write`.
- `grid_edge.is_active` column — NOT in `init-db.sql`. Edges have no soft-delete state.
- `SUPERSESSION_MAP[EX_PARTNER_OF] = {PARTNER_OF}` — NOT present; only `{SPOUSE_OF}` is.
- ... etc.

---

## 8. Self-verification checklist (before submitting V1.0)

- [ ] Every function name in the spec is in §1 with verified signature
- [ ] Every table.column reference is in §2 with verified shape
- [ ] Every enum value is in §3 with verified existence
- [ ] Every CHECK constraint extension is in §4 with current values
- [ ] Every cross-module helper is in §5
- [ ] Every "already in production" claim is in §6 with the actual owning migration
- [ ] Section 7 explicitly lists what the spec considered but is NOT writing because it doesn't exist
- [ ] For any "operation X happens via Y" claim in the spec: I read the 50 lines around Y in §1, including guards/branches/early returns

If any box is unchecked, V1.0 is not ready for adversarial review.
