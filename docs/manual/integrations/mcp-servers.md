# MCP Servers

Model Context Protocol (MCP) servers extend Claude Code with external tools. Instead of relying on file reads alone, agents can call structured tool APIs that return JSON data from Obsidian vaults, library documentation services, and platform integrations.

## What Is MCP

MCP is a protocol that lets AI agents call external tools over a standardized interface. Each MCP server exposes named tools with typed parameters and structured responses. Claude Code discovers these tools at startup and makes them available alongside built-in tools like Read, Edit, and Bash.

The practical benefit: agents get structured data instead of parsing markdown files. An MCP call to `failure_patterns()` returns JSON with root cause codes, frequencies, and prevention steps. A file read of `patterns-critical.md` returns unstructured text that the agent must interpret.

## Configured Servers

Three MCP servers are configured in `settings.json`:

### vault-metrics

A custom Python server that provides access to the Obsidian vault and `.claude/memory/` files.

```json
{
  "vault-metrics": {
    "command": "python3",
    "args": ["~/agents/mcp-server/server.py", "--mcp"]
  }
}
```

**Tools provided**:

| Tool | Description |
|------|-------------|
| `vault_status` | Current project status from Obsidian vault |
| `vault_search` | Search across vault content |
| `vault_dashboard` | Cross-project overview |
| `agent_metrics` | Performance metrics from `metrics.jsonl` (supports time ranges) |
| `failure_patterns` | Learned failure patterns with root causes and prevention steps |

!!! note "Machine-Local Configuration"
    The vault-metrics server path varies by machine. Configure it in `settings.local.json` (not symlinked) rather than `settings.json` (symlinked) when the path differs across machines.

### context7

Injects current library documentation into agent context. This eliminates stale API hallucinations -- when an agent needs to use a library method, context7 provides the current docs instead of relying on training data that may be outdated.

```json
{
  "context7": {
    "command": "npx",
    "args": ["-y", "@upstash/context7-mcp@latest"]
  }
}
```

### apple-mcp

macOS platform integration providing access to system features like Calendar, Contacts, and other Apple services.

```json
{
  "apple-mcp": {
    "command": "bunx",
    "args": ["--no-cache", "apple-mcp@latest"]
  }
}
```

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

## settings.json Configuration

All MCP servers are configured under the `mcpServers` key in `settings.json`:

```json
{
  "mcpServers": {
    "vault-metrics": {
      "command": "python3",
      "args": ["~/agents/mcp-server/server.py", "--mcp"]
    },
    "apple-mcp": {
      "command": "bunx",
      "args": ["--no-cache", "apple-mcp@latest"]
    },
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    }
  }
}
```

Each server entry specifies:

| Field | Description |
|-------|-------------|
| `command` | The executable to run (e.g., `python3`, `npx`, `bunx`) |
| `args` | Arguments passed to the command |

Claude Code starts each MCP server as a subprocess at session start and communicates with it over the MCP protocol.

## Adding a New MCP Server

To add a new MCP server:

1. **Implement the server** following the MCP protocol specification. The server must handle tool discovery and tool execution requests.

2. **Add the entry** to `settings.json` (or `settings.local.json` for machine-specific servers):

    ```json
    {
      "mcpServers": {
        "my-server": {
          "command": "python3",
          "args": ["/path/to/my_server.py", "--mcp"]
        }
      }
    }
    ```

3. **Restart Claude Code** to pick up the new server. MCP servers are discovered at session start.

4. **Test the tools** by asking Claude Code to list available MCP tools or by calling one directly.

!!! tip "Local vs Global Servers"
    Use `settings.json` (symlinked, version-controlled) for servers that work on all machines. Use `settings.local.json` (not symlinked, machine-specific) for servers with paths that vary by machine.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| MCP tools not appearing | Restart Claude Code; check that the server command is in PATH |
| Server crashes at startup | Run the command manually to see error output |
| `failure_patterns()` returns empty | Verify `.claude/memory/failures.jsonl` exists and has data |
| context7 slow on first call | Normal -- `npx` downloads the package on first run |
