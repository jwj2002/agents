# Mode 3: Local Copy of a jbox06 Repo (Hybrid)

> Moved out of the always-loaded `claude-config/rules/dev-environment.md` (#384)
> to keep the always-loaded prompt under budget. This is a rare path; read it
> only when the user explicitly wants a local copy of a jbox06 repo.

Sometimes a VitalAILabs app repo needs a local copy on the laptop — for offline
work, alternate tooling, or side experiments.

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
