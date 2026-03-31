---
name: deep-review
version: 1.0
description: Comprehensive critical code review focused on quality, performance, patterns, and reuse
argument-hint: [path-or-scope]
---

# Deep Code Review (v1.0)

Comprehensive, critical code review. Not a pre-commit check — a thorough architectural and quality review.

## Usage

```
/deep-review src/services/           # Review a directory
/deep-review app/models.py           # Review a specific file
/deep-review .                       # Review entire project
/deep-review --since main            # Review all changes since main
```

## Instructions

Perform a comprehensive, critical code review. Be direct and honest — do not soften findings or pad with praise. Evaluate the code as if reviewing a pull request for a production system you are personally responsible for.

### Step 1: Determine Scope

Parse the argument to determine what to review:
- **File path**: Review that file
- **Directory path**: Review all source files in that directory (recursively)
- **`.`**: Review the entire project (focus on `src/`, `app/`, `server/`, `backend/`, `frontend/` — skip `node_modules/`, `.venv/`, `dist/`, `build/`)
- **`--since main`** or **`--since <ref>`**: Review `git diff <ref>...HEAD`
- **No argument**: Review all uncommitted changes (`git diff HEAD`)

### Step 2: Read Everything First

**CRITICAL**: Read every file in scope BEFORE forming opinions. Do not review from memory or assumptions.

- For directories: glob all source files, read each one
- For `--since`: get the diff, then read the full files that changed (not just the diff — you need context)
- Build a mental model of the module structure, data flow, and dependencies before writing findings

### Step 3: Evaluate Each Dimension

Evaluate each dimension independently. For each, state what you found — not what you looked for. Skip dimensions that don't apply (e.g., security for a pure utility module with no I/O).

#### 1. Architecture & Design
- Does the structure make sense for the problem being solved?
- Are responsibilities clearly separated or tangled?
- Are there god objects, god functions, or circular dependencies?
- Is the abstraction level consistent (not mixing high-level orchestration with low-level details in the same function)?

#### 2. Code Reuse & DRY
- Is there duplicated logic that should be extracted?
- Are there existing utilities/helpers being ignored in favor of inline rewrites?
- Are abstractions being created prematurely (one caller, no variation)?
- Could shared patterns be consolidated without over-engineering?

#### 3. Correctness & Edge Cases
- Are there logic errors, off-by-one mistakes, or unhandled states?
- What happens with empty inputs, None/null values, or concurrent access?
- Are error paths tested or just optimistic happy paths?
- Are type contracts honored (what goes in, what comes out)?

#### 4. Performance
- Are there unnecessary loops, redundant I/O, or N+1 query patterns?
- Are large datasets loaded when only a subset is needed?
- Are there blocking calls in async contexts or async calls that should be sync?
- Is caching used where appropriate, and invalidated correctly?

#### 5. Security
- Input validation at system boundaries (user input, API requests, file uploads)?
- SQL injection, XSS, command injection, path traversal?
- Secrets in code, logs, or error messages?
- Auth/authz checks present and correct?

#### 6. Readability & Maintainability
- Can a new developer understand this code without the author explaining it?
- Are names descriptive and consistent?
- Is complexity justified or accidental?
- Are comments explaining "why" (not "what")?

#### 7. Error Handling
- Are errors caught at the right level (not too broad, not too narrow)?
- Do error messages help diagnose the problem?
- Are failures recoverable where they should be?
- Are external service failures handled gracefully?

### Step 4: Report Findings

For each finding, provide:

```
**File:Line** — `path/to/file.py:42`
**Severity** — CRITICAL / WARNING / SUGGESTION
**What** — the specific problem (not generic advice)
**Why** — the consequence if left unfixed
**Fix** — concrete code change or approach (not "consider improving")
```

Group findings by dimension. Use this structure:

```markdown
## Architecture & Design

### [SEVERITY] Short title — `file:line`
**What**: ...
**Why**: ...
**Fix**: ...
```

### Step 5: Summary

End with:

```markdown
## Summary

**Scope**: X files reviewed (Y total lines)
**Findings**: X total (Y critical, Z warnings, W suggestions)

### Top 3 Priorities
1. ...
2. ...
3. ...

### Overall Assessment
One honest paragraph. What is the code's biggest strength and biggest weakness?
Is this production-ready? What would you fix before shipping?
```

## Rules

- Do NOT inflate findings. If the code is solid, say so with a short summary.
- Do NOT add generic advice ("consider adding more tests"). Every finding must reference a specific location in the code.
- Do NOT praise code to be polite. Neutral silence on a dimension means it's fine.
- PREFER fewer high-quality findings over many trivial ones.
- READ every file in scope before forming opinions. Do not review from memory.
- Be HONEST. The goal is to make the code better, not to make the author feel good.
