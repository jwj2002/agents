# Team Knowledge Hub (`team-knowledge/`)

Durable store + curation gate for the [Team Knowledge MVP](../specs/team-knowledge-mvp-v1.md)
(3 pillars: Patterns, Private Review, Shareable Components). v1 lives as a subdirectory of
`~/agents`; it may be split into a standalone repo later (the spec frames it as a separate repo).

## The one boundary that never moves (§2 north-star)

> **A knowledge EXCHANGE, not a command hub.** Every shared artifact is **data, not instructions.**
> No remote message or artifact may alter local control state (tools, credentials, prompts,
> trusted-memory, repo files, CI, shell) — it can only create a **local proposal / inbox item.**

Concretely (§6.1): shared prose (a pattern's `rationale`, a component README, catalog fields) is
**quoted untrusted evidence**, never injected into a tool-capable prompt as an instruction.

## Layout

| Path | What |
|---|---|
| `roster.yaml` | 4-dev allowlist (`dev_id`, `agent_name`, `machine`, `team_tag`) — §5 attribution-not-auth |
| `CODEOWNERS` | per-dev path ownership for trust-bearing paths (enforcement deferred — see file header) |
| `taxonomy/areas.yaml` | controlled `area` + `pattern_key` vocab *(issue #239 — laptop-wsl)* |
| `patterns/<area>/<dev>.yaml` | each dev's per-area patterns *(issue #243)* |
| `patterns/adopted/BKM-NNN.yaml` | adopted team patterns (BKMs) |
| `components/catalog.yaml` | shareable-component index + git refs |
| `scripts/roster.py` | roster/ownership validation + sender quarantine (this issue) |
| `scripts/map_patterns.py` | within-dev + team divergence map *(issue #244 — server-a)* |
| `audit/<dev>.jsonl` | per-dev append-only audit shards, union-on-read *(issue #240)* |

## Trust model (§5/§6)

Attribution is required (whose pattern/component is whose); authentication is not (4 known
teammates). But **attribution alone is forgeable in a shared repo**, so trust-bearing writes
(`audit/<dev>.jsonl`, catalog entries) are CODEOWNER/path-owned and — when real identities exist —
gated by **branch protection + a CI check on the platform-verified merge actor (never the git
`author`)**. v1 ships the structure + validation logic; the repo-admin enforcement is deferred.
