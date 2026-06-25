---
paths: ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/backend/**", "**/frontend/**", "**/js/**"]
---

# Calculation Placement: backend owns derived values, frontend owns presentation

The line for any app with a backend + a UI. Not "move all calculations to the
backend" (that over-centralizes presentation and adds latency/coupling) — the
rule is a **distinction**.

## The rule

| Kind of calculation | Belongs | Examples |
|---|---|---|
| **Canonical / derived business value** — a number a user cites, acts on, exports, emails, or that must be identical across views/sessions/users/PDF | **Backend** (ETL / API / service) | scores, rankings, priority, risk/churn, lifetime/forecast values, tiers, any rate/ratio a decision rests on |
| **Presentation transform** — derived purely for *this render* | **Frontend** | number/locale formatting, sorting/filtering the already-fetched set, chart geometry, view-scoped "what's in this view" counts, show/hide, unit rescale for display |

## Why (production-worthy)

- **Single source of truth** — the same value must be byte-identical in every
  consumer (UI, another view, export, email, PDF). Client computation forces
  each consumer to re-derive → drift.
- **Determinism** — client values that normalize against "the fetched page"
  change with page size / who's looking. A ranked *call list* whose scores shift
  per session is a defect, not a style nit.
- **Testability / auditability** — a value users act on must be unit-testable
  and reproducible server-side.
- **Integrity** — business logic in an inspectable/tamperable client is not
  authoritative.
- **Reuse** — the first time the number is needed elsewhere (report, email),
  client-only computation forces duplication.

## The test for "canonical"

Ask: *would two users (or this user next week, or an export) need this number to
be the same?* Yes → backend. Is it only meaningful for the pixels on screen
right now? → frontend.

## Enforceable invariant

> **No canonical/derived value is computed in the frontend; the frontend only
> formats, charts, sorts, filters, and shows.**

A frontend that holds business arithmetic (weighted scores, log/normalization of
data fields, ratios a decision rests on) violates this. Pure formatting,
chart-axis math, and sorting the fetched set do not. A lint check that view code
contains no score/priority/weight arithmetic on data fields makes it mechanical.

## Anti-pattern guard (don't over-correct)

Do **not** push presentation to the backend: server-side number formatting,
round-tripping every interactive sort, or computing "what's visible in this
paginated view" server-side all degrade UX and couple presentation to the API.
Leave those on the client.

*Provenance: Hillsboro Hops 2026-06-25 — win-back priority was computed in the
browser, normalized against the fetched pool, so the same customer's "call-first"
score shifted with page size; not in any API, not testable. Surfaced while
designing the data-validation harness.*
