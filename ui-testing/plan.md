# UI Testing Framework — Master Plan

## Overview

Cross-project UI testing infrastructure. Developed against DocketIQ, designed for reuse across all FastAPI + React + PostgreSQL applications.

## Maturity Model

| Phase | Project | Mode | Goal |
|-------|---------|------|------|
| Phase 1 | DocketIQ | Manual → capture Playwright specs | Build framework, find issues, develop patterns |
| Phase 2 | Second project | Start with automated specs | Validate framework transfers, refine |
| Phase 3a | Third project | Automated + manual spot checks | Prove framework catches issues without full manual pass |
| Phase 3b | All projects | Full CI, review failures only | Steady state — manual testing is the exception |

## Architecture

```
~/agents/ui-testing/              # SHARED (agents repo)
├── plan.md                       # This file
├── templates/
│   ├── test-plan.md              # Template for per-project test plans
│   ├── test-run.md               # Template for daily test run results
│   └── issue.md                  # Template for tracked issues
├── fixtures/
│   └── auth.ts                   # Shared login/auth helper
├── helpers/
│   ├── screenshot.ts             # Screenshot + comparison utilities
│   └── navigation.ts             # Common navigation helpers
└── playwright.base.config.ts     # Base config (4 viewports)

<project>/frontend/e2e/           # PER-PROJECT (project repo)
├── tests/                        # Playwright spec files
│   ├── auth.spec.ts
│   ├── schedule.spec.ts
│   └── ...
├── fixtures/                     # Project-specific fixtures
│   └── seed.ts                   # Seed data setup/teardown
├── results/                      # Tracking (committed)
│   ├── ui-test-plan.md           # Test cases for this app
│   ├── test-runs/                # Daily run results
│   │   └── YYYY-MM-DD.md
│   └── issues/                   # Tracked failures
│       └── UI-NNN-description.md
└── playwright.config.ts          # Project config (extends base)
```

## Browser Coverage (4 viewports)

| Viewport | Device | Why |
|----------|--------|-----|
| Desktop Chrome | Chromium 1280x720 | Primary — office schedulers |
| Desktop Safari | WebKit 1280x720 | CSS/JS differences, Mac users |
| Mobile Chrome | Pixel 5 (393x851) | Android field workers |
| Mobile Safari | iPhone 13 (390x844) | iPhone field workers |

Automated tests run all 4. Manual tests focus on Chrome desktop with spot-checks on mobile.

## Test Data Strategy

- Clean seed before each test suite (B with guardrails)
- Tests that create/delete data clean up in `afterEach`
- Tests needing specific data create it in `beforeEach` fixtures
- Seed uses project's existing YAML templates

## Session Memory (3 layers)

| Layer | What | Where | Survives |
|-------|------|-------|----------|
| In-session state | Current test, pass/fail progress | `.agents/ui-test-state.yaml` (gitignored) | Context compaction |
| Test run results | Per-run pass/fail, issues found | `frontend/e2e/results/test-runs/` (committed) | Forever |
| Cross-session learnings | Patterns, decisions, infra notes | `.claude/memory/ui-testing.md` | Across conversations |

## Test Execution Flow

### Manual → Automated Progression

**Phase 1 (Manual):**
1. Agent navigates via Playwright MCP, takes screenshot
2. User directs interactions
3. Agent clicks/fills/navigates, screenshots at key points
4. On pass: capture steps as Playwright e2e spec

**Phase 2 (Semi-automated):**
1. Run captured Playwright spec
2. Show screenshots at assertion points
3. User confirms pass/fail

**Phase 3 (Fully automated):**
1. Playwright specs run in CI
2. Failures create GitHub issues with screenshots
3. User reviews only failures

## Pattern Decision Framework

When a UI issue is found, ask 4 questions:

| # | Question | Yes → | No → |
|---|----------|-------|------|
| 1 | Would this appear in a new project on this stack? | Global pattern candidate | App-specific at most |
| 2 | Would catching it early save >30 min debugging? | Worth capturing | Fix and move on |
| 3 | Can it be expressed as a verifiable check? | Strong pattern | Just a note |
| 4 | Does it overlap an existing pattern? | Merge into existing | New pattern if 1-3 pass |

**Outcomes:**
1. **Just fix it** — low recurrence, fast to diagnose
2. **Add to app runbook** — app-specific gotcha → `.claude/memory/runbooks.md`
3. **Create global pattern** — stack-level issue → MCP pattern server
4. **Create behavioral eval** — high-frequency, verifiable → `behavioral-evals.md`

**Anti-bloat:** Quarterly review — archive patterns not referenced in 90 days.

## jbox6 Vault Sync Setup

When development moves to jbox6:
1. Install obsidian-agent on jbox6 (already in agents repo)
2. Configure vault at `~/obsidian/WorkVault/` on jbox6
3. Init git repo in the vault: `cd ~/obsidian/WorkVault && git init`
4. Add remote pointing to a private repo or your local machine
5. obsidian-agent systemd timer writes test run summaries to vault
6. Pull vault to local Obsidian for viewing + Dataview queries

## Priority Order (DocketIQ)

| Priority | Area | Test Cases |
|----------|------|------------|
| P0 | Login + auth | Login, logout, token refresh, role access, protected routes |
| P1 | Schedule views + DnD | Day/week/month views, drag move, queue→schedule, unschedule |
| P2 | Job management | Create, read, update, delete, status transitions |
| P3 | Customer management | CRUD with addresses, search, pagination |
| P4 | Personnel + equipment + crews | Resource CRUD, assignment, skills |
| P5 | Admin settings + branding | App config, logo upload, branding |
| P6 | Notifications + audit | Notification list, mark read, audit log view |
| P7 | PDF reports + email | Report generation, email test |
