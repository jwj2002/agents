# Core Failure Patterns

The `core-patterns.md` rule file is always loaded into every agent session, regardless of project or context. At 12 lines, it is the most concise and highest-impact rule in the system.

## Why It Exists

Analysis of 86 completed issues across production projects revealed that **three failure patterns account for over 50% of all agent failures**. Rather than loading hundreds of lines of prevention guidance every session, the core patterns file encodes the minimum viable prevention in a compact format that fits within any context budget.

The three patterns covered here have a combined occurrence rate of 89% across all recorded failures. Encoding them as an always-loaded rule means every agent --- MAP, PLAN, PATCH, PROVE --- applies these checks proactively without needing to load project-specific pattern files.

## The Three Patterns

| Pattern | Frequency | Trigger | Prevention |
|---------|-----------|---------|------------|
| **ENUM_VALUE** | 26% of fullstack failures | Issue involves role, status, or type fields across frontend and backend | Read the backend enum definition. Use the VALUE string (right side of `=`), not the Python name (left side). `"CO-OWNER"` not `"CO_OWNER"`. |
| **COMPONENT_API** | 17% of frontend failures | Reusing an existing React component or custom hook | Read the actual source file. Extract PropTypes or function signature before using. Never invent props. |
| **VERIFICATION_GAP** | 63% of all failures | Any assumption about code structure, spec content, or API shape | Verify by reading actual code with the Read tool. Never assume a file exists, a function signature matches, or a schema field is present. |

### ENUM_VALUE in Detail

Backend Python enums define members with a NAME and a VALUE:

```python
class AdvisorRole(str, Enum):
    CO_OWNER = "CO-OWNER"      # NAME: CO_OWNER, VALUE: "CO-OWNER"
    ASSOCIATE = "ASSOCIATE"    # NAME: ASSOCIATE, VALUE: "ASSOCIATE"
```

The database stores the VALUE. The API sends and receives the VALUE. Frontend code must use the VALUE. The NAME is only used in Python code to reference the enum member. When an agent uses `"CO_OWNER"` in a frontend fetch call or API request body, it silently fails validation because the backend expects `"CO-OWNER"`.

The CONTRACT agent now documents enum VALUES explicitly in a dedicated section, and the PROVE agent verifies that frontend strings match backend VALUES during its verification pass.

### COMPONENT_API in Detail

Agents have training data about common React patterns, but your project's hooks and components may differ. For example:

```javascript
// Training data says:
const { session, loading } = useSession();

// But your project actually does:
const session = useSession();  // returns value directly
```

The fix is mechanical: read the actual source file before using any component or hook. The MAP agent documents reusable component APIs in its artifact so that PATCH does not need to re-discover them.

### VERIFICATION_GAP in Detail

This is the most common pattern because it is the most general. Any time an agent proceeds based on an assumption rather than reading actual code, it risks a VERIFICATION_GAP failure. Common triggers include:

- Assuming a spec requirement was already implemented
- Assuming a file exists at an expected path
- Assuming a function accepts certain parameters
- Assuming a database column has a particular type

## Decision Matrix

When starting any issue, agents evaluate these triggers:

| Condition | Action |
|-----------|--------|
| Issue references a spec | Read the spec file FIRST before planning |
| Issue involves enums across stack boundary | Read backend enum, extract VALUE strings |
| Issue reuses existing component or hook | Read source file, extract actual API |
| Any assumption about code structure | Read the actual file to confirm |

!!! warning "Single Source of Truth"
    `core-patterns.md` is the canonical definition of these three patterns. All other files --- agent definitions, training docs, workflow docs --- **reference** these patterns but do not redefine them. When updating a pattern, edit `core-patterns.md` only. Duplicating definitions across files leads to drift where one copy gets updated and others become stale.

## Quick Gotchas

These additional failure modes appear frequently enough to warrant awareness, even though they are not in the always-loaded file:

| Gotcha | What Goes Wrong | Prevention |
|--------|----------------|------------|
| **Directory structure** | Agent creates `backend/src/` or reorganizes folders | CLAUDE.md must list forbidden directory changes explicitly |
| **React hook return shape** | Agent assumes `const { data } = useHook()` when hook returns value directly | Read the hook source; destructuring patterns vary per project |
| **Access control** | Agent adds endpoint without `account_id` scoping | Use `require_account_owner` or equivalent from `deps.py`; never inline permission checks |
| **SQLite compatibility** | Agent uses PostgreSQL-only syntax in test fixtures | Tests run against SQLite in-memory; avoid `ARRAY`, `JSONB`, or `ON CONFLICT` syntax |
| **Multi-model updates** | Agent changes one model but forgets related models | When modifying a model, grep for all foreign key references and relationship definitions |

## How Agents Load It

The rule file uses `alwaysApply: true` in its frontmatter, which means Claude Code loads it into every session automatically. No conditional trigger is needed. The file lives at:

```
~/.claude/rules/core-patterns.md  (symlink)
    -> ~/agents/claude-config/rules/core-patterns.md  (source)
```

!!! tip "Full Patterns for Complex Issues"
    For COMPLEX pipeline tier issues (6+ files, architectural decisions), agents load the extended pattern file at `.claude/memory/patterns-full.md` (~660 lines). This contains detailed prevention checklists with examples for all 12 root cause codes. The core patterns file handles the common cases; the full file handles edge cases.

## Relationship to the Learning Loop

Core patterns are the output of the self-learning system. The `/learn` command analyzes `metrics.jsonl` and `failures.jsonl`, clusters failures by root cause, and updates pattern files. When a pattern reaches 5+ occurrences, `/learn --apply` writes prevention checklists directly into agent definition files and bumps agent versions.

The core patterns file is updated manually and rarely --- only when a new failure pattern reaches sufficient frequency to warrant always-loaded status. The current three patterns have been stable since early 2026.

## Related Rules

| Rule | Loaded When | Purpose |
|------|------------|---------|
| `behavioral-evals.md` | PROVE agent runs | Defines verification test cases by file type |
| `eval-file-mapping.md` | PROVE agent runs | Maps changed files to relevant evals |
| `post-merge-verification.md` | `/pr --merge` | Post-merge health checks |
