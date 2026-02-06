#!/usr/bin/env python3
import json
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
    RESET = "\033[0m"

    # Server name simplified to DELLPRO (blue)
    server = f"{BLUE}DELLPRO{RESET}"

    # Get username (pink)
    username = f"{PINK}{getpass.getuser()}{RESET}"

    # Get current date in MM/DD format (orange)
    current_date = f"{ORANGE}{datetime.now().strftime('%m/%d')}{RESET}"

    # Get context used percentage (green)
    context_window = input_data.get("context_window", {})
    used_percentage = context_window.get("used_percentage")

    # Format context display
    if used_percentage is not None:
        context_display = f"{GREEN}{used_percentage:.1f}%{RESET}"
    else:
        context_display = f"{GREEN}0.0%{RESET}"

    # Build status line
    status_line = f"{server} | {username} | {current_date} | {context_display} ctx"

    print(status_line)

if __name__ == "__main__":
    main()
