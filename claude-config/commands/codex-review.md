---
description: Get a second opinion from OpenAI Codex on a plan or proposal
allowed-tools:
  - Bash
  - Read
  - Glob
---

# Codex Review

Get a second opinion from OpenAI Codex CLI on the current plan or specified file.

## Instructions

1. **Find the content to review:**
   - If arguments provided: `$ARGUMENTS`
   - Otherwise, find the most recent `.md` file in `.agents/outputs/` or look for a plan file

2. **Load OPENAI_API_KEY:**
   - First check `~/.claude/.env` (global config)
   - Then check `.env` in current directory
   - Or use the key from environment

3. **Run Codex exec:**
   ```bash
   if [ -f ~/.claude/.env ]; then
     export $(grep OPENAI_API_KEY ~/.claude/.env | xargs)
   elif [ -f .env ]; then
     export $(grep OPENAI_API_KEY .env | xargs)
   fi

   codex exec --skip-git-repo-check --sandbox read-only -o /tmp/codex-review-output.md "[PROMPT]"
   ```

4. **Read and summarize the output** from `/tmp/codex-review-output.md`

5. **Present findings** with a clear recommendation on whether changes are needed

## Review Prompt Template

Use this prompt structure when calling Codex:

```
Review this plan/proposal and provide a second opinion:

---
[INSERT PLAN CONTENT]
---

Analyze for:
1. Missed requirements or edge cases
2. Potential risks or issues not addressed
3. Alternative approaches worth considering
4. Assumptions needing stakeholder validation

Be specific and constructive. If the plan is solid, say so briefly.
```

## Output Format

Present the results as:

```
## Codex Second Opinion

**Assessment:** [One line summary]

**Key Feedback:**
- [Bullet points of main observations]

**Recommended Action:** [None needed / Consider updating X / Discuss Y with stakeholders]
```
