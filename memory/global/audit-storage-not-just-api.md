---
name: audit-storage-not-just-api
type: feedback
summary: When retiring/refactoring a system with an API and a backing store, grep the storage layer and direct-DB callers too — not just the API surface.
durability: durable
---
When auditing a system that has both an API surface and a backing store, grep for
**direct backend access** in addition to the API. Callers that hit the store
directly (raw `sqlite3.connect`, direct table reads) bypass the API and won't show
up in API-name greps — and they break silently when the store changes.
