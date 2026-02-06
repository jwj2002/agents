# Claude MCP Server — Vault & Metrics

MCP server providing tools for Obsidian vault access and agent performance metrics.

## Tools

| Tool | Description |
|------|-------------|
| `vault_status` | Read STATUS.md for a project → structured JSON |
| `vault_search` | Search daily logs across projects |
| `vault_dashboard` | Read DASHBOARD.md → cross-project overview |
| `agent_metrics` | Query metrics.jsonl → success rates, trends |
| `failure_patterns` | Read failures.jsonl → top failure patterns |

## Setup

### 1. Install dependencies

```bash
cd ~/agents/mcp-server
pip install -e .
```

### 2. Configure Claude Code

Add to `~/.claude/settings.local.json`:

```json
{
  "mcpServers": {
    "vault-metrics": {
      "command": "python3",
      "args": ["/home/YOUR_USER/agents/mcp-server/server.py", "--mcp"]
    }
  }
}
```

### 3. Set vault path

```bash
export OBSIDIAN_VAULT_PATH=~/path/to/your/vault
```

## Standalone Usage (Testing)

```bash
# List tools
python3 server.py --help

# Query vault dashboard
python3 server.py vault_dashboard

# Get project status
python3 server.py vault_status '{"project": "VE-RAG"}'

# Search logs
python3 server.py vault_search '{"query": "auth", "project": "VE-RAG"}'

# Agent metrics
python3 server.py agent_metrics '{"period": "30d"}'

# Failure patterns
python3 server.py failure_patterns
```
