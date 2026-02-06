---
description: Apply suggested agent improvements from learning analysis
argument-hint: [--dry-run] [--agent NAME] [--pattern PATTERN_NAME]
---

# Agent Update Command

Applies suggested improvements to agent definitions based on learned patterns.

## Usage

```bash
/agent-update              # Apply all suggestions interactively
/agent-update --dry-run    # Preview changes without applying
/agent-update --agent MAP  # Update specific agent only
/agent-update --pattern ENUM_VALUE  # Apply fix for specific pattern
```

---

## How It Works

1. Reads `.claude/memory/patterns.md` for suggested updates
2. Identifies patterns with 5+ occurrences (high impact)
3. Generates specific text additions for agent definitions
4. Applies changes using Claude Code's **Edit tool** (not sed)
5. Increments agent version in frontmatter

---

## Process

### Step 1: Load Suggestions

Read `.claude/memory/patterns.md` and look for sections titled "Suggested Update":

```bash
grep -A 20 "Suggested Update" .claude/memory/patterns.md
```

### Step 2: Validate Target Files

Check agent files exist using project-first resolution:

```bash
for AGENT in map plan patch prove map-plan contract test-planner; do
  if [ -f ".claude/agents/${AGENT}.md" ]; then
    echo "Project: .claude/agents/${AGENT}.md"
  elif [ -f "$HOME/.claude/agents/${AGENT}.md" ]; then
    echo "Global: ~/.claude/agents/${AGENT}.md"
  else
    echo "WARNING: Agent file not found: ${AGENT}.md"
  fi
done
```

### Step 3: Preview Changes

For each suggestion, show:
1. Target file and location
2. Current content at that location
3. Proposed addition

### Step 4: Apply Changes

**Use Claude Code's Edit tool** to insert text at the correct location:

```markdown
Use the Edit tool with:
- file_path: path to agent .md file
- old_string: the section AFTER which to insert (enough context to be unique)
- new_string: the original section + the new addition appended
```

**If Edit tool is not available** (e.g., running outside Claude Code), use Python:

```python
from pathlib import Path

agent_file = Path(".claude/agents/map.md")
content = agent_file.read_text()

# Find insertion point
marker = "### 5. Document Enums (MANDATORY for fullstack)"
idx = content.find(marker)
if idx == -1:
    print(f"Marker not found in {agent_file}")
else:
    # Find end of current section (next ### heading)
    next_section = content.find("\n### ", idx + len(marker))
    insertion_point = next_section if next_section != -1 else len(content)
    new_content = content[:insertion_point] + "\n\n" + addition + "\n" + content[insertion_point:]
    agent_file.write_text(new_content)
```

### Step 5: Increment Agent Version

After modifying an agent, increment the minor version in its frontmatter:

```markdown
# Before
version: 1.0

# After
version: 1.1
```

Use the Edit tool to update the version line.

### Step 6: Verify Changes

```bash
# Check file is still valid markdown
head -20 .claude/agents/map.md
tail -20 .claude/agents/map.md

# Verify frontmatter
head -10 .claude/agents/map.md
```

### Step 7: Commit Changes

```bash
git add .claude/agents/
git commit -m "feat(agents): apply learned patterns

Applied automatic improvements from /learn analysis:
- [list agents modified and what patterns addressed]

Based on analysis of N issues with X% success rate."
```

---

## Dry Run Mode

With `--dry-run`:
- Performs all analysis
- Shows what WOULD change
- Does NOT modify any files
- Does NOT increment versions

---

## Rollback

If updates cause issues:

```bash
# Revert last agent update commit
git revert HEAD

# Or restore specific agent
git checkout HEAD~1 .claude/agents/map.md
```

---

## Update History

Track applied updates in `.claude/memory/updates.jsonl`:

```json
{
  "date": "2026-02-06",
  "agent": "map",
  "pattern": "ENUM_VALUE",
  "old_version": "1.0",
  "new_version": "1.1",
  "commit": "abc123"
}
```

---

## Related Commands

- `/learn` — Generate update suggestions
- `/metrics` — View pattern impact
- `/orchestrate` — Test updated agents
