---
description: Analyze failure patterns and update learned knowledge base
argument-hint: [--since YYYY-MM-DD] [--dry-run] [--verbose] [--apply] [--validate] [--cross-project]
---

# Learn Command

Analyzes accumulated failures and successes to extract patterns and update the knowledge base.

## Usage

```bash
/learn                      # Analyze all recorded outcomes
/learn --since 2025-01-01   # Analyze outcomes since date
/learn --dry-run            # Preview changes without updating files
/learn --verbose            # Show detailed analysis
/learn --apply              # Analyze + write prevention checklists into agent files
/learn --apply --dry-run    # Preview what --apply would write without modifying files
/learn --cross-project      # Aggregate patterns across all projects
/learn --validate           # Compare before/after success rates per pattern
```

---

## What This Command Does

0. **Pulls latest shards** and reads the watermark from `telemetry/_state.json`
1. **Loads outcome data** from `telemetry/*/failures.jsonl` (cross-machine union)
2. **Clusters failures** by root cause
3. **Calculates metrics** (success rates, trends)
4. **Extracts new patterns** from recurring failures
5. **Updates patterns-full.md** with learned knowledge
6. **Suggests agent updates** for high-frequency patterns
6.6. **Commits + auto-PRs** watermark + patterns (when `--apply`)
7.5. **Surfaces gate advisory** regardless of `--apply`

---

## Prerequisites

- `~/agents/telemetry/_state.json` exists (created by PATCH; zero-state epoch is fine)
- `~/agents/telemetry/` directory is committed to git (created by Stop hook on first failure)
- Git repository (for agent update suggestions and auto-PR)

---

## Process

### Step 0: Pull + Read Watermark + Materialize Union

**Always run first** — even on `--dry-run`.  Shards from other machines must
be present before counting or analyzing.

```bash
cd ~/agents

# 0a. Pull latest shards (fast-forward only — no merge commits on shards)
git pull --ff-only
# If diverged: STOP with message:
#   "Resolve git divergence before running /learn: git -C ~/agents pull --ff-only"

# 0b. Read watermark (last time /learn --apply succeeded)
LAST_LEARN_AT=$(python3 ~/agents/claude-config/scripts/telemetry_gate.py \
  --print-watermark 2>/dev/null || echo "2000-01-01T00:00:00Z")

# 0c. Count new failures across all host shards since watermark
NEW_COUNT=$(python3 ~/agents/claude-config/scripts/telemetry_gate.py \
  --count-only 2>/dev/null || echo 0)

echo "New failures since last learn: $NEW_COUNT (watermark: $LAST_LEARN_AT)"

# 0d. Materialize the cross-machine union into a temp file.
#     EVERY downstream step (Steps 1–6) reads UNION_FILE, never a local path.
#     The union is a snapshot: records added after this moment are NOT included,
#     so the watermark advanced at Step 6.6 precisely covers this snapshot.
TS=$(date -u +%Y%m%d-%H%M%S)
UNION_FILE="/tmp/learn-union-${TS}.jsonl"
# Concatenate all host shard failure files; normalize_record is handled by
# telemetry_gate's _iter_shard_records internals during counting.
# We cat the raw shards here; the clustering steps below parse JSON themselves.
cat ~/agents/telemetry/*/failures.jsonl 2>/dev/null > "$UNION_FILE"
echo "Union snapshot: $UNION_FILE ($(wc -l < "$UNION_FILE") lines)"

# 0e. Compute consumed_max from the union snapshot (B2 — used at Step 6.6).
CONSUMED_MAX=$(python3 ~/agents/claude-config/scripts/telemetry_gate.py \
  --compute-consumed-max 2>/dev/null || echo "")
```

### Step 1: Load Outcome Data

Read from the union snapshot materialized in Step 0 (`$UNION_FILE`).
**Never read `.claude/memory/failures.jsonl` directly for cross-machine learn** —
that file is a local aggregation, not the authoritative cross-machine union.
Apply a 90-day rolling window.

```bash
# Read from the Step 0 snapshot — ALWAYS use $UNION_FILE for failure clustering.
FAILURE_COUNT=$(grep -c '^{' "$UNION_FILE" 2>/dev/null || echo 0)

# 90-day window filter (use python for reliable cross-platform ISO comparison)
WINDOW_START=$(python3 -c "
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(days=90)
print(cutoff.strftime('%Y-%m-%dT%H:%M:%SZ'))
" 2>/dev/null || echo "1970-01-01T00:00:00Z")

# For metrics (success rate), read the merged global file (local dashboard)
METRIC_COUNT=$(wc -l < ~/.claude/memory/metrics.jsonl 2>/dev/null || echo 0)

echo "Loading outcomes..."
echo "  Failures (union snapshot, 90d window): $FAILURE_COUNT"
echo "  Metrics (local):  $METRIC_COUNT"
echo "  New since watermark: $NEW_COUNT"
```

If no data exists, report and exit:
```
No outcome data found. Run some issues through /orchestrate first.
```

### Step 2: Parse and Cluster Failures

Read each failure record from `$UNION_FILE` and group by `root_cause`.
**All jq/parse commands below operate on `$UNION_FILE`** (the snapshot from Step 0),
never on `.claude/memory/failures.jsonl` or any local path.

```bash
# Extract root causes and count — reads union snapshot
cat "$UNION_FILE" | \
  jq -r '.root_cause' | \
  sort | uniq -c | sort -rn
```

Expected output:
```
  12 ENUM_VALUE
   8 COMPONENT_API
   6 MULTI_MODEL
   4 ACCESS_CONTROL
   3 SQLITE_COMPAT
   2 OTHER
```

### Step 3: Analyze Each Cluster

For each root cause with 3+ occurrences:

#### 3a. Extract Common Attributes

```bash
# Find common files affected — reads union snapshot
cat "$UNION_FILE" | \
  jq -r 'select(.root_cause == "ENUM_VALUE") | .files[]' | \
  sort | uniq -c | sort -rn | head -5
```

#### 3b. Identify Trigger Conditions

Look for patterns in:
- Issue complexity (TRIVIAL/SIMPLE/COMPLEX)
- Stack (backend/frontend/fullstack)
- Affected domains (accounts, advisors, expenses)

#### 3c. Find Preventive Agent

Determine which agent SHOULD have caught this:
- MAP: Investigation gaps
- PLAN: Design gaps
- CONTRACT: API specification gaps
- PATCH: Implementation gaps
- PROVE: Verification gaps

### Step 4: Calculate Metrics

```bash
# Overall success rate
PASS=$(cat .claude/memory/metrics.jsonl | jq -r 'select(.status == "PASS")' | wc -l)
BLOCKED=$(cat .claude/memory/metrics.jsonl | jq -r 'select(.status == "BLOCKED")' | wc -l)
TOTAL=$((PASS + BLOCKED))
RATE=$((PASS * 100 / TOTAL))

echo "Success rate: ${RATE}% ($PASS/$TOTAL)"
```

Calculate by dimension:
- By complexity (TRIVIAL/SIMPLE/COMPLEX)
- By stack (backend/frontend/fullstack)
- By week (trend analysis)

### Step 5: Generate Updated patterns-full.md

Create new version of `.claude/memory/patterns-full.md`:

```markdown
# Learned Patterns

**Last updated**: $(date +%Y-%m-%d)
**Total issues analyzed**: $TOTAL
**Success rate**: ${RATE}%

## High-Frequency Failure Patterns

[For each cluster with 3+ occurrences, generate section]

### N. ROOT_CAUSE — Description

**Frequency**: X% of failures (N occurrences)
**Severity**: BLOCKED

**Pattern**: [Description extracted from failure details]

**Common files affected**:
- [file patterns from analysis]

**Trigger conditions**:
- [conditions extracted from analysis]

**Prevention checklist**:
- [ ] [Agent]: [Action]

**Responsible agents**: [List]
```

### Step 6: Identify Agent Update Candidates

For patterns by occurrence count:

- **≥5 occurrences** → eligible for `--apply` (auto-apply when flag is set)
- **2–4 occurrences** → surface as proposals in the summary; NEVER auto-applied
- **<2 occurrences** → mention in raw output only; no action

```markdown
## Suggested Agent Updates

### 1. MAP Agent — Add Enum VALUE Verification

**Reason**: ENUM_VALUE pattern occurred 12 times (26%)

**Suggested addition** to `.claude/agents/map.md`:

```markdown
### Enum Value Check (MANDATORY for fullstack)

If issue is fullstack and involves role/status/type fields:

1. Find enum definition:
   ```bash
   grep -r "class.*Enum" backend/backend/*/enums.py
   ```

2. Document VALUES explicitly:
   | Python Name | Python VALUE |
   |-------------|--------------|
   
3. Flag any NAME ≠ VALUE cases with ⚠️
```

**Impact**: Would have prevented 12 failures
```

### Step 6.5: Apply Updates (if `--apply`)

For each suggested agent update from Step 6:

1. **Read the target agent file** (resolve project-local first, then global):
   ```bash
   AGENT_FILE=".claude/agents/${AGENT}.md"
   [ ! -f "$AGENT_FILE" ] && AGENT_FILE="$HOME/.claude/agents/${AGENT}.md"
   ```

2. **Find insertion point**: After the "Pre-Flight" section, before the "Process" or "Implementation" section.

3. **Generate prevention checklist**:
   ```markdown
   ## Learned Prevention: {ROOT_CAUSE} ({count} failures)

   **Added by /learn --apply on {YYYY-MM-DD}**

   - [ ] {prevention action from failure records}
   - [ ] {second prevention if multiple failure details}
   ```

4. **Show diff to user**:
   ```
   === Proposed change to agents/{agent}.md ===
   + ## Learned Prevention: ENUM_VALUE (12 failures)
   + **Added by /learn --apply on 2026-03-25**
   + - [ ] Read backend enum definition BEFORE writing frontend code
   + - [ ] Document VALUE strings in MAP-PLAN artifact
   ```

5. **Apply changes** (occurrence-gated):
   - If `--dry-run`: Show diff only, do NOT write regardless of count
   - If occurrence count is **2–4**: Print proposal block only — do NOT write to agent file
     ```
     [PROPOSAL — 3 occurrences, needs ≥5 to auto-apply]
     Pattern: {ROOT_CAUSE}
     Suggested change: {agent file} — {description}
     Run /learn --apply again once count reaches 5+.
     ```
   - If occurrence count is **≥5** and `--apply` flag is set: Write changes,
     bump agent version (minor increment in YAML frontmatter)
   - Record application in `.claude/memory/pattern-events.jsonl`:
     ```json
     {"date":"YYYY-MM-DD","pattern":"ENUM_VALUE","action":"applied","target":"agents/map-plan.md","version_before":"1.0","version_after":"1.1","occurrences":12}
     ```

6. **After all updates applied**, report:
   ```
   Applied N agent updates:
     agents/map-plan.md (1.0 -> 1.1): Added ENUM_VALUE prevention
     agents/patch.md (1.2 -> 1.3): Added MULTI_MODEL prevention

   Review changes: git diff --stat
   ```

**Idempotency**: Before inserting, check if a `## Learned Prevention: {ROOT_CAUSE}` section already exists. If so, update the count and date rather than duplicating.

### Step 6.6: Branch + Commit Watermark + Auto-PR (only when `--apply` and NOT `--dry-run`)

After all pattern updates are written in Steps 6.5.  This step uses the
`$CONSUMED_MAX` computed in Step 0d (NOT wall-clock `now()`).

**Branch FIRST, then commit (M6)** — never commit on `main`.

1. **Create/switch to a learn branch from latest origin/main** (M6):
   ```bash
   cd ~/agents
   HOST=$(python3 -c "
   import sys; sys.path.insert(0,'$HOME/agents/lib')
   from project_resolver import get_host_name; print(get_host_name())
   " 2>/dev/null || hostname -s)
   TS=$(date -u +%Y%m%d-%H%M%S)
   BRANCH="learn/auto-${HOST}-${TS}"
   git fetch origin
   git checkout -b "$BRANCH" origin/main
   ```

2. **Re-apply pattern changes onto the new branch** (cherry-pick or re-write from
   the in-memory state — the branch is freshly cut from origin/main so the
   working tree starts clean):
   ```bash
   # Copy updated pattern files into the working tree (they were written to disk
   # in Step 6.5 but we are now on a fresh branch — git will see them as unstaged).
   # If Step 6.5 already wrote to the working tree, nothing more to do here.
   ```

3. **Write watermark atomically to consumed_max** (B2 + M7 monotonic):
   ```bash
   # $CONSUMED_MAX was set in Step 0e — it is the max recorded_at from the
   # union snapshot, never wall-clock now().
   if [ -n "$CONSUMED_MAX" ]; then
     python3 ~/agents/claude-config/scripts/telemetry_gate.py \
       --write-watermark "$CONSUMED_MAX" --host "$HOST"
     # Exit 0 = advanced; exit 2 = no-op (already at/beyond consumed_max — OK).
   fi
   ```

4. **Stage and commit** telemetry shard(s), watermark, and any agent file changes:
   ```bash
   git add telemetry/ claude-config/agents/ \
       .claude/memory/patterns-full.md \
       .claude/memory/pattern-events.jsonl 2>/dev/null || true
   git commit -m "learn: apply patterns + advance watermark to $CONSUMED_MAX"
   ```

5. **Auto-PR via /ship-style guarded merge** (reuse steps 4-8 of ship.md —
   do NOT reinvent; reference ship.md for the branch/push/PR/wait/merge sequence):
   ```bash
   git push --force-with-lease origin HEAD
   gh pr create \
     --title "learn: auto-apply patterns $(date -u +%Y-%m-%d)" \
     --body "Auto-generated by /learn --apply.
   Gate: $NEW_COUNT new failures since $LAST_LEARN_AT.
   Watermark advanced to: $CONSUMED_MAX (max consumed recorded_at — not wall-clock now).
   Host: $HOST"
   # Wait for CI, verify HEAD parity, squash merge (per ship.md §4-8)
   gh pr checks --watch
   gh pr merge --squash --delete-branch
   ```

6. **After merge: reset local main to origin/main**:
   ```bash
   git checkout main
   git pull --ff-only
   ```

**Monotonic watermark invariant (M7)**: `--write-watermark` calls
`write_watermark_monotonic()` which re-reads `_state.json` immediately before
writing.  If a concurrent `/learn --apply` on another machine merged and the
rebase pulled a newer watermark, the monotonic guard ensures we never move it
backward.

**Idempotency**: If a concurrent `/learn --apply` already merged (watermark advanced),
re-read `_state.json` from the working tree after rebase. If new count drops below
threshold, commit only the watermark update (no pattern changes — gate was already
satisfied by the first run).

**`--dry-run` guard**: Step 6.6 is completely skipped when `--dry-run` is set.
No watermark write, no commit, no PR.

### Step 7: Output Summary

```
═══════════════════════════════════════════════════════════
                    LEARNING COMPLETE
═══════════════════════════════════════════════════════════

Data analyzed:
  • Issues:     47
  • Failures:   35 
  • Successes:  39

Patterns identified:
  • Total:      7
  • New:        2 (since last run)
  • Updated:    3

Success rate trend:
  • Week 1:     75%
  • Week 2:     81%
  • Week 3:     85%
  • Week 4:     91% ↑ Improving!

Files updated:
  ✓ .claude/memory/patterns-full.md

Suggested agent updates (5+ occurrence patterns):
  1. MAP agent:   Add enum VALUE verification (12 failures)
  2. PATCH agent: Add multi-model detection (6 failures)

Next steps:
  • Review updated patterns-full.md
  • Manually apply suggested agent updates
  • Continue using /orchestrate to gather more data
═══════════════════════════════════════════════════════════
```

### Step 7.5: Gate Advisory (always shown)

Surface the gate status regardless of `--apply` or `--dry-run`:

```
═══════════════════════════════════════════════════════════
Gate status:  $NEW_COUNT new failure(s) since last learn ($LAST_LEARN_AT)
Threshold:    5  |  Fallback ceiling: 3 days
Status:       [TRIPPED / not tripped]
Next run:     $([ TRIPPED ] && echo "now (run /learn --apply)" || echo "poller will check in ≤12h")
═══════════════════════════════════════════════════════════
```

---

## Dry Run Mode

With `--dry-run`, the command:
- Performs all analysis
- Shows what WOULD be updated
- Does NOT modify any files

```
[DRY RUN] Would update: .claude/memory/patterns-full.md
[DRY RUN] Changes:
  + New pattern: SCOPE_CREEP (3 occurrences)
  ~ Updated: ENUM_VALUE (12 → 15 occurrences)
```

---

## When to Run

**Recommended schedule**:
- Weekly (Friday end of day)
- After every 10 completed issues
- After any COMPLEX issue completion
- When success rate drops below 80%

---

## Troubleshooting

### No data found
```bash
# Initialize empty files
echo "" > .claude/memory/failures.jsonl
echo "" > .claude/memory/metrics.jsonl
```

### jq not available
```bash
# Install jq
apt-get install jq  # Linux
brew install jq     # macOS
```

### Parse errors
```bash
# Validate JSONL format
cat .claude/memory/failures.jsonl | jq -c '.' > /dev/null
```

---

## Cross-Project Learning (`--cross-project`)

Aggregates failure patterns and metrics across all projects:

### Step 8: Scan All Projects

Derive project paths from `~/.claude/rules/github-accounts.md` (if available):

```bash
# Extract project paths from github-accounts.md table
ACCOUNTS_FILE="$HOME/.claude/rules/github-accounts.md"
if [ -f "$ACCOUNTS_FILE" ]; then
  PROJECT_PATHS=$(grep -oP '~/[a-zA-Z0-9_/-]+' "$ACCOUNTS_FILE" | sort -u)
else
  # Fallback: scan common locations
  PROJECT_PATHS=$(echo ~/projects/* ~/agents)
fi

# Expand ~ and scan each for failure data
for RAW_PATH in $PROJECT_PATHS; do
  DIR="${RAW_PATH/#\~/$HOME}"
  MEMORY_DIR="${DIR}/.claude/memory"
  if [ -f "${MEMORY_DIR}/failures.jsonl" ]; then
    PROJECT=$(basename "$DIR")
    echo "Found failures.jsonl in $PROJECT"
    cat "${MEMORY_DIR}/failures.jsonl"
  fi
done
```

### Step 9: Merge Patterns

- Group by `root_cause` across all projects
- Note contributing projects for each pattern
- Write to global `~/.claude/memory/patterns-full.md` (not project-local)
- Merge same root_cause counts from different projects

Example output:
```markdown
### ENUM_VALUE — Cross-Project Pattern
**Frequency**: 18 total (12 from mymoney, 4 from VE-RAG, 2 from saas-starter)
**Prevention**: [Same as single-project]
```

---

## Pattern Validation (`--validate`)

Compares success rates before and after pattern additions:

### Step 10: Track Pattern Events

Record when patterns are added/modified:

```bash
# Append to pattern-events.jsonl
echo '{"date":"'$(date +%Y-%m-%d)'","pattern":"ENUM_VALUE","action":"added","success_rate_before":0.74,"agent_versions":{"map":"1.0","patch":"1.0"}}' >> .claude/memory/pattern-events.jsonl
```

### Step 11: Compare Before/After

For each pattern in `pattern-events.jsonl`:
1. Get success rate BEFORE pattern was added (from date field)
2. Get success rate AFTER pattern was added (current)
3. Report delta:

```
Pattern Validation Results:
  ENUM_VALUE:      74% → 91% (+17%) ✅ Effective
  COMPONENT_API:   81% → 85% (+4%)  ✅ Minor improvement
  SCOPE_CREEP:     88% → 86% (-2%)  ⚠️ No improvement — review pattern
```

**Auto-revert** (only when `--apply` and `--validate` are both set):

For each applied pattern where success rate delta is **≤ 0%**:

1. Remove the `## Learned Prevention: {ROOT_CAUSE}` block from the agent file
2. Revert agent version (minor decrement in YAML frontmatter)
3. Record revert in `pattern-events.jsonl`:
   ```json
   {"date":"YYYY-MM-DD","pattern":"SCOPE_CREEP","action":"reverted","reason":"no_improvement","delta":-0.02,"target":"agents/patch.md"}
   ```
4. Report in summary:
   ```
   AUTO-REVERTED: SCOPE_CREEP — 88% → 86% (-2%) in agents/patch.md
   ```

Patterns that are reverted twice are permanently marked `blocked` in
`pattern-events.jsonl` and will not be auto-applied again.

---

## Related Commands

- `/metrics` — View performance dashboard
- `/orchestrate` — Run issues (generates outcome data)
