---
paths: ["**"]
---

# Core Failure Patterns (Always Loaded)

From the 2026 failure corpus (N=40, Jan–Jun 2026; regenerated 2026-06-09, #366).
Apply proactively.

| Pattern | Share | Trigger | Prevention |
|---------|-------|---------|------------|
| **VERIFICATION_GAP** | 27.5% (#1) | Any assumption about code structure, spec content, or data shape | Read the actual code — "resolved/unchanged" claims need a fresh read; new field → grep every consumer |
| **AMBIGUITY_UNRESOLVED** | 7.5% (#2) | Two valid interpretations; a noticed contradiction | Pick ONE, document it, flag the alternative |
| **ENUM_VALUE** / **COMPONENT_API** | 0 in 2026 (legacy; mechanically gated by E01 runner + /quick gate) | Fullstack enum/component work | Backend enum VALUE not NAME (`"CO-OWNER"` not `"CO_OWNER"`); read component source/PropTypes before reuse |

**Full patterns**: `~/.claude/memory/patterns-full.md` (per-cluster evidence;
regenerated alongside patterns-critical.md — load for COMPLEX issues)
