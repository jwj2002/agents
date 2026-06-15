---
name: grep-every-sql-site-before-dropping
type: feedback
summary: Before a spec/PR drops or renames a DB table or column, grep EVERY SQL site (incl. raw strings, ORMs, migrations) — API-surface greps miss direct callers.
durability: durable
---
Before locking any change that drops or renames a database table/column, run an
exhaustive grep for **every** SQL site — raw query strings, ORM models, migrations,
views, and direct-DB callers that bypass the API. API-surface greps alone miss the
callers that will break at runtime. Same lesson as auditing storage independently
of the API surface. See [[audit-storage-not-just-api]].
