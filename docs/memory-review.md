<!-- memory-review v1 -->
# Claude Code Memory Review — 2026-06-08

**Scope:** project-tier fact memory on this machine. Counts and conventions only — no memory content.

## Verdict
Strong infrastructure (typed, indexed, hook-loaded, disciplined), but the store is **write-heavy and read-light** — working well as a *capture habit and archive*, under-working as *active recall*.

## System at a glance
| Metric | Value |
|---|---|
| Total facts | 119 (74 file-per-fact + 45 inline) |
| Projects with memory | 13 |
| Type mix | project 49 · feedback 16 · reference 8 · user 1 |
| Retrieval | passive (SessionStart index injection) |

## The decisive metric — recall
| Measure | Value |
|---|---|
| Writes / edits (60d) | 142 |
| Fact-body reads (60d) | 15 |
| Write : read ratio | ~9 : 1 |
| Sessions with any fact read | 6 of 28 (21%) |
| Cold facts (untouched 30d+) | 51% |

You're capturing ~9 facts for every one read back. The lessons are written but rarely re-consulted.

## Gaps
1. **Write-heavy / passive recall (biggest).** Index titles inject every session; fact bodies — where the "why" lives — are read ~1 session in 5.
2. **Mixed storage model.** Most projects use file-per-fact + index; `vaultiq-snow` (35) and `VE-RAG-System` (10) store facts inline in MEMORY.md.
3. **Dangling reference.** `core-patterns.md` points to `~/.claude/memory/patterns-full.md`, which doesn't exist.
4. **Index off-by-one** in `vaultiq-platform` (15 entries vs 14 files).
5. **Half the store is cold** (51% untouched 30+ days).

## Recommended corrections (NOT yet applied — review step is gated)
- **Promote durable `feedback` facts to content-injection** (like the learning-rules loop that already works) — highest leverage.
- **Get memory to the subagents** that do the work under `/orchestrate`.
- **Split durable vs perishable**; give session-state a TTL, keep `project` for durable constraints.
- **Migrate the 2 inline projects** to file-per-fact.
- **Mechanical fixes:** rebuild each MEMORY.md index to match files; fix the dangling reference; prune/archive cold facts.

## What works (keep)
Typed taxonomy, capture discipline, `[[slug]]` linking, project→global promotion, and the **learning-rules loop** (7 rules, cross-repo sourced, enforced at PROVE) — the model the fact store should follow.

*Corrections above are recommendations only; nothing in the memory store was modified to produce this review.*
