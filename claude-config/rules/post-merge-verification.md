---
paths: ["**/.github/**", "**/CHANGELOG*", "**/.agents/**"]
---

# Post-Merge Verification

Run automatically after squash merge in the `/pr` workflow. Ensures main is healthy.

## Checklist

After merge completes (before branch cleanup):

```bash
# 1. Pull latest main
git checkout main && git pull origin main

# 2. Lint
ruff check . && ruff format --check .
# Frontend (if applicable): cd frontend && npm run lint

# 3. Tests
pytest tests/ -x --timeout=60
# Frontend (if applicable): cd frontend && npm run build

# 4. Server startup (if applicable)
# Start server, wait 5s, check health endpoint, kill
timeout 15 python3 -m uvicorn app.main:app --host 127.0.0.1 --port 9999 &
sleep 5
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9999/api/v1/health 2>/dev/null)
kill %1 2>/dev/null
# HTTP_CODE should be 200

# 5. Check for new warnings in startup logs
# Look for: ImportError, ModuleNotFoundError, DeprecationWarning
```

## If Any Check Fails

1. Report the failure to the user BEFORE branch cleanup
2. Suggest: `git checkout -b fix/hotfix-<description> origin/main`
3. Do NOT prune branches until main is green
4. Do NOT continue with other work until the hotfix is merged
