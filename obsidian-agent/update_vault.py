#!/usr/bin/env python3
"""Backward-compatible entry point.

Preferred usage: python -m obsidian_agent [args]
"""
import sys
from pathlib import Path

# Ensure the package is importable when running as a script
sys.path.insert(0, str(Path(__file__).parent))

from obsidian_agent.__main__ import main

if __name__ == "__main__":
    main()
