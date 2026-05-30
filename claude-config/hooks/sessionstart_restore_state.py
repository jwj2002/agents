#!/usr/bin/env python3
"""
Claude Code SessionStart hook (Optimized v2):
- Loads compact YAML state (~300 tokens vs ~650)
- Loads critical patterns only (~200 tokens vs ~2600)
- Detects active orchestrate workflow and provides continue instructions
- Total: ~500 tokens vs ~3250 (85% reduction)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# File-based error logging
_log_file = Path.home() / ".claude" / "hooks.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)


def _rotate_log_if_oversize(max_bytes: int = 10 * 1024 * 1024) -> None:
    """Rotate hooks.log if it exceeds max_bytes (default 10 MB).

    Keeps one rotated copy at hooks.log.1; older copies are discarded.
    Runs once per session via SessionStart so the cost is negligible.
    """
    try:
        if not _log_file.exists() or _log_file.stat().st_size <= max_bytes:
            return
        rotated = _log_file.with_suffix(_log_file.suffix + ".1")
        if rotated.exists():
            rotated.unlink()
        _log_file.rename(rotated)
    except Exception:
        # Never let log rotation break session startup.
        pass


_rotate_log_if_oversize()

logging.basicConfig(
    filename=str(_log_file),
    level=logging.WARNING,
    format="%(asctime)s [sessionstart] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Try to import centralized state manager
try:
    from state_manager import get_active_work as _sm_get_active_work
    HAS_STATE_MANAGER = True
except ImportError:
    HAS_STATE_MANAGER = False


def get_active_work(yaml_content: str) -> dict:
    """Extract active_work from YAML content (fallback when state_manager unavailable)."""
    if not HAS_YAML:
        return {}
    try:
        data = yaml.safe_load(yaml_content)
        return data.get("active_work", {}) if data else {}
    except Exception as e:
        logging.warning(f"Failed to parse YAML state: {e}", exc_info=True)
        return {}


def main() -> int:
    _hook_in = json.load(sys.stdin)

    # 0. Pull latest agent shards (fail-open — divergence warns but does not abort session).
    _agents_root = Path.home() / "agents"
    if _agents_root.is_dir():
        try:
            _pull = subprocess.run(
                ["git", "-C", str(_agents_root), "pull", "--ff-only", "--quiet"],
                capture_output=True,
                timeout=10,
            )
            if _pull.returncode != 0:
                logging.warning(
                    "git pull --ff-only failed on agents repo — shards may be stale. "
                    "Resolve with: git -C ~/agents pull --ff-only"
                )
                print(
                    "**Advisory**: agents repo diverged from origin — "
                    "run `git -C ~/agents pull --ff-only` to sync latest shards.\n"
                )
            else:
                # Pull succeeded — check whether the telemetry gate is tripped.
                _gate_script = _agents_root / "claude-config" / "scripts" / "telemetry_gate.py"
                if _gate_script.exists():
                    try:
                        _gate = subprocess.run(
                            ["python3", str(_gate_script), "--verbose"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if _gate.returncode == 0:  # gate tripped
                            _gate_msg = _gate.stdout.strip() or "gate tripped"
                            print(f"**Advisory**: /learn gate tripped — {_gate_msg}\n")
                    except Exception as _gate_exc:
                        logging.warning(f"telemetry_gate check failed (non-fatal): {_gate_exc}")
        except (subprocess.TimeoutExpired, OSError, Exception) as _pull_exc:
            logging.warning(f"git pull --ff-only failed (non-fatal): {_pull_exc}")

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    global_claude_dir = Path.home() / ".claude"
    checkpoints_dir = project_dir / ".agents" / "outputs" / "claude_checkpoints"
    project_memory_dir = project_dir / ".claude" / "memory"
    global_memory_dir = global_claude_dir / "memory"

    print("## Restored Context\n")

    # 1. Load compact YAML state (preferred) or fallback to markdown
    yaml_state = checkpoints_dir / "PERSISTENT_STATE.yaml"
    md_state = checkpoints_dir / "PERSISTENT_STATE.md"

    active_work = {}
    if yaml_state.exists():
        yaml_content = yaml_state.read_text(encoding="utf-8")
        if HAS_STATE_MANAGER:
            active_work = _sm_get_active_work(project_dir)
        else:
            active_work = get_active_work(yaml_content)
        print("### Project State\n")
        print("```yaml")
        print(yaml_content)
        print("```\n")
    elif md_state.exists():
        print("### Project State\n")
        print(md_state.read_text(encoding="utf-8"))
        print()

    # 2. Load critical patterns (project-specific first, then global fallback)
    patterns_critical = project_memory_dir / "patterns-critical.md"
    if not patterns_critical.exists():
        patterns_critical = global_memory_dir / "patterns-critical.md"

    if patterns_critical.exists():
        print("### Critical Patterns (Always Apply)\n")
        print(patterns_critical.read_text(encoding="utf-8"))
        print()
    else:
        # Fallback: try reading rules/core-patterns.md (canonical source)
        core_patterns = global_claude_dir / "rules" / "core-patterns.md"
        if core_patterns.exists():
            print("### Critical Patterns (Always Apply)\n")
            print(core_patterns.read_text(encoding="utf-8"))
            print()
        else:
            # Last resort: minimal inline reminder
            print("### Critical Patterns\n")
            print("1. **VERIFICATION_GAP**: Read spec/code before assuming")
            print("2. **ENUM_VALUE**: Use VALUES not Python names (CO-OWNER not CO_OWNER)")
            print("3. **COMPONENT_API**: Read PropTypes before using components")
            print()
            print("Full patterns: `.claude/memory/patterns-full.md`\n")

    # 3. Check for active orchestrate workflow and provide continue instructions
    issue = active_work.get("issue")
    phase = active_work.get("phase")
    branch = active_work.get("branch")

    if issue and phase:
        print("### ACTIVE ORCHESTRATE WORKFLOW\n")
        print(f"**Issue**: #{issue}")
        print(f"**Phase**: {phase}")
        print(f"**Branch**: {branch}")
        print()
        print("**CRITICAL**: You were in the middle of an orchestrate workflow.")
        print("Continue with the current phase using the Task tool:")
        print()
        print("1. Read `.claude/commands/orchestrate.md` for phase instructions")
        print("2. Check for existing artifacts in `.agents/outputs/`")
        print(f"3. Continue the `{phase}` phase for issue #{issue}")
        print()
        print("If the phase was completed, proceed to the next phase in the workflow.")
        print()

    # 4. Hint about full patterns location
    print("---")
    print("*Full patterns available at `.claude/memory/patterns-full.md` if needed.*\n")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
