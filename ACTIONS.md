# Actions — agents

Open and recently closed actions for this project.

**How to use**
- Add: append a row, next ID, status=open, fill owner/opened/source
- Update: edit in place (status, notes, closed date)
- Closed >30 days: move to Archive
- Refer as `A-NNN` in commits, PRs, chat, other docs

**Status:** `open` · `wip` · `blocked` · `done` · `cancelled`

## Sources

_(none yet)_

## Open

| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
|----|----|----|----|----|----|----|----|----|
| A-010 | #133 | Phase 6A — port /dashboard to Python CLI at ~/agents/dashboard/cli.py; /dashboard skill becomes thin wrapper; share ACTIONS.md parser with action CLI | Jason | open | 2026-05-07 | spec-toolchain-consolidation |  |  |
| A-011 |  | Phase 6B — audit all knowledge-mcp consumers (skills, plugins, anything in ~/agents/); per-tool decide port-to-CLI / keep / kill; output a follow-up plan | Jason | open | 2026-05-07 | spec-toolchain-consolidation |  |  |
| A-012 |  | Phase 6C — archive ~/agents/knowledge-mcp/, drop MCP registration from settings.json, update PLAN.md target architecture (gated on 6B) | Jason | open | 2026-05-07 | spec-toolchain-consolidation |  |  |
| A-013 |  | Phase 7 — investigate cross-device project state; evaluate git-as-sync vs SSH-based remote read vs centralized store; output decision doc at specs/cross-device-state.md (gated on 6A complete) | Jason | open | 2026-05-07 | spec-toolchain-consolidation |  |  |

## Recently Closed

| ID | Issue | Action | Owner | Closed | Files | Notes |
|----|----|----|----|----|----|----|
| A-001 |  | v2: MCP tool exposing ACTIONS.md to /dashboard at query time | Jason | 2026-05-06 |  | 2026-05-06: Obsolete: dashboard skill v6.0 reads ACTIONS.md directly per project (SKILL.md:163-203). No MCP tool needed. |
| A-002 |  | v2.5: cap-sync — GH issue create/mirror per A-NNN row | Jason | 2026-05-06 |  | 2026-05-06: Cancelled as scoped. Bidirectional ACTIONS.md<->GH issue sync is duplication for a single-user surface; precedent (Linear/Jira/org-mode) only justifies it when multiple humans live in different surfaces. Current design (Issue col blank, opt in to gh issue create when collaboration/CI matters) is correct. Multi-host (GH jwj2002 + jjob-spec + GitLab on jbox06) makes sync cost worse. |
| A-003 |  | v3: -e editor mode (open $EDITOR with template, parse rows) | Jason | 2026-05-06 |  | 2026-05-06: Cancelled as scoped under cap (v3 roadmap). README bin/README.md:86-99 remains the durable pointer. May be re-filed under the action CLI — see notes on A-004. |
| A-004 |  | v3: TODO comment scanner pulls TODO: markers into ACTIONS.md | Jason | 2026-05-06 |  | 2026-05-06: Cancelled as scoped under cap (v3 roadmap). TODO scanner has its own duplication tension (code TODO vs ACTIONS row); README bin/README.md:86-99 remains the pointer. |
| A-005 |  | v3: alternate capture surfaces (iOS Shortcut, voice, email) | Jason | 2026-05-06 |  | 2026-05-06: Cancelled as scoped under cap (v3 roadmap). Alt surfaces (iOS/voice/email) are infrastructure, not CLI features — the CLI can be a target but the interfaces live elsewhere. README bin/README.md:86-99 remains the pointer. |
| A-006 | #123 | Consolidate cap into action CLI: multi-row args, stdin, -e (editor template), -i (interactive loop); deprecate bin/cap to thin shim | Jason | 2026-05-06 |  | 2026-05-06: Shipped in #126 (commit 137fd62). cap consolidated into action --new with multi-row, stdin, -e, -i; bin/cap deleted. |
| A-007 | #124 | action --list: show metadata columns (Opened, Src, Issue, attachment count) by default; add --short for compact and --no-trunc for full Action text | Jason | 2026-05-06 |  | 2026-05-06: Shipped in #125 (commit 6cacbbb). action --list now wide tabular by default; --short and --no-trunc added. |
| A-008 | #129 | dashboard: subscriptions are authoritative — remove --all bypass; missing/empty subs file should error, not silently show everything | Jason | 2026-05-07 |  | 2026-05-07: Edge case (resolved 2026-05-07): when ~/.claude/dashboard-subscriptions.json is missing or has empty 'subscribed', error out with an instructive message pointing at /project NAME --subscribe. No silent fall-through to all-projects. Apply the same rule to multi-project /dashboard and to /dashboard --all (the --all flag should be removed). | 2026-05-07: Shipped in #130 (commit daeec0f). dashboard skill v6.0 → v6.1: subscriptions authoritative, --all removed, instructive error on missing/empty subs and on all-stale-subs. |
| A-009 |  | subscribe this machine to agents + buddy (and clean up _smoke_test_action leftover) in ~/.claude/dashboard-subscriptions.json | Jason | 2026-05-07 |  | 2026-05-07: Done 2026-05-07. ~/.claude/dashboard-subscriptions.json updated to {agents, buddy} on this laptop. _smoke_test_action leftover removed. /dashboard should now render with the authoritative-subs rule from #130. |

## Archive

_(none yet)_

---
Next ID: **A-014**
