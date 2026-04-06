#!/usr/bin/env python3
import json
import socket
import sys
import getpass
from datetime import datetime

def main():
    # Read JSON input from stdin
    input_data = json.load(sys.stdin)

    # ANSI color codes
    BLUE = "\033[34m"
    PINK = "\033[95m"
    ORANGE = "\033[38;5;214m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    RESET = "\033[0m"

    # Server name from hostname (blue)
    hostname = socket.gethostname().split(".")[0].upper()
    server = f"{BLUE}{hostname}{RESET}"

    # Get username (pink)
    username = f"{PINK}{getpass.getuser()}{RESET}"

    # Agent name (orange) — from .mcp.json in cwd, agent config, or env
    import os
    agent_name = input_data.get("agent", {}).get("name") or os.environ.get("AGENT_NAME") or ""
    if not agent_name:
        try:
            mcp_path = os.path.join(os.getcwd(), ".mcp.json")
            with open(mcp_path) as f:
                mcp = json.load(f)
            for srv in mcp.get("mcpServers", {}).values():
                agent_name = srv.get("env", {}).get("AGENT_NAME", "")
                if agent_name:
                    break
        except Exception:
            pass
    agent_display = f" | {ORANGE}{agent_name}{RESET}" if agent_name else ""

    # Get current date in MM/DD format (orange)
    current_date = f"{ORANGE}{datetime.now().strftime('%m/%d')}{RESET}"

    # Get context used percentage (green)
    context_window = input_data.get("context_window", {})
    used_percentage = context_window.get("used_percentage")

    # Format context display (red when >75% — compaction danger zone)
    if used_percentage is not None:
        ctx_color = RED if used_percentage > 75 else GREEN
        context_display = f"{ctx_color}{used_percentage:.1f}%{RESET}"
    else:
        context_display = f"{GREEN}0.0%{RESET}"

    # Build status line
    status_line = f"{server} | {username} | {current_date} | {context_display} ctx{agent_display}"

    print(status_line)

if __name__ == "__main__":
    main()
