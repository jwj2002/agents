# Code Review Agent

Reviews staged git changes before commit using Claude.

## What It Checks

### Critical (blocks commit)
- SQL injection, XSS, command injection
- Hardcoded secrets, API keys, passwords
- Null pointer / undefined access
- Infinite loops, resource leaks

### Warning (should fix)
- Missing error handling
- Unchecked array access
- TODO/FIXME in code
- Debug statements (console.log, print)
- Magic numbers

### Info (suggestions)
- Naming improvements
- Simplification opportunities
- Missing type hints
- Documentation gaps

### Project Patterns
- ENUM_VALUE: Use string VALUES not Python names
- COMPONENT_API: Verify props match PropTypes
- TODO/STUB: Check for incomplete code

## Usage

### Manual Review

```bash
# Review staged changes
code-review

# Review all uncommitted changes
code-review --all

# Strict mode (exit 1 if any issues)
code-review --strict

# JSON output
code-review --json
```

### Claude Code

```
/review
```

### Pre-Commit Hook (Automatic)

Install the hook to run review before every commit:

```bash
~/agents/code-review/install-hook.sh ~/projects/mymoney-dev
```

After installation:
- Review runs automatically on `git commit`
- Commit blocked if critical issues, warnings, review tool failures, or truncated diffs are found
- Bypass with `git commit --no-verify`

## Output Example

```
============================================================
CODE REVIEW
============================================================

Files: 3
  - src/api/auth.py
  - src/utils/db.py
  - frontend/Login.jsx

Summary: Found potential SQL injection and missing error handling.

CRITICAL ISSUES (must fix):
----------------------------------------
  [security] src/utils/db.py:45
    SQL query built with string concatenation
    → Use parameterized queries instead

WARNINGS (should fix):
----------------------------------------
  [error-handling] src/api/auth.py:23
    API call without try/catch
    → Wrap in try/catch and handle errors

  [todo] frontend/Login.jsx:67
    TODO comment left in code
    → Complete or remove before commit

============================================================
NOT APPROVED ✗ - Fix critical issues before committing
============================================================
```

## Files

| File | Purpose |
|------|---------|
| `config.py` | Review categories and patterns |
| `review.py` | Main review logic |
| `install-hook.sh` | Installs pre-commit hook |

## Integration with PROVE

| Agent | When | Purpose |
|-------|------|---------|
| **code-review** | Pre-commit | Catch issues before commit |
| **PROVE** | Post-PATCH | Verify implementation in orchestrate workflow |

Use both for defense in depth: code-review for ad-hoc work, PROVE for orchestrated issues.
