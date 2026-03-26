# Git Workflow Simulation Report

**Date**: 2026-03-14
**Purpose**: Validate the Contributing Policy against real scenarios from Buddy's git history and multi-agent parallel work patterns.

---

## Simulation 1: The Personal Probes Disaster (PRs #396-402)

### What Happened (Actual)
One branch `feature/personal-probes` was reused for 7 consecutive PRs over 2 hours:
- PR #396: feat: Add personal getting-to-know-you probes
- PR #397: fix: Add cache-busting for static assets
- PR #398: fix: Skip HSTS on LAN IPs
- PR #399: fix: Handle missing getUserMedia
- PR #400: fix: Make save_memory proactive
- PR #401: perf: Skip grid context scoring
- PR #402: fix: Don't filter single-word STT with digits

**Problems**: Can't revert one change without analyzing all 7. History shows 7 merges from same branch. Impossible to know which diff belongs to which PR.

### What Should Have Happened (Policy Applied)

```
Agent receives 7 independent tasks from backlog

Step 1: Check for file overlap
  - #396 touches: src/buddy/soul.md, src/buddy/capabilities/probes.py
  - #397 touches: src/buddy/static/index.html
  - #398 touches: src/buddy/middleware/security.py
  - #399 touches: src/buddy/static/js/voice.js
  - #400 touches: src/buddy/capabilities/memory.py
  - #401 touches: src/buddy/services/grid_retrieval.py
  - #402 touches: src/buddy/services/stt_filter.py
  → No overlap! All 7 can run in parallel.

Step 2: Create 7 branches from main
  feature/issue-396-personal-probes
  fix/issue-397-cache-busting
  fix/issue-398-hsts-lan
  fix/issue-399-get-user-media
  fix/issue-400-proactive-memory-save
  perf/issue-401-skip-grid-scoring
  fix/issue-402-stt-digit-filter

Step 3: 7 agents work in parallel (worktree isolation)
  Each agent: edit files → run checks → commit → push → create PR

Step 4: Merge queue processes PRs sequentially
  Each PR tested against main + all PRs ahead in queue
  Squash merged → clean linear history

Step 5: Result
  7 clean commits on main, each independently revertable
  Total time: ~30 minutes (parallel) vs ~2 hours (serial reuse)
```

### Verdict: PASS — Policy prevents the root cause (branch reuse) and enables faster parallel execution.

---

## Simulation 2: Audio Visualizer Churn (6 commits, full revert)

### What Happened (Actual)
```
0a61ee8 feat: Add audio visualizer to Now Playing bar
ba282b2 debug: Add logging to audio-analysis endpoint
cd78748 fix: Remove duplicate /v1 prefix in audio-analysis API path
d87e135 feat: Replace deprecated Audio Analysis API with procedural waveform
c01dd0a fix: Improve visualizer visibility and contrast
31a243e revert: Remove audio visualizer, restore clean Now Playing bar
```
6 commits for a feature that was ultimately removed. Debug commits shipped to main.

### What Should Have Happened (Policy Applied)

```
Step 1: Agent creates branch
  feature/issue-N-audio-visualizer

Step 2: Agent implements on branch
  - Discovers API deprecation during development
  - Fixes API path, switches to procedural waveform
  - Adjusts visibility/contrast
  - ALL of this happens on the branch, not main

Step 3: Agent runs checks on branch
  - Lint passes
  - Tests pass (or agent writes test for visualizer)
  - Manual test: visualizer looks acceptable

Step 4: Agent opens PR with single squashed commit
  "feat(ui): add audio visualizer to Now Playing bar"
  - PR body describes the approach (procedural waveform)
  - Debug logging removed before PR

Step 5: Review reveals concerns
  Option A: Fix on branch → re-push → re-review
  Option B: Close PR if feature not ready
  → Feature never ships broken to main

Step 6: If later reverted
  Single commit to revert: git revert <SHA>
  Clean, traceable, one line in history
```

### Verdict: PASS — Policy keeps experimental work off main. Debug commits never reach main. Revert is one commit, not 6.

---

## Simulation 3: WebRTC Config Flip-Flop (2-hour reversal)

### What Happened (Actual)
```
5b459fb chore: Default voice transport to WebRTC    (13:20)
76c94d0 chore: Revert voice transport to WebSocket  (15:36)
```

### What Should Have Happened (Policy Applied)

```
Step 1: Agent enters Plan Mode before implementing
  - Reads current transport config
  - Identifies the question: "Is WebRTC faster than WebSocket for voice?"
  - Runs latency analysis BEFORE coding:
    "STT is the bottleneck (1500ms), not transport (<10ms).
     WebRTC adds complexity without addressing the real latency source."
  - Conclusion: Don't switch to WebRTC

Step 2: Agent documents decision in plan
  "Transport is not the bottleneck. STT latency dominates.
   No change needed. Moving to next task."

Step 3: No commits. No flip-flop. No wasted effort.
```

### Verdict: PASS — Policy's "validate architecture decisions before coding" rule prevents the flip-flop entirely.

---

## Simulation 4: Parallel Agents on Buddy (3 agents, independent work)

### Scenario
Three agents work simultaneously:
- Agent A: Implement scam detection (security/scam_scanner.py, capabilities/safety.py)
- Agent B: Add hybrid retrieval with RRF (services/memory_retrieval.py)
- Agent C: Fix email boundary rule bug (services/email_boundaries.py, config/behavior.yaml)

### Simulation

```
T=0: Orchestrator assigns work
  ┌─ Check open PRs: gh pr list --state open → none
  ├─ File ownership:
  │   Agent A: security/scam_scanner.py (new), capabilities/safety.py
  │   Agent B: services/memory_retrieval.py
  │   Agent C: services/email_boundaries.py, config/behavior.yaml
  └─ No file overlap → safe to parallelize

T=0: All agents start (worktree isolation)
  Agent A: git worktree add ../buddy-A feature/issue-600-scam-detection origin/main
  Agent B: git worktree add ../buddy-B feature/issue-601-hybrid-retrieval origin/main
  Agent C: git worktree add ../buddy-C fix/issue-602-email-boundary-bug origin/main

T=30min: Agent C finishes first (small fix)
  1. ruff check . → pass
  2. pytest tests/test_email.py → pass
  3. git push -u origin fix/issue-602-email-boundary-bug
  4. gh pr create --title "fix(email): correct boundary rule priority ordering"
  5. CI passes → enters merge queue → squash merged to main

T=45min: Agent B finishes
  1. git fetch origin && git rebase origin/main → clean (no overlap with Agent C's files)
  2. ruff check . → pass
  3. pytest tests/test_memory.py → pass
  4. git push -u origin feature/issue-601-hybrid-retrieval
  5. gh pr create --title "feat(memory): add hybrid retrieval with RRF fusion"
  6. CI passes → merge queue → squash merged

T=90min: Agent A finishes (larger feature)
  1. git fetch origin && git rebase origin/main → clean (no overlap)
  2. ruff check . → pass
  3. pytest tests/test_security.py → pass
  4. git push -u origin feature/issue-600-scam-detection
  5. gh pr create --title "feat(security): add scam pattern detection for voice input"
  6. CI passes → merge queue → squash merged

T=90min: Result
  main has 3 new clean commits, independently revertable
  No merge conflicts, no coordination overhead
  All agents worked in parallel safely
```

### Verdict: PASS — Worktree isolation + file ownership + rebase-before-PR eliminates conflicts.

---

## Simulation 5: Parallel Agents with File Conflict

### Scenario
Two agents need to edit the same file:
- Agent A: Add scam detection to `capabilities/__init__.py` (register new capability)
- Agent B: Add weather alerts to `capabilities/__init__.py` (register new capability)

### Simulation

```
T=0: Orchestrator detects conflict
  Agent A files: capabilities/scam.py (new), capabilities/__init__.py
  Agent B files: capabilities/weather_alerts.py (new), capabilities/__init__.py
  → CONFLICT on capabilities/__init__.py

T=0: Orchestrator serializes
  Agent A starts first (higher priority issue)
  Agent B is queued, will start after Agent A's PR merges

T=30min: Agent A finishes
  1. Creates PR, CI passes, squash merged to main
  2. capabilities/__init__.py now has scam capability registered

T=30min: Agent B starts
  1. git checkout -b feature/issue-N-weather-alerts origin/main
     → Now has Agent A's changes in main
  2. Adds weather_alerts registration to capabilities/__init__.py
     → No conflict because it's working with the latest version
  3. Creates PR, CI passes, squash merged

T=60min: Result
  Both capabilities registered, no conflict, clean history
```

### Verdict: PASS — Serialization prevents conflicts on shared files. Small delay (30min) but zero rework.

---

## Simulation 6: CI Failure on Main (Emergency)

### Scenario
A PR passes CI individually but causes a test failure when merged with another PR that merged seconds before it.

### Simulation

```
T=0: PR #610 merges to main (changes auth middleware)
T=0: PR #611 merges to main (changes auth tests) — CI passed on PR branch
T=1: main CI fails — auth tests reference old middleware API

WITHOUT merge queue:
  main is broken. All agents must stop. Hotfix needed.

WITH merge queue (policy applied):
  T=0: PR #610 enters merge queue position 1
  T=0: PR #611 enters merge queue position 2
  T=5: PR #610 tested against main → passes → merged
  T=6: PR #611 tested against main + PR #610 → FAILS
  T=6: PR #611 is ejected from queue, author notified
  T=6: Agent rebases PR #611, fixes test, re-pushes
  T=10: PR #611 re-enters queue, tested against current main → passes → merged

  main NEVER broke.
```

### Verdict: PASS — Merge queue is the critical safeguard. Without it, main breaks. With it, the conflict is caught before merge.

---

## Simulation 7: Large Feature — Phased PRs

### Scenario
Implement "hybrid retrieval with RRF" — touches schema, service, retrieval pipeline, tests. ~600 lines total.

### Simulation

```
Phase 1: Schema (PR #620)
  Branch: feature/issue-601-phase-1-schema
  Changes: migrations/add_fts_index.sql, models/memory.py
  ~80 lines, schema-only, backward compatible
  → Merge to main

Phase 2: Service (PR #621)
  Branch: feature/issue-601-phase-2-service (from updated main)
  Changes: services/memory_retrieval.py, services/rrf.py (new)
  ~200 lines, new RRF fusion logic
  → Merge to main

Phase 3: Integration (PR #622)
  Branch: feature/issue-601-phase-3-integration (from updated main)
  Changes: capabilities/memory_search.py, config/defaults.yaml
  ~150 lines, wire RRF into search capability
  → Merge to main

Phase 4: Tests (PR #623)
  Branch: feature/issue-601-phase-4-tests (from updated main)
  Changes: tests/test_rrf.py, tests/test_memory_retrieval.py
  ~170 lines, comprehensive test coverage
  → Merge to main

Each phase:
  - Leaves main in working state
  - Is independently reviewable
  - Can be reverted without affecting other phases
  - Is small enough for confident review
```

### Verdict: PASS — 600-line feature broken into 4 digestible PRs. Each is under 200 lines. Main stays green throughout.

---

## Simulation 8: Spec → Issues → Parallel Implementation

### Scenario
New spec "Add safety features to Buddy" generates 4 issues:
- #630: Prompt injection scanner
- #631: PII scanner for stored content
- #632: Taint tracking for tool chains
- #633: Merkle-chained audit log

### Simulation

```
T=0: /spec-review generates 4 issues with dependency analysis
  #630: No dependencies (standalone scanner)
  #631: No dependencies (standalone scanner)
  #632: Depends on #630 and #631 (needs scanner output for taint labels)
  #633: No dependencies (standalone audit system)

T=0: Orchestrator plans parallel execution
  Wave 1 (parallel): #630, #631, #633 (no dependencies between them)
  Wave 2 (serial): #632 (after #630 and #631 merge)

T=0: Wave 1 launches 3 agents
  Agent A: feature/issue-630-injection-scanner → security/injection_scanner.py
  Agent B: feature/issue-631-pii-scanner → security/pii_scanner.py
  Agent C: feature/issue-633-audit-log → security/audit.py
  → No file overlap, safe to parallelize

T=60min: Wave 1 complete
  3 PRs created, CI passes, squash merged sequentially via merge queue

T=60min: Wave 2 launches 1 agent
  Agent D: feature/issue-632-taint-tracking → security/taint.py
  → Branches from main which now has #630 + #631 + #633
  → Can import injection_scanner and pii_scanner

T=120min: Wave 2 complete
  PR created, CI passes, squash merged

Result: 4 clean commits on main, all independently revertable
  Total elapsed: ~2 hours
  Total agent-hours: ~4 hours (but 3 ran in parallel)
```

### Verdict: PASS — Dependency-aware wave scheduling maximizes parallelism while respecting ordering constraints.

---

## Simulation 9: Documentation Update (Architecture Docs Drift)

### Scenario
After implementing hybrid retrieval (Simulation 7), the architecture docs at `docs/memory-system.md` are now stale — they describe pgvector-only retrieval but the codebase now has RRF fusion. An agent is tasked with updating docs.

### What Could Go Wrong (Without Policy)
```
Agent edits docs/memory-system.md directly on main          ← no PR
Includes a "while I'm here" refactor of config.py           ← mixed concerns
References a function that was renamed in a parallel PR      ← stale reference
Ships with broken internal links to removed sections         ← no link check
```

### Simulation (Policy Applied)

```
T=0: Agent creates docs branch
  git checkout -b docs/update-memory-architecture origin/main

T=5min: Agent reads current codebase to verify accuracy
  - Reads services/memory_retrieval.py → confirms RRF is implemented
  - Reads services/rrf.py → confirms function names and parameters
  - Reads config/defaults.yaml → confirms config keys for hybrid mode

T=15min: Agent updates docs/memory-system.md
  - Adds "Hybrid Retrieval" section describing RRF fusion
  - Updates architecture diagram
  - Adds config examples for enabling hybrid mode
  - References actual file paths: services/rrf.py:reciprocal_rank_fusion()

T=20min: Pre-PR checks (docs-specific)
  - [ ] All referenced file paths exist? → grep confirms
  - [ ] All function names current? → grep confirms
  - [ ] Internal links resolve? → section headers match
  - [ ] No code changes mixed in? → git diff --name-only shows only .md files
  - [ ] Dates are absolute, not relative? → "Implemented March 2026" not "last week"

T=22min: Create PR
  git commit -m "docs(memory): update architecture for hybrid RRF retrieval"
  gh pr create --title "docs(memory): update architecture for hybrid RRF retrieval"

T=25min: CI passes (docs don't break lint/tests), squash merged

Result:
  - Docs are accurate and match current codebase
  - No code changes mixed into docs PR
  - All references verified against actual source files
  - Clean single commit on main
```

### Verdict: PASS — Docs-only branch with accuracy verification against codebase prevents drift and stale references.

---

## Simulation 10: Spec Drafting with Multiple Review Rounds

### Scenario
Jason wants a spec for "Add safety features to Buddy." The spec needs exploration, drafting, human review, revision, and finalization before any code is written.

### What Could Go Wrong (Without Policy)
```
Spec written in Google Doc                    ← not version controlled
Implementation starts before spec is approved ← scope creep, rework
Spec references change during implementation  ← no single source of truth
Multiple agents read different versions       ← inconsistent implementations
Spec decisions not recorded                   ← same debates re-litigated later
```

### Simulation (Policy Applied)

```
T=0: Agent creates spec branch
  git checkout -b docs/spec-630-safety-features origin/main

T=0-30min: Drafting Phase
  Agent runs /spec-draft:
  - Explores codebase: reads current security (HMAC, OAuth, email boundaries)
  - Identifies gaps: no content scanning, no taint tracking, no audit trail
  - Writes docs/specs/spec-630-safety-features.md:
    - Problem statement
    - Proposed solution (4 components: injection, PII, taint, audit)
    - Alternatives considered (why not OpenJarvis's full scanner pipeline)
    - API contracts (scanner interface, audit event schema)
    - Data model (security_events table)
    - Decision log (empty, to be filled during review)
    - Success criteria

T=30min: Create draft PR
  git commit -m "docs(spec): draft safety features spec"
  git push -u origin docs/spec-630-safety-features
  gh pr create --title "docs(spec): safety features" --draft
  → Draft PR — signals "not ready for implementation"

T=1day: Review Round 1
  Jason reviews, leaves comments:
  - "Add scam detection as 5th component — critical for Buddy's elderly users"
  - "Taint tracking should integrate with existing capability policies"
  - "Decision: use regex-based scanning, not ML — keep it simple"

T=1day+30min: Agent addresses feedback
  - Adds scam detection section
  - Updates taint tracking to reference capability policies
  - Records decision in Decision Log:
    | 2026-03-14 | Regex-based scanning over ML | Lower complexity, no model deps |
    | 2026-03-14 | Add scam detection | Critical for elderly user safety |
  - git commit -m "docs(spec): address review — add scam detection, decision log"
  - git push

T=2days: Review Round 2
  Jason approves with minor wording changes.

T=2days+15min: Finalization
  Agent runs /spec-review:
  - Validates spec completeness
  - Generates 5 GitHub issues (#630-#634) with dependency graph
  - Final commit: "docs(spec): finalize safety features spec"
  - Marks PR as ready (undraft)
  - Squash merged → single clean commit on main

T=2days+15min: Implementation begins
  Issues #630-#634 are now ready for Use Cases 2-4 (code work)
  All agents read the spec from main — single source of truth
  If spec needs updating during implementation → separate docs/ PR

Result:
  - Spec is version-controlled on main
  - Review history preserved in PR comments
  - Decision log prevents re-litigating choices
  - Implementation doesn't start until spec is merged
  - All agents read the same spec from main
```

### Verdict: PASS — Draft PR workflow allows iterative review without polluting main. Spec-first prevents implementation rework.

---

## Simulation 11: Stale Branch Accumulation

### Scenario
After 50 PRs over 8 days, the Buddy repo has accumulated stale remote branches. `deleteBranchOnMerge` was false. Some branches were merged via squash (different SHA), so `git branch -r --merged` doesn't always catch them.

### What Happened (Actual — Buddy repo)
```
$ git branch -r | wc -l
→ 15+ remote branches still on origin after merging

$ git fetch --prune origin
→ Pruned 4 stale refs (already deleted on remote but local refs lingered)

$ git branch -r --merged origin/main | grep -v main
→ Some branches show as "not merged" because they were squash-merged
   (different SHA on main vs branch tip)
```

**Impact**: Cluttered branch list, confusing for agents checking `gh pr list`, wasted remote storage, risk of accidentally basing work on a stale branch instead of main.

### Simulation (Policy Applied)

```
Prevention Layer:
  - Repo setting: "Automatically delete head branches" = ✓
  - Every PR merge auto-deletes the remote branch
  - 90% of stale branches never exist

Post-Merge Layer (every agent, every time):
  $ git fetch --prune origin
  $ git branch -d feature/issue-N-slug
  → Remote ref pruned, local branch deleted
  → Zero accumulation per PR

Weekly Hygiene Layer (catches stragglers):
  # Find merged remote branches
  $ git branch -r --merged origin/main | grep -v 'main\|HEAD'
  → feature/old-experiment (merged 2 weeks ago, auto-delete wasn't on)
  → Delete: git push origin --delete old-experiment

  # Find local branches tracking deleted remotes
  $ git branch -vv | grep ': gone]'
  → feature/issue-397-cache-busting [origin/feature/issue-397: gone]
  → Delete: git branch -D feature/issue-397-cache-busting

  # Find unmerged branches older than 30 days
  $ git for-each-ref --sort=-committerdate refs/remotes/origin ...
  → 2026-02-01 origin/feature/issue-544-545-voice-pipeline-fixes
    → Already merged via squash (different SHA). Safe to delete.
  → 2026-01-15 origin/experiment/webrtc-test
    → Abandoned experiment. Close any open PR, then delete.

Result:
  - 0 stale branches on origin
  - 0 orphaned local branches
  - Clean branch list for agents to check before starting work
```

### Verdict: PASS — Three-layer defense (auto-delete + post-merge prune + weekly hygiene) prevents accumulation and cleans existing debt.

---

## Summary: Policy Coverage Matrix

| Scenario | Root Cause | Policy Rule That Prevents It | Simulation Result |
|----------|-----------|-------------------------------|-------------------|
| Branch reuse (7 PRs) | No branch-per-PR discipline | "One branch = one PR = one logical change" | PASS |
| Feature churn (add/revert) | Incomplete work merged to main | "Run checks on branch before PR" | PASS |
| Config flip-flop | Decision made without data | "Validate architecture before coding" | PASS |
| Parallel work (no conflict) | — | Worktree isolation + file ownership | PASS |
| Parallel work (file conflict) | Shared file editing | Serialization of conflicting agents | PASS |
| CI failure on main | Race condition between merges | Merge queue | PASS |
| Large feature | Mega-PR too big to review | Phased PRs, each < 200 lines | PASS |
| Spec → parallel implementation | Dependency ordering | Wave-based scheduling | PASS |
| Debug commits on main | No pre-merge cleanup | "Remove debug code before PR" | PASS |
| Multi-issue commits | Bundling unrelated work | "One issue per commit" | PASS |
| Docs drift after code change | No docs-specific workflow | "Docs-only branch, verify against codebase" | PASS |
| Spec iteration before implementation | Spec not version-controlled | "Draft PR, finalize before coding" | PASS |
| Stale branch accumulation | No auto-delete, no periodic cleanup | "Auto-delete + post-merge prune + weekly hygiene" | PASS |

**All 13 scenarios handled by the policy. Zero gaps identified.**

---

## Recommendations for Buddy Project (Immediate)

Based on these simulations, the Buddy project needs:

1. **Add CI** (Day 1): Create `.github/workflows/ci.yml` with ruff + pytest
2. **Enable branch protection** (Day 1): Require status checks, linear history
3. **Enable merge queue** (Day 1): Prevent semantic conflicts between concurrent merges
4. **Enable auto-delete branches** (Day 1): Stop stale branch accumulation
5. **Allow only squash merge** (Day 1): Disable merge commit and rebase options
6. **Add PR template** (Day 1): `.github/pull_request_template.md`
7. **Add `.pre-commit-config.yaml`** (Week 1): Shareable, version-controlled hooks

---

*This simulation validates the Contributing Policy against real failure scenarios from the Buddy project's git history and projected multi-agent workflows.*
