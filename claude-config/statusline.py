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

    # Agent name (orange) — from .mcp.json in cwd, agent config, or env. While
    # parsing .mcp.json, also note the channel server's CHANNEL_ENV_FILE (an
    # ai-channels profile) so the connected channel can be shown below.
    agent_name = (
        input_data.get("agent", {}).get("name") or os.environ.get("AGENT_NAME") or ""
    )
    channel_env_file = os.environ.get("CHANNEL_ENV_FILE", "")
    try:
        mcp_path = os.path.join(os.getcwd(), ".mcp.json")
        with open(mcp_path) as f:
            mcp = json.load(f)
        for srv in mcp.get("mcpServers", {}).values():
            env = srv.get("env", {})
            if not agent_name:
                agent_name = env.get("AGENT_NAME", "")
            if not channel_env_file:
                channel_env_file = env.get("CHANNEL_ENV_FILE", "")
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

    # ai-channels: show the connected channel (📡). Prefer an explicit
    # AI_CHANNELS_CHANNEL env var; otherwise read CHANNEL= from the profile the
    # session's channel MCP server points at (CHANNEL_ENV_FILE, captured above).
    channel = os.environ.get("AI_CHANNELS_CHANNEL", "")
    if not channel and channel_env_file:
        try:
            with open(os.path.expanduser(channel_env_file)) as f:
                for line in f:
                    if line.startswith("CHANNEL="):
                        channel = line.split("=", 1)[1].strip().strip("\"'")
                        break
        except Exception:
            pass
    channel_display = f" | {GREEN}📡 {channel}{RESET}" if channel else ""

    # Build status line
    status_line = f"{server} | {username} | {cwd} | {current_date} | {context_display} ctx{rate_display}{agent_display}{channel_display}"

    print(status_line)


if __name__ == "__main__":
    main()
