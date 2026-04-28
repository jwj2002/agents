# MCP Servers

Model Context Protocol (MCP) servers extend Claude Code with external tools. Instead of relying on file reads alone, agents can call structured tool APIs that return JSON data from Obsidian vaults, library documentation services, and platform integrations.

## What Is MCP

MCP is a protocol that lets AI agents call external tools over a standardized interface. Each MCP server exposes named tools with typed parameters and structured responses. Claude Code discovers these tools at startup and makes them available alongside built-in tools like Read, Edit, and Bash.

The practical benefit: agents get structured data instead of parsing markdown files. An MCP call to `failure_patterns()` returns JSON with root cause codes, frequencies, and prevention steps. A file read of `patterns-critical.md` returns unstructured text that the agent must interpret.

## Configured Servers

MCP servers are registered at user scope by `claude-config/install.sh` using `claude mcp add --scope user`, which writes to `~/.claude.json`. This is per-machine config — not committed to the repo and not symlinked.

The installer registers four servers (apple-mcp on macOS only). Each subsection below shows the registration command the installer runs.

### knowledge

A TypeScript MCP server that exposes the local knowledge graph (patterns, decisions, project state) over MCP. Backed by `knowledge-mcp/index.ts` running under tsx.

```bash
claude mcp add --scope user knowledge -- \
  ~/agents/knowledge-mcp/node_modules/.bin/tsx \
  ~/agents/knowledge-mcp/index.ts
```

Requires `npm install` in `~/agents/knowledge-mcp/` (handled by install.sh on first run).

### vault-metrics

A custom Python server that provides access to the Obsidian vault and `.claude/memory/` files.

```bash
claude mcp add --scope user vault-metrics -- \
  ~/agents/mcp-server/.venv/bin/python \
  ~/agents/mcp-server/server.py
```

Runs in a dedicated venv (`mcp-server/.venv/`) created by install.sh Phase 2.

**Tools provided**:

| Tool | Description |
|------|-------------|
| `vault_status` | Current project status from Obsidian vault |
| `vault_search` | Search across vault content |
| `vault_dashboard` | Cross-project overview |
| `agent_metrics` | Performance metrics from `metrics.jsonl` (supports time ranges) |
| `failure_patterns` | Learned failure patterns with root causes and prevention steps |

### context7

Injects current library documentation into agent context. This eliminates stale API hallucinations — when an agent needs to use a library method, context7 provides the current docs instead of relying on training data that may be outdated.

```bash
claude mcp add --scope user context7 -- \
  npx -y @upstash/context7-mcp@latest
```

### apple-mcp

macOS platform integration providing access to system features like Calendar, Contacts, Notes, and Reminders.

```bash
claude mcp add --scope user apple-mcp -- \
  npx -y apple-mcp@latest
```

Skipped on non-macOS platforms.

## MCP-First Pattern Loading

Agents use MCP tools as the preferred source for failure patterns during pre-flight. File reads serve as a fallback when MCP is unavailable.

```
+---------------------+     +--------------------------+
|  Agent Pre-Flight   |---->|  MCP: failure_patterns() |
|                     |     |  MCP: agent_metrics(30d) |
|  (all agents via    |     +----------+---------------+
|   _base.md)         |                | fails?
|                     |                v
|                     |     +--------------------------+
|                     |---->|  File: patterns-critical |
|                     |     |  File: patterns-full.md  |
+---------------------+     +--------------------------+
```

**Why MCP-first**: The `failure_patterns()` tool returns structured JSON with root cause codes, frequencies, and prevention steps. This is more reliable than parsing a markdown file, and the MCP server can aggregate data from multiple sources (vault + memory files) in a single call.

!!! example "Sample `failure_patterns()` response"
    ```json
    {
      "patterns": [
        {
          "root_cause": "ENUM_VALUE",
          "frequency": 26,
          "description": "Frontend uses Python enum NAME instead of VALUE",
          "prevention": "CONTRACT must document enum VALUES explicitly"
        },
        {
          "root_cause": "VERIFICATION_GAP",
          "frequency": 63,
          "description": "Agent assumed API shape without reading source",
          "prevention": "Read actual source file before using any component"
        }
      ],
      "period": "last_30_days",
      "total_failures": 12
    }
    ```

## Adding a New MCP Server

To add a new MCP server:

1. **Implement the server** following the MCP protocol specification. The server must handle tool discovery and tool execution requests.

2. **Register the server** with Claude Code:

    ```bash
    claude mcp add --scope user my-server -- python3 /path/to/my_server.py
    ```

3. **Restart Claude Code** to pick up the new server. MCP servers are discovered at session start.

4. **Test the tools** by asking Claude Code to list available MCP tools or by calling one directly.

!!! tip "Project vs User Servers"
    Use user-scope registration for personal machine tooling. Use project `.mcp.json` only when a repo should share an MCP server definition with collaborators.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| MCP tools not appearing | Restart Claude Code; check that the server command is in PATH |
| Server crashes at startup | Run the command manually to see error output |
| `failure_patterns()` returns empty | Verify `.claude/memory/failures.jsonl` exists and has data |
| context7 slow on first call | Normal -- `npx` downloads the package on first run |
