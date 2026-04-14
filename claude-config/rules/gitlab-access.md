# GitLab Access (Internal VitalAILabs)

## Server

- **GitLab URL:** http://172.16.20.50:8929
- **SSH Git:** ssh://git@172.16.20.50:8931
- **Group:** vitalailabs

## Authentication — NEVER Store Credentials

Agents must NEVER:
- Hardcode tokens, PATs, or passwords in code, config, memory, CLAUDE.md, or chat output
- Log or echo credentials in terminal output
- Store credentials in git-tracked files
- Create new tokens without user approval

## How to Authenticate

### Git operations (clone, push, pull)

**SSH (preferred):** Uses the SSH key configured on each dev box. No token needed.
```bash
git clone ssh://git@172.16.20.50:8931/vitalailabs/<repo>.git
```

**HTTPS:** Uses `credential.helper=store` which reads from `~/.git-credentials` on the dev box. Git handles auth automatically — do not extract or read the credentials file.
```bash
git clone http://172.16.20.50:8929/vitalailabs/<repo>.git
```

### GitLab CLI (`glab`) — preferred for issue/MR operations

`glab` is installed and authenticated on jbox06. Use it from inside app repos:
```bash
ssh jbox06 'cd ~/app-repos/<repo> && glab issue list'
ssh jbox06 'cd ~/app-repos/<repo> && glab issue create --title "..." --label "P0"'
ssh jbox06 'cd ~/app-repos/<repo> && glab mr create --title "..."'
```

### GitLab API access (for bulk/scripted operations)

When direct API access is needed (listing all projects, bulk operations, etc.):

1. Read the PAT from the credential store on the target dev box:
   ```bash
   ssh <devbox> 'grep "172.16.20.50" ~/.git-credentials'
   ```
2. Extract the token portion programmatically — do not display it in chat output
3. Use it in API calls within the same command chain, using the PRIVATE-TOKEN header (not query param — avoids URL encoding issues):
   ```bash
   ssh <devbox> 'TOKEN=$(grep "172.16.20.50" ~/.git-credentials | sed "s/.*:\(glpat-[^@]*\)@.*/\1/") && curl -s -H "PRIVATE-TOKEN: $TOKEN" "http://172.16.20.50:8929/api/v4/projects?search=<query>"'
   ```
4. Never store the extracted token in a variable across multiple commands

## Dev Box → GitLab Mapping

| Dev Box | SSH Alias | User | Auth Method |
|---------|-----------|------|-------------|
| jbox06 | `jbox06` | jjob | SSH key + .git-credentials |
| et01 | `et01` | jwj2002 | SSH key |
| spark (staging) | `spark` | jwj2002 | SSH key |

## App Repos

App repos live in `~/app-repos/` on dev boxes. They are cloned from GitLab by the Dev Center or manually. The naming convention is `app-<slug>`.

To list all projects in the vitalailabs group:
```bash
ssh <devbox> 'TOKEN=$(grep "172.16.20.50" ~/.git-credentials | sed "s/.*:\(glpat-[^@]*\)@.*/\1/") && curl -s "http://172.16.20.50:8929/api/v4/groups/vitalailabs/projects?per_page=100&private_token=$TOKEN" | python3 -c "import sys,json; [print(p[\"path_with_namespace\"]) for p in json.load(sys.stdin)]"'
```
