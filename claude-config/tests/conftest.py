"""Pytest config — make `hooks/` importable as a top-level module."""

from __future__ import annotations

import sys
from pathlib import Path

# Put hooks/ on sys.path so `from state_manager import ...` works the same
# way `python3 -c 'import state_manager'` does from the orchestrator
# command (which prepends `$HOME/.claude/hooks`).
_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
