# Conditional Rules

Rules in this system follow a tiered loading strategy: load the minimum context needed for the current task. Every token of rules competes with code context in the agent's working memory, so unnecessary rules waste capacity that could be spent reading source files.

## How Conditional Loading Works

!!! info "Auto-loading behavior"
    Rules load automatically based on which files the agent is reading or editing. You do not need to manually activate rules -- Claude Code matches the file path against the path patterns in each rule's frontmatter and loads matching rules transparently.

Claude Code evaluates rule files based on **path-based triggers** defined in each file's YAML frontmatter under the `paths:` key. When the agent is working in a directory that matches a trigger pattern, the corresponding rule is loaded. When no match occurs, the rule stays unloaded and costs zero tokens.

```yaml
---
paths: ["**/backend/**", "**/api/**", "**/services/**"]
---
```

Only `git-workflow.md` declares `alwaysApply: true` in its frontmatter. Other always-loaded rules (`core-patterns.md`, `implementation-routing.md`, `github-accounts.md`, `dev-environment.md`) achieve the same effect by setting `paths: ["**"]`, which matches every file in the workspace.

## Complete Rule Inventory

There are **12 rule files** in `claude-config/rules/`:

| Rule File | Lines | Loaded When | Purpose |
|-----------|-------|-------------|---------|
| `core-patterns.md` | 15 | `paths: ["**"]` (always) | Top 3 failure patterns covering 89% of failures |
| `git-workflow.md` | 113 | `alwaysApply: true` (always) | Branch naming, commit conventions, PR process |
| `implementation-routing.md` | 90 | `paths: ["**"]` (always) | Codex delegation, plan mode vs orchestrate routing |
| `github-accounts.md` | 43 | `paths: ["**"]` (always) | Multi-account git configuration |
| `dev-environment.md` | 141 | `paths: ["**"]` (always) | Local vs jbox06 vs hybrid mode routing |
| `behavioral-evals.md` | 144 | `**/backend/**`, `**/frontend/**`, `**/.agents/**`, `Dockerfile`, `*.env*` | E01-E15 verification check catalog |
| `eval-file-mapping.md` | 42 | `**/.agents/**`, `**/backend/**`, `**/frontend/**`, `**/PROVE*.md` | Maps file patterns to relevant evals |
| `orchestrate-workflow.md` | 587 | `.agents/**/*.md` | Agent efficiency rules, artifact naming, CONTRACT requirements |
| `spec-review-workflow.md` | 360 | `**/specs/**`, `**/.agents/**` | Spec finalization gate, review process, issue creation rules |
| `rbac-pattern.md` | 110 | `**/backend/**/auth/**`, `**/backend/**/permissions*`, `**/backend/**/security/**`, `**/auth/**`, `**/router*` | Permission-based access control pattern |
| `gitlab-access.md` | 74 | `**/app-repos/**`, `**/vitalailabs/**`, `**/.gitlab/**` | Internal GitLab auth and credential handling |
| `post-merge-verification.md` | 42 | `**/.github/**`, `**/CHANGELOG*`, `**/.agents/**` | Post-merge ops verification checklist |

## Token Budget Analysis

Loading all rules simultaneously would consume roughly 50 KB of context. With conditional loading, a typical session loads only what it needs:

| Scenario | Rules Loaded | Approximate Lines |
|----------|-------------|-------------------|
| Bare laptop session | core-patterns + git-workflow + implementation-routing + github-accounts + dev-environment | ~400 |
| Backend module work | always-loaded + rbac-pattern (if auth path) | ~510 |
| Orchestrate pipeline | always-loaded + orchestrate-workflow + behavioral-evals + eval-file-mapping | ~1,200 |
| Spec review | always-loaded + spec-review-workflow | ~760 |
| GitLab/jbox06 work | always-loaded + gitlab-access | ~470 |

!!! note "Savings Compound"
    A frontend-only session can skip `orchestrate-workflow.md` (587 lines) and `rbac-pattern.md` (110 lines). The recovered space is equivalent to reading two additional source files -- which directly improves implementation accuracy.

## When Each Rule Loads

### Always-Loaded Rules

These five rules load into every session:

- **core-patterns.md** -- Three failure patterns that apply to all codebases (`paths: ["**"]`)
- **git-workflow.md** -- Branch, commit, and PR conventions (`alwaysApply: true`)
- **implementation-routing.md** -- Decision matrix for `/quick`, plan mode, `/orchestrate`, and Codex delegation (`paths: ["**"]`)
- **github-accounts.md** -- Maps projects to the correct GitHub account (`paths: ["**"]`)
- **dev-environment.md** -- Routes work between laptop, jbox06, and hybrid modes (`paths: ["**"]`)

### Backend Authorization Context

When the agent reads or writes auth-related backend files (`**/backend/**/auth/**`, `**/backend/**/permissions*`, `**/backend/**/security/**`, `**/auth/**`, `**/router*`):

- **rbac-pattern.md** loads with the role-to-permission mapping pattern, the `require_permission()` dependency factory, and per-endpoint enforcement rules.

### Orchestrate Context

When the agent operates on files matching `.agents/**/*.md` (typically during `/orchestrate` workflows):

- **orchestrate-workflow.md** loads with artifact naming conventions, agent size compliance targets, and CONTRACT enforcement rules.

### Verification Context

When the agent is running PROVE or otherwise touching files in `**/backend/**`, `**/frontend/**`, `**/.agents/**`, `Dockerfile`, or `*.env*`:

- **behavioral-evals.md** loads with the E01-E15 verification catalog.
- **eval-file-mapping.md** loads with the file-pattern routing table.

### Spec Context

When the agent operates on files matching `**/specs/**` or `**/.agents/**`:

- **spec-review-workflow.md** loads with the spec finalization gate, draft-to-final workflow, and issue creation rules.

### GitLab Context

When working in `**/app-repos/**`, `**/vitalailabs/**`, or `**/.gitlab/**`:

- **gitlab-access.md** loads with VitalAILabs GitLab auth, credential helpers, and dev-box mapping.

### Post-Merge Context

When working in `**/.github/**`, `**/CHANGELOG*`, or `**/.agents/**`:

- **post-merge-verification.md** loads with the post-squash-merge health checklist used by `/pr`.

## Design Principles

1. **Minimum context for current task** -- Only load rules relevant to the files being touched.
2. **Always-loaded stays small** -- Even the always-loaded set is now ~400 lines combined; growth here costs every session.
3. **Conditional rules can be large** -- `orchestrate-workflow.md` at 587 lines is acceptable because it only loads inside `.agents/`.
4. **Path patterns must be specific** -- Broad patterns like `**/*.py` would defeat the purpose; use directory-based patterns that match project structure.
5. **No duplication across rules** -- Each rule owns its domain; cross-references use "see `core-patterns.md`" rather than repeating content.

## Rule File Anatomy

Every rule file follows the same structure:

```markdown
---
description: "Optional human-readable description for tooling"
alwaysApply: true                # only set on git-workflow.md
paths: ["**/backend/**"]         # path triggers (use ["**"] for always-loaded)
---

# Rule Title

Content that agents read and follow.
```

The frontmatter is parsed by Claude Code to determine loading behavior. The body is injected into the agent's context when the rule is active. Keep the body focused -- avoid tutorial-style explanations and focus on actionable instructions.

## What Each Conditional Rule Contains

### orchestrate-workflow.md (587 lines)

The largest rule file. Loaded during agent pipeline execution:

- Artifact naming convention (`{agent}-{issue}-{mmddyy}.md`)
- Agent output size targets with compression checklists
- CONTRACT enforcement (mandatory for fullstack, PATCH stops without it)
- Parallel execution rules (which phases can overlap)
- State management integration points

### spec-review-workflow.md (360 lines)

Loaded during spec analysis and issue creation:

- Spec finalization gate (status must be `final` before issues are created)
- Draft-to-final lifecycle with review rounds
- Gap classification (Implemented, Partial, Missing, Differs)
- Issue creation format and dependency ordering

### behavioral-evals.md (144 lines)

The E01-E15 catalog: each eval traces back to a real production failure with what to check, why, and how to verify. Used by PROVE.

### dev-environment.md (141 lines)

Routes work between local development, remote jbox06 development (VitalAILabs apps via SSH), and hybrid mode. Includes SSH alias conventions and bundle-based laptop-to-jbox06 sync flows.

### rbac-pattern.md (110 lines)

The single-org permission pattern: `User.role` -> `ROLE_PERMISSIONS` dict -> `require_permission("resource:action")` dependency. Includes the dependency factory implementation and router usage examples.

!!! tip "Adding New Rules"
    When creating a new rule file, choose the narrowest `paths:` pattern that covers the relevant files. Measure the file size and consider whether the content could be added to an existing rule instead. Rules under 1 KB can often be merged with an existing always-loaded rule; rules over 5 KB should always be conditional. Use `paths: ["**"]` (not `alwaysApply: true`) for new always-loaded rules unless you specifically need the legacy frontmatter key.
