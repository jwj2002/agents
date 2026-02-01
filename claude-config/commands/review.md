# Code Review

Review staged git changes before committing.

## Instructions

Run the code review agent on staged changes:

```bash
python3 ~/agents/code-review/review.py
```

For all uncommitted changes:

```bash
python3 ~/agents/code-review/review.py --all
```

Report the findings to the user, highlighting any critical issues that should be fixed before committing.
