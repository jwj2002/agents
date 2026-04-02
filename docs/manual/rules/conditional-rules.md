# Conditional Rules

Rules in this system follow a tiered loading strategy: load the minimum context needed for the current task. Every token of rules competes with code context in the agent's working memory, so unnecessary rules waste capacity that could be spent reading source files.

## How Conditional Loading Works

!!! info "Auto-loading behavior"
    Rules load automatically based on which files the agent is reading or editing. You do not need to manually activate rules -- Claude Code matches the file path against the glob patterns in each rule's frontmatter and loads matching rules transparently.

Claude Code evaluates rule files based on **path-based triggers** defined in each file's YAML frontmatter. When the agent is working in a directory that matches a trigger glob, the corresponding rule is loaded. When no match occurs, the rule stays unloaded and costs zero tokens.

```yaml
---
description: "FastAPI layered architecture rules"
globs: ["**/backend/**", "**/api/**", "**/services/**"]
---
```

Rules with `alwaysApply: true` bypass the path matching and load into every session. Only `core-patterns.md`, `git-workflow.md`, `implementation-routing.md`, and `github-accounts.md` use this setting.

## Complete Rule Inventory

| Rule File | Size | Loaded When | Purpose |
|-----------|------|-------------|---------|
| `core-patterns.md` | 0.7 KB (12 lines) | **Always** (`alwaysApply: true`) | Top 3 failure patterns covering 89% of failures |
| `git-workflow.md` | 3.2 KB | **Always** (`alwaysApply: true`) | Branch naming, commit conventions, PR process |
| `implementation-routing.md` | 2.1 KB | **Always** (`alwaysApply: true`) | Plan mode vs orchestrate decision matrix |
| `github-accounts.md` | 1.0 KB | **Always** (`alwaysApply: true`) | Multi-account git configuration |
| `fastapi-layered-pattern.md` | 23.6 KB (767 lines) | `**/backend/**`, `**/api/**`, `**/services/**` | Full layered architecture reference: router, service, repository, models, schemas, deps |
| `orchestrate-workflow.md` | 16.7 KB (588 lines) | `.agents/**/*.md` | Agent efficiency rules, artifact naming, size compliance, CONTRACT requirements |
| `spec-review-workflow.md` | 12.0 KB (361 lines) | `**/specs/**`, `**/.agents/**` | Spec finalization gate, review process, issue creation rules |
| `behavioral-evals.md` | 4.2 KB (~140 lines) | PROVE phase | Behavioral verification test suite |
| `eval-file-mapping.md` | 1.2 KB (~38 lines) | PROVE phase | Maps file patterns to relevant evals |
| `post-merge-verification.md` | 1.2 KB (~38 lines) | `/pr --merge` | Post-merge ops verification checklist |

## Token Budget Analysis

Loading all rules simultaneously would consume approximately 43 KB of context. With conditional loading, a typical session loads only what it needs:

| Scenario | Rules Loaded | Approximate Size |
|----------|-------------|-----------------|
| Backend bugfix | core-patterns + git-workflow + implementation-routing + fastapi-layered | ~28 KB |
| Frontend-only change | core-patterns + git-workflow + implementation-routing | ~6 KB |
| Orchestrate pipeline | core-patterns + git-workflow + orchestrate-workflow | ~21 KB |
| Spec review | core-patterns + git-workflow + spec-review-workflow | ~16 KB |
| Documentation update | core-patterns + git-workflow + implementation-routing | ~6 KB |

!!! note "Savings Compound"
    A frontend-only session saves ~37 KB of context by not loading `fastapi-layered-pattern.md` or `orchestrate-workflow.md`. That recovered space is equivalent to reading two additional source files --- which directly improves implementation accuracy.

## When Each Rule Loads

### Always-Loaded Rules

These four rules load into every session regardless of working directory:

- **core-patterns.md** --- Three failure patterns that apply to all codebases
- **git-workflow.md** --- Branch, commit, and PR conventions used on every project
- **implementation-routing.md** --- Decision matrix for choosing plan mode vs orchestrate
- **github-accounts.md** --- Maps projects to the correct GitHub account

### Backend Context

When the agent reads or writes files matching `**/backend/**`, `**/api/**`, or `**/services/**`:

- **fastapi-layered-pattern.md** loads with the full architecture reference: layer responsibilities, module structure, enum conventions, access control patterns, and SQLAlchemy/Pydantic usage rules

### Orchestrate Context

When the agent operates on files matching `.agents/**/*.md` (typically during `/orchestrate` workflows):

- **orchestrate-workflow.md** loads with artifact naming conventions, agent size compliance targets, and CONTRACT enforcement rules

### Spec Context

When the agent operates on files matching `**/specs/**` or `**/.agents/**`:

- **spec-review-workflow.md** loads with the spec finalization gate, draft-to-final workflow, and issue creation rules

## Design Principles

1. **Minimum context for current task** --- Only load rules relevant to the files being touched
2. **Always-loaded stays tiny** --- The always-loaded rules total ~7 KB combined; any growth here costs every session
3. **Conditional rules can be large** --- `fastapi-layered-pattern.md` at 767 lines is acceptable because it only loads for backend work
4. **Path globs must be specific** --- Broad globs like `**/*.py` would defeat the purpose; use directory-based patterns that match project structure
5. **No duplication across rules** --- Each rule owns its domain; cross-references use "see `core-patterns.md`" rather than repeating content

## Rule File Anatomy

Every rule file follows the same structure:

```markdown
---
description: "Human-readable description for tooling"
alwaysApply: true                # or omit for conditional
globs: ["**/backend/**"]         # path triggers (conditional only)
---

# Rule Title

Content that agents read and follow.
```

The frontmatter is parsed by Claude Code to determine loading behavior. The body is injected into the agent's context when the rule is active. Keep the body focused --- avoid tutorial-style explanations and focus on actionable instructions.

## What Each Conditional Rule Contains

### fastapi-layered-pattern.md (23.6 KB)

The largest rule file. Contains the complete FastAPI layered architecture reference:

- Layer responsibilities (router, service, repository, models, schemas, deps)
- Module file structure with per-file conventions
- Enum rules (member names = UPPER_SNAKE, values = stored in DB)
- Access control patterns (always via dependencies, never inline)
- SQLAlchemy 2.0 conventions (Mapped types, select() syntax)
- Pydantic v2 conventions (ConfigDict, from_attributes)
- Error handling (AppError subclasses, not HTTPException in services)

### orchestrate-workflow.md (16.7 KB)

Loaded during agent pipeline execution:

- Artifact naming convention (`{agent}-{issue}-{mmddyy}.md`)
- Agent output size targets with compression checklists
- CONTRACT enforcement (mandatory for fullstack, PATCH stops without it)
- Parallel execution rules (which phases can overlap)
- State management integration points

### spec-review-workflow.md (12.0 KB)

Loaded during spec analysis and issue creation:

- Spec finalization gate (status must be `final` before issues are created)
- Draft-to-final lifecycle with review rounds
- Gap classification (Implemented, Partial, Missing, Differs)
- Issue creation format and dependency ordering

!!! tip "Adding New Rules"
    When creating a new rule file, choose the narrowest glob that covers the relevant files. Measure the file size and consider whether the content could be added to an existing rule instead. Rules under 1 KB can often be merged with an existing always-loaded rule; rules over 5 KB should always be conditional.
