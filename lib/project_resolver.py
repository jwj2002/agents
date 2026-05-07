"""Project name resolution + registration + per-machine subscriptions.

Tool-agnostic. Used by `action/cli.py`, `project/cli.py`, and any future
CLI that needs to resolve a project name from cwd / --project flag and
manage `~/.claude/dashboard-subscriptions.json`.

Public API:
- resolve_from_cwd() -> str | None
- list_known_projects() -> list[str]
- project_yaml_path(name) -> Path
- project_dir_exists(name) -> bool
- read_subscriptions() -> list[str]
- add_subscription(name) / remove_subscription(name)
- register_project(name, owner='jason') -> Path  (writes default YAML)
- interactive_pick(candidates, header) -> str  (TTY)
- resolve_with_picker(name, no_prompt=False) -> str  (combined resolver)

All failure modes raise ProjectResolutionError; callers translate to
their own user-facing error type.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HOME = Path.home()
KNOWLEDGE_PROJECTS_DIR = HOME / "agents" / "knowledge" / "projects"
SUBSCRIPTIONS_PATH = HOME / ".claude" / "dashboard-subscriptions.json"


class ProjectResolutionError(Exception):
    """Raised when a project name can't be resolved or is unknown."""


# ---------- cwd resolution ----------

def resolve_from_cwd() -> str | None:
    """Infer project name from current working directory. None if no inference.

    Convention: ~/agents → "agents"; ~/projects/<name>/... → <name>.
    Skips ~/projects/_archived/* (archived clones don't represent active
    projects).
    """
    cwd = Path.cwd().resolve()
    agents_dir = HOME / "agents"
    projects_dir = HOME / "projects"
    if cwd == agents_dir or agents_dir in cwd.parents:
        return "agents"
    if projects_dir in cwd.parents:
        first = cwd.relative_to(projects_dir).parts[0]
        if first == "_archived":
            return None
        return first
    return None


# ---------- YAML registry ----------

def project_yaml_path(name: str) -> Path:
    return KNOWLEDGE_PROJECTS_DIR / f"{name}.yaml"


def project_dir_exists(name: str) -> bool:
    """Return True if a local repo directory exists for this project name."""
    if name == "agents":
        return (HOME / "agents").is_dir()
    return (HOME / "projects" / name).is_dir()


def list_known_projects() -> list[str]:
    """All registered project YAMLs, filtered by this machine's subscriptions if non-empty.

    Falls back to all registered yamls if subscriptions file is missing or empty.
    """
    if not KNOWLEDGE_PROJECTS_DIR.exists():
        return []
    all_registered = sorted(p.stem for p in KNOWLEDGE_PROJECTS_DIR.glob("*.yaml"))
    subs = read_subscriptions()
    if not subs:
        return all_registered
    filtered = [p for p in all_registered if p in subs]
    return filtered if filtered else all_registered


def register_project(name: str, owner: str = "jason") -> Path:
    """Write a default YAML to knowledge/projects/<name>.yaml + subscribe this machine.

    Raises FileExistsError if YAML already exists. Returns the YAML path.
    """
    yaml_path = project_yaml_path(name)
    if yaml_path.exists():
        raise FileExistsError(f"project yaml already exists: {yaml_path}")
    today_str = date.today().isoformat()
    content = (
        f"schema_version: 1\n"
        f"project: {name}\n"
        f"status: active\n"
        f'focus: ""\n'
        f"next_steps: []\n"
        f"blockers: []\n"
        f"open_questions: []\n"
        f"specs: []\n"
        f"dependencies: []\n"
        f'updated_at: "{today_str}"\n'
        f"updated_by: {owner}\n"
    )
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(content)
    add_subscription(name)
    return yaml_path


# ---------- subscriptions ----------

def read_subscriptions() -> list[str]:
    """Read subscribed project names. Returns [] on missing / malformed / empty."""
    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text())
        subs = data.get("subscribed", [])
        return [s for s in subs if isinstance(s, str)]
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return []


def add_subscription(name: str) -> None:
    """Append name to dashboard-subscriptions.json, creating the file if absent. Idempotent."""
    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    subs: list[str] = data.get("subscribed", []) if isinstance(data.get("subscribed"), list) else []
    if name not in subs:
        subs.append(name)
    data["subscribed"] = subs
    SUBSCRIPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIPTIONS_PATH.write_text(json.dumps(data, indent=2) + "\n")


def remove_subscription(name: str) -> None:
    """Drop name from dashboard-subscriptions.json. No-op if name absent or file missing."""
    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    subs: list[str] = data.get("subscribed", []) if isinstance(data.get("subscribed"), list) else []
    if name in subs:
        subs.remove(name)
    data["subscribed"] = subs
    SUBSCRIPTIONS_PATH.write_text(json.dumps(data, indent=2) + "\n")


# ---------- interactive picker ----------

def interactive_pick(candidates: list[str], header: str) -> str:
    """Print numbered menu, prompt for 1-based selection.

    Reprompts up to 3 times on out-of-range or non-numeric input.
    Raises ProjectResolutionError on Ctrl-C, EOF, blank input, or exhausted retries.
    """
    print(header)
    for i, name in enumerate(candidates, 1):
        print(f"  {i}) {name}")
    for attempt in range(3):
        try:
            raw = input(f"Enter number (1-{len(candidates)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ProjectResolutionError("project selection cancelled")
        if not raw:
            raise ProjectResolutionError("project selection cancelled")
        try:
            choice = int(raw)
        except ValueError:
            if attempt < 2:
                print(f"  invalid input — enter a number between 1 and {len(candidates)}")
                continue
            raise ProjectResolutionError("too many invalid inputs — project selection aborted")
        if 1 <= choice <= len(candidates):
            return candidates[choice - 1]
        if attempt < 2:
            print(f"  out of range — enter a number between 1 and {len(candidates)}")
        else:
            raise ProjectResolutionError("too many invalid inputs — project selection aborted")
    raise ProjectResolutionError("too many invalid inputs — project selection aborted")


# ---------- combined resolver ----------

def resolve_with_picker(name: str | None, *, no_prompt: bool = False) -> str:
    """Resolve a project name via cwd / explicit name / picker, with auto-register on first use.

    Validation order:
      1. If `name` is None: try cwd inference → return; else picker (TTY) or error.
      2. If `name` matches a known project → return.
      3. If `name` matches a local repo dir → auto-register + return.
      4. Otherwise picker (TTY) or error with helpful pointer.

    Raises ProjectResolutionError on any failure path.
    """
    if not name:
        cwd_name = resolve_from_cwd()
        if cwd_name is not None:
            return cwd_name
        if sys.stdin.isatty() and not no_prompt:
            return interactive_pick(list_known_projects(), "no project resolved. Pick one:")
        raise ProjectResolutionError(
            "no project resolved — pass --project <name> or run from inside the project directory"
        )

    known = list_known_projects()
    if name in known:
        return name

    if project_dir_exists(name):
        register_project(name)
        print(f'registered new project "{name}" on this machine')
        return name

    if sys.stdin.isatty() and not no_prompt:
        return interactive_pick(known, f'unknown project "{name}". Pick one:')

    subs = read_subscriptions()
    subscribed_str = ", ".join(subs) if subs else "(none)"
    raise ProjectResolutionError(
        f'unknown project "{name}"\n'
        f"  - not registered (knowledge/projects/{name}.yaml missing)\n"
        f"  - no repo at ~/projects/{name}/\n"
        f"  To add: clone the repo to ~/projects/{name}, or register manually.\n"
        f"  Subscribed on this machine: {subscribed_str}"
    )
