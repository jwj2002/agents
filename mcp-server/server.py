#!/usr/bin/env python3
"""
Claude MCP Server — Vault Access & Agent Metrics

Provides tools for querying Obsidian vault state and agent performance data.

Usage:
    python3 server.py                    # Start server (stdio transport)
    python3 server.py --help             # Show help

Configure in ~/.claude/settings.local.json:
    "mcpServers": {
        "vault-metrics": {
            "command": "python3",
            "args": ["~/agents/mcp-server/server.py"]
        }
    }
"""
from __future__ import annotations

import json
import sys

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

from tools.vault_status import vault_status
from tools.vault_search import vault_search
from tools.vault_dashboard import vault_dashboard
from tools.agent_metrics import agent_metrics
from tools.failure_patterns import failure_patterns


TOOLS = {
    "vault_status": {
        "fn": vault_status,
        "description": "Read project STATUS.md from Obsidian vault. Returns structured data with status, next steps, blockers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project name (folder name under vault/Projects/)"},
            },
            "required": ["project"],
        },
    },
    "vault_search": {
        "fn": vault_search,
        "description": "Search daily logs in Obsidian vault for a query string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for (case-insensitive)"},
                "project": {"type": "string", "description": "Optional project name to scope search"},
            },
            "required": ["query"],
        },
    },
    "vault_dashboard": {
        "fn": vault_dashboard,
        "description": "Read DASHBOARD.md or scan Projects/ directory for a cross-project overview.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "agent_metrics": {
        "fn": agent_metrics,
        "description": "Query agent performance metrics from metrics.jsonl. Returns success rates, breakdowns, trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "Time period: '7d', '30d', '90d', or 'all'", "default": "30d"},
                "project": {"type": "string", "description": "Optional project path"},
            },
        },
    },
    "failure_patterns": {
        "fn": failure_patterns,
        "description": "Read failures.jsonl and return top failure patterns grouped by root cause.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Optional project path"},
            },
        },
    },
}


def run_standalone():
    """Run tools directly without MCP (for testing)."""
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print("Available tools:")
        for name, tool in TOOLS.items():
            print(f"  {name}: {tool['description'][:80]}")
        print("\nUsage: python3 server.py <tool_name> [json_args]")
        print("Example: python3 server.py vault_dashboard")
        print("Example: python3 server.py vault_status '{\"project\": \"VE-RAG\"}'")
        return

    tool_name = sys.argv[1]
    if tool_name not in TOOLS:
        print(f"Unknown tool: {tool_name}")
        sys.exit(1)

    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = TOOLS[tool_name]["fn"](**args)
    print(json.dumps(result, indent=2))


async def run_mcp():
    """Run as MCP server."""
    server = Server("vault-metrics")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name=name,
                description=tool["description"],
                inputSchema=tool["input_schema"],
            )
            for name, tool in TOOLS.items()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name not in TOOLS:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        result = TOOLS[name]["fn"](**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    if not HAS_MCP or (len(sys.argv) > 1 and sys.argv[1] != "--mcp"):
        run_standalone()
    else:
        import asyncio
        asyncio.run(run_mcp())
