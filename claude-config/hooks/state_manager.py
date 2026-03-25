#!/usr/bin/env python3
"""
Centralized state manager for PERSISTENT_STATE.yaml.

Used by: orchestrate command (inline), precompact hook, sessionstart hook.
Single source of truth for reading/writing orchestrate workflow state.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

_log_file = Path.home() / ".claude" / "hooks.log"
logging.basicConfig(
    filename=str(_log_file),
    level=logging.WARNING,
    format="%(asctime)s [state_manager] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _state_path(project_dir: Path) -> Path:
    return project_dir / ".agents" / "outputs" / "claude_checkpoints" / "PERSISTENT_STATE.yaml"


def load_state(project_dir: Path) -> dict:
    """Read PERSISTENT_STATE.yaml and return its contents as a dict."""
    if not HAS_YAML:
        return {}
    path = _state_path(project_dir)
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logging.warning(f"Failed to load state: {e}")
        return {}


def _write_state(project_dir: Path, data: dict) -> None:
    """Write state dict back to PERSISTENT_STATE.yaml."""
    if not HAS_YAML:
        return
    path = _state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def update_phase(project_dir: Path, issue: int, branch: str, phase: str, action: str) -> None:
    """Update active_work with current phase. Tracks completed phases for --resume."""
    data = load_state(project_dir)
    active = data.get("active_work", {})

    # Track the previous phase as completed (if transitioning)
    prev_phase = active.get("phase")
    completed = active.get("completed_phases", [])
    if prev_phase and prev_phase != phase and prev_phase not in completed:
        completed.append(prev_phase)

    data["active_work"] = {
        "issue": issue,
        "branch": branch,
        "phase": phase,
        "last_action": action,
        "completed_phases": completed,
    }

    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["updated"] = datetime.now().strftime("%Y-%m-%d")

    _write_state(project_dir, data)


def clear_active(project_dir: Path, issue: int) -> None:
    """Clear active workflow state after successful completion."""
    data = load_state(project_dir)
    data["active_work"] = {
        "issue": None,
        "branch": "main",
        "phase": None,
        "last_action": f"Completed issue #{issue}",
        "completed_phases": [],
    }

    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["updated"] = datetime.now().strftime("%Y-%m-%d")

    _write_state(project_dir, data)


def get_completed_phases(project_dir: Path, issue: int) -> list[str]:
    """Get list of completed phases for an issue. Used by --resume."""
    data = load_state(project_dir)
    active = data.get("active_work", {})
    if active.get("issue") != issue:
        return []
    return active.get("completed_phases", [])


def get_active_work(project_dir: Path) -> dict:
    """Get the active_work section. Used by sessionstart hook."""
    data = load_state(project_dir)
    return data.get("active_work", {})


def update_from_extracted(project_dir: Path, extracted: dict) -> None:
    """Update state from precompact transcript extraction."""
    data = load_state(project_dir)

    if "active_work" not in data:
        data["active_work"] = {}

    if extracted.get("last_issue"):
        data["active_work"]["issue"] = extracted["last_issue"]
    if extracted.get("last_phase"):
        data["active_work"]["phase"] = extracted["last_phase"]
    if extracted.get("artifacts_created"):
        data["active_work"]["last_action"] = f"Created {extracted['artifacts_created'][-1]}"

    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["updated"] = datetime.now().strftime("%Y-%m-%d")

    _write_state(project_dir, data)
