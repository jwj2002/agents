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
| A-008 |  | dashboard: subscriptions are authoritative — remove --all bypass; missing/empty subs file should error, not silently show everything | Jason | open | 2026-05-07 | review-2026-05-07 |  |  |
| A-009 |  | subscribe this machine to agents + buddy (and clean up _smoke_test_action leftover) in ~/.claude/dashboard-subscriptions.json | Jason | open | 2026-05-07 | review-2026-05-07 |  |  |

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

## Archive

_(none yet)_

---
Next ID: **A-010**
