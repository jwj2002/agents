---
paths: ["**/specs/**", "**/.agents/**"]
---

# Spec New-Substrate Domain Sweep — 5 Questions Before R1

**When a spec proposes a NEW persistence substrate (sync, indexing,
queueing, cache, write-through layer), answer 5 domain-expertise
questions in the spec body BEFORE submitting V1.0 for adversarial
review.**

The code-reality manifest checks what EXISTS. This rule checks what a
domain expert would say about your NEW substrate — gaps that the
manifest can't catch because the substrate didn't exist to manifest
against.

---

## When this rule fires

Your spec introduces ANY of:

| Substrate kind | Examples |
|---|---|
| **Sync** | Polling a remote system, delta tokens, history APIs, change-data-capture, eventual-consistency mirror |
| **Indexing** | Search index, embedding store, header-only mirror of remote content, cached projection |
| **Queueing** | Job queue, deferred task store, retry buffer, dead-letter queue |
| **Cache** | Read-through cache, write-through cache, TTL-bounded store |
| **Write-through** | Local write that must also write to a remote system, with rollback semantics |

If your spec's net-new schema is doing one of those things,
**answer the 5 questions in the spec body** before R1 review.

---

## The 5 questions

### Q1 — Deletion / move / rename model

For every upstream entity your substrate mirrors or projects: **what
happens when the upstream side deletes, moves, archives, renames, or
marks the entity?**

Your spec must answer:
- Do you propagate the delete (cascade tombstone)?
- Do you keep the local copy until next full sync?
- Do you mark `deleted_at` and continue showing in some views?
- What WS frame fires?
- What is the user experience — do search hits include or exclude
  recently-deleted entities?

**R1 finding this would have prevented:** W5 (Workspace V1 email_index
did not specify delete handling).

### Q2 — Cursor / state shape (row-level vs entity-level)

Where does sync cursor state live?

- **Row-level** (e.g., a column on each mirror row) — almost always
  wrong. Fails for empty entities, duplicates across rows, races on
  multi-row updates.
- **Entity-level** (e.g., one row per provider+account in a separate
  state table) — almost always right. Single writer per entity.
- **Process-level** (in-memory) — only valid for ephemeral
  substrates; bad on restart.

Your spec must:
1. State which level (row / entity / process).
2. If row-level: explain why this case is the exception (almost
   certainly you can't).
3. If entity-level: name the separate state table and its columns.

**R1 finding this would have prevented:** W4 (Workspace V1 put
`sync_state` on `email_index` row, should have been on a separate
`email_sync_state` table keyed by (provider, account)).

### Q3 — Identifier uniqueness scope

For every upstream identifier your substrate stores: **is the
identifier globally unique, or only locally unique within an
account/tenant/provider?**

Most provider IDs (Gmail message_id, Slack message_ts, Microsoft
Graph thread_id) are **per-account only**, not globally unique. If
your substrate has multiple accounts, the natural primary key MUST
include the account.

Your spec must declare:
- For each upstream ID, the uniqueness scope.
- The local primary key shape (composite vs surrogate).
- How the REST endpoint resolves identity (e.g.,
  `(provider, account, message_id)` not just `message_id`).

**R1 finding this would have prevented:** W6 (Workspace V1 email
thread endpoint took only `provider_thread_id`, would leak
cross-account data).

### Q4 — Derived-data classification (privacy / sensitivity)

For any data your substrate derives from upstream content (snippets,
embeddings, summaries, fingerprints, hashes): **what classification
applies?**

Default-to-public is unsafe. Default-to-sender-based is unsafe (misses
sensitive content from ordinary senders). Default-to-private with
escalation pathways is usually right.

Your spec must:
1. Name the classification levels (e.g., L0/L1/L2/L3 from privacy_class).
2. State the default for derived data.
3. State the escalation pathway (sender, keyword, manual override).
4. State whether derived data (snippets, embeddings) inherits the
   upstream entity's classification or is classified separately.
5. State retention semantics — does the substrate retain after the
   upstream deletes?

**R1 finding this would have prevented:** W8 (Workspace V1 email_index
classified only by sender; missed sensitive content from ordinary
senders + embeddings classified as derived without explicit policy).

### Q5 — Migration portability prerequisites

For every schema your substrate adds: **what extensions, types, and
operational prerequisites does it need across all deployment
environments?**

Your spec must declare:
- Required Postgres extensions (e.g., `vector`, `pgcrypto`,
  `pg_trgm`) and the migration's `CREATE EXTENSION IF NOT EXISTS`.
- Vector / type dimensions (e.g., 768d nomic, 1536d openai) and where
  the value comes from.
- Index creation constraints (e.g., `ivfflat` requires populated
  tables for sensible `lists` parameter — empty-table creation may
  warn or fail).
- Down-migration completeness (every UP statement has a corresponding
  DOWN statement OR an explicit "down-migration drops the column;
  data loss accepted" with rationale).
- Compatibility across deployment targets (local Docker pg vs
  Supabase pooler vs Supabase direct vs jbox06 pg).

**R1 finding this would have prevented:** W9 (Workspace V1 email_index
migration didn't specify `vector` extension, didn't address ivfflat
empty-table behavior, didn't define down-migration).

---

## How to apply

Add a `## §N — Domain Sweep` section to the spec, with subsections
for each of the 5 questions. ~200-400 words per question for a
typical substrate. Insert this section **between the substrate's
schema/design section and its Acceptance Criteria section.**

Example layout for an email-index spec:

```
## §9 Email Index (E3) — Backend Substrate
   §9.1 Goals
   §9.2 Schema
   §9.3 Sync Services
   §9.4 REST Endpoints
   §9.5 Frontend consumption
   §9.6 Privacy Gating

## §9a Domain Sweep — substrate completeness check  ← NEW
   §9a.1 Q1 Deletion / move / rename model
   §9a.2 Q2 Cursor / state shape
   §9a.3 Q3 Identifier uniqueness
   §9a.4 Q4 Derived-data classification
   §9a.5 Q5 Migration portability

## §10 Acceptance Criteria
```

For specs that propose MULTIPLE substrates, write one Domain Sweep
section per substrate.

---

## When to skip

- Your spec proposes no new persistence substrate (e.g., it only adds
  voice tools or UI components against existing tables). Skip the
  rule.
- Your spec extends an existing substrate that already has a Domain
  Sweep section in its V1 spec. Cross-reference instead of duplicating.
- Your spec is a project-private prototype with no deployment story.
  Skip with explicit one-line rationale.

A general "small change" is NOT a valid skip. The 2026-06-03 R1 email
substrate was framed as "just an index" — the 5 missed answers turned
a "small change" into 4 blockers.

---

## How this rule was born

**2026-06-03 Mavis Workspace V1 R1.** Four of 12 blocking findings on
Workspace V1 (W4, W5, W6, W8, W9) were all email-substrate domain
gaps. The spec proposed `email_index` + sync services without an
expert-domain sweep; each missed answer became a blocker.

Classified in
`~/projects/buddy/.agents/outputs/r1-root-cause-analysis.md` as
"Group D — process-absent." No existing global rule covered NEW
substrate domain sweeps; the code-reality manifest only checks what
EXISTS, not what a domain expert would have asked about a NEW thing.

This rule fills the gap. New global rule per Proposal 4 of
`r1-corrective-proposals.md`.

## Companion rules

- `~/.claude/rules/spec-self-review.md` — calls this rule out in Check 4
  (when the spec is UI/Fullstack; this rule generalizes the check to
  all NEW substrates regardless of UI involvement).
- `~/.claude/rules/spec-review-workflow.md` — overall spec workflow.
- `~/.claude/rules/spec-schema-collision-check.md` — Q5's migration
  portability check overlaps; that rule covers EXISTING-schema
  collisions, this one covers NEW-schema completeness.
- `~/.claude/templates/code-reality-manifest.md` — Q1 cross-refs the
  manifest's §7 Negative Manifest for "what's new vs what exists."
