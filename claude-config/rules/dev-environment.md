---
paths: ["**"]
---

# Development Environment Routing

## Development Modes

Every project falls into one of three modes. Check which mode before writing code or creating issues.

### Mode 1: Local Development (default)

Code lives on this laptop. Standard git workflow.

**Applies to:** GitHub repos, personal projects, open-source work.

**Indicators:**
- Repo is cloned under `~/projects/` on the laptop
- Remote is GitHub (github.com)

**Issue tracking:** GitHub Issues via `gh` CLI. Follow github-accounts.md for account routing.
- No VitalAILabs platform involvement

**Workflow:** Edit files locally with Claude Code tools (Write, Edit). Use git normally.

### Mode 2: Remote Development on jbox06

Code lives on jbox06 (`172.16.20.58`). Claude Code on the laptop writes files via SSH.

**Applies to:** All VitalAILabs app repos (`app-*`), anything in `~/app-repos/` on jbox06.

**Indicators:**
- Repo is in `~/app-repos/` on jbox06
- Remote is internal GitLab (172.16.20.50)
- App is managed by the VitalAILabs Dev Center
- Project memory or CLAUDE.md says "jbox06" or "VitalAILabs app"

**Workflow:**
- **Read files:** `ssh jbox06 'cat ~/app-repos/<repo>/<path>'`
- **Write files:** `ssh jbox06 'cat > ~/app-repos/<repo>/<path> << '\''EOF'\'' ... EOF'`
- **List files:** `ssh jbox06 'ls ~/app-repos/<repo>/'` or `find`
- **Run tests:** `ssh jbox06 'cd ~/app-repos/<repo> && python3 -m pytest'`
- **Git operations:** `ssh jbox06 'cd ~/app-repos/<repo> && git add -A && git commit -m "msg" && git push origin <branch>'`
- **Never** clone VitalAILabs app repos locally — laptop cannot reach GitLab directly

**Issue tracking:** GitLab Issues via `glab` CLI on jbox06 (installed and authenticated):
```bash
# List issues (run from inside an app repo on jbox06)
ssh jbox06 'cd ~/app-repos/<repo> && glab issue list'

# Create an issue
ssh jbox06 'cd ~/app-repos/<repo> && glab issue create --title "..." --description "..." --label "P0,backend"'

# View an issue
ssh jbox06 'cd ~/app-repos/<repo> && glab issue view 3'

# Create a merge request
ssh jbox06 'cd ~/app-repos/<repo> && glab mr create --title "..." --description "..."'
```

**Do NOT use `gh` CLI for VitalAILabs projects** — `gh` is for GitHub only. Use `glab` on jbox06 for GitLab.

## How to Detect Mode

Before writing code, check:

1. **Is there a project memory** referencing jbox06 or a VitalAILabs app? → Mode 2
2. **Does the user say** "on jbox06" or reference an app repo? → Mode 2
3. **Is the repo under** `~/projects/` on the laptop? → Mode 1
4. **When in doubt:** Ask — "Are we developing locally or on jbox06?"

## SSH Alias

```
Host jbox06
    HostName 172.16.20.58
    User jjob
    IdentityFile ~/.ssh/id_ed25519
```

## jbox06 App Repo Convention

All VitalAILabs app repos live at `~/app-repos/app-<slug>/` on jbox06.

To list all app repos:
```bash
ssh jbox06 'ls ~/app-repos/'
```

## Rules for Remote Development

- One source of truth: the repo on jbox06. No local clones.
- All file writes go through SSH to jbox06.
- All git operations (commit, push, branch) run on jbox06.
- Read files via SSH before editing — same as local Read tool but through `ssh jbox06 'cat ...'`.
- Test on jbox06 where the platform runtime is available.
- GitLab push goes from jbox06 → GitLab (local network, instant).

## Mode 3: Local Copy of a jbox06 Repo (Hybrid)

Sometimes a VitalAILabs app repo needs a local copy on the laptop — for offline work, alternate tooling, or side experiments.

**Indicators:**
- User explicitly says "pull this to my laptop" or "I want a local copy"
- Repo exists in both `~/projects/` on laptop AND `~/app-repos/` on jbox06

**Setup:** Bundle from jbox06, clone locally:
```bash
ssh jbox06 'cd ~/app-repos/<repo> && git bundle create /tmp/<repo>.bundle --all'
scp jbox06:/tmp/<repo>.bundle /tmp/
cd ~/projects && git clone /tmp/<repo>.bundle <repo>
```

**Workflow:**
- Develop locally using standard Claude Code tools (Write, Edit)
- jbox06 remains the push path to GitLab — laptop cannot reach GitLab directly
- To sync laptop → jbox06 → GitLab:
  ```bash
  cd ~/projects/<repo>
  git bundle create /tmp/<repo>.bundle <branch>
  scp /tmp/<repo>.bundle jbox06:/tmp/
  ssh jbox06 'cd ~/app-repos/<repo> && git pull /tmp/<repo>.bundle <branch> && git push origin <branch>'
  ```
- To sync jbox06 → laptop:
  ```bash
  ssh jbox06 'cd ~/app-repos/<repo> && git bundle create /tmp/<repo>.bundle --all'
  scp jbox06:/tmp/<repo>.bundle /tmp/
  cd ~/projects/<repo> && git pull /tmp/<repo>.bundle <branch>
  ```

**Rules for hybrid mode:**
- jbox06 is still the authority for pushing to GitLab
- Always sync before and after local work sessions to avoid drift
- If both copies diverge, jbox06 wins (it's closer to GitLab)
- Mark in project memory which mode the repo is in

## Do NOT

- Try to reach GitLab (172.16.20.50) directly from the laptop — it won't work
- Maintain two copies without syncing — creates drift
- Assume a local clone is up to date — always fetch from jbox06 first
