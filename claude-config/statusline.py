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
    CYAN = "\033[36m"
    RESET = "\033[0m"

    # Server name from hostname (blue)
    hostname = socket.gethostname().split(".")[0].upper()
    server = f"{BLUE}{hostname}{RESET}"

    # Get username (pink)
    username = f"{PINK}{getpass.getuser()}{RESET}"

    # Current working directory, home-relative (cyan)
    import os

    home = os.path.expanduser("~")
    cwd_raw = os.getcwd()
    cwd_display = "~" + cwd_raw[len(home) :] if cwd_raw.startswith(home) else cwd_raw
    cwd = f"{CYAN}{cwd_display}{RESET}"

    # Agent name (orange) — from .mcp.json in cwd, agent config, or env
    agent_name = (
        input_data.get("agent", {}).get("name") or os.environ.get("AGENT_NAME") or ""
    )
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

    # Rate-limit ambient display — only shown when >= 70% of a quota window is used.
    # Suppressed entirely when rate_limits is absent (older CC, API key users).
    rate_segments = []
    try:
        rate_limits = input_data.get("rate_limits")
        if isinstance(rate_limits, dict):
            windows = [
                ("5h", rate_limits.get("fiveHour")),
                ("7d", rate_limits.get("sevenDay")),
            ]
            for label, window in windows:
                if not isinstance(window, dict):
                    continue
                pct = window.get("used_percentage")
                if not isinstance(pct, (int, float)):
                    continue
                if pct < 70:
                    continue
                # Pick color by threshold
                rl_color = RED if pct >= 90 else ORANGE
                # Append reset time (HH:MM local) when critical
                resets_at = window.get("resets_at")
                reset_str = ""
                if pct >= 90 and isinstance(resets_at, str):
                    try:
                        reset_dt = datetime.fromisoformat(
                            resets_at.replace("Z", "+00:00")
                        )
                        reset_local = reset_dt.astimezone()
                        reset_str = f"@{reset_local.strftime('%H:%M')}"
                    except Exception:
                        pass
                rate_segments.append(f"{rl_color}{pct:.1f}%{reset_str} {label}{RESET}")
    except Exception:
        pass  # Never crash statusline on malformed rate_limits data

    rate_display = (" | " + " ".join(rate_segments)) if rate_segments else ""

    # Build status line
    status_line = f"{server} | {username} | {cwd} | {current_date} | {context_display} ctx{rate_display}{agent_display}"

    print(status_line)


if __name__ == "__main__":
    main()
