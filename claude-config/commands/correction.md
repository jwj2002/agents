---
description: Mark a just-PASSED issue as first_pass_incorrect and record what was missed
argument-hint: <issue-number> "<what was missed>"
---

# Correction Command

Records a post-PROVE correction turn — a defect not caught by PROVE that required
follow-up work. This makes first-pass-correctness measurable over time.

## Usage

```bash
/correction 179 "forgot to wire the new check into main()"
/correction 184 "missed that the MCP reader needed a backward-compat note"
```

## When to Use

After running /orchestrate on an issue and then discovering a missed wiring,
an overlooked requirement, or a logic error that PROVE did not catch — before
or after /ship. Run once per correction turn; multiple corrections for the
same issue append to the `corrections` list.

## Process

### Step 1: Parse Arguments

Extract issue number and reason from the command arguments. The first argument
is the issue number; everything after it (quoted or unquoted) is the reason.

### Step 2: Flip the Metrics Record

```bash
python3 - <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.expanduser('~/.claude/hooks'))
from state_manager import flip_to_correction
from pathlib import Path

issue = int("$ISSUE")
reason = "$REASON"

ok = flip_to_correction(Path('.'), issue, reason, emit_failure=True)
if ok:
    print(f"Recorded correction for issue #{issue}: first_pass_correct=false")
    print(f"Reason: {reason}")
    print(f"A FIRST_PASS_DEFECT entry was also appended to failures.jsonl.")
else:
    print(f"WARNING: No metrics record found for issue #{issue}.")
    print("Run /orchestrate first or verify the issue number.")
PYEOF
```

### Step 3: Confirm

After the flip, verify the record was written:

```bash
tail -5 .claude/memory/metrics.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    if r.get('first_pass_correct') == False:
        print(f\"  Issue #{r['issue']}: first_pass_correct=false, corrections={r['corrections']}\")
"
```

## Notes

- The original PASS record is preserved in metrics.jsonl as history.
- The appended correction record is the canonical state (most-recent wins).
- /learn and /metrics will count this issue as first_pass_correct=false.
- The Stop hook in verify_completion.py will hint at this command when it
  detects a probable correction turn (fix-branch + recent unflipped PASS).
