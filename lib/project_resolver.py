"""Project name resolution + registration + per-machine subscriptions + host name.

Tool-agnostic. Used by `action/cli.py`, `project/cli.py`, `decision/cli.py`,
and any future CLI that needs to resolve a project name from cwd / --project
flag and manage `~/.claude/dashboard-subscriptions.json`.

Public API (legacy, retained):
- resolve_from_cwd() -> str | None
- list_known_projects() -> list[str]
- project_yaml_path(name) -> Path
- project_dir_exists(name) -> bool
- read_subscriptions() -> list[str]
- add_subscription(name) / remove_subscription(name)
- get_host_name() -> str  (reads ~/.claude/host-name, falls back to gethostname)
- set_host_name(name) -> None  (writes the file)
- register_project(name, owner='jason', host=None) -> Path  (writes default YAML)
- interactive_pick(candidates, header) -> str  (TTY)
- resolve_with_picker(name, no_prompt=False) -> str  (combined resolver)

Public API (Path B vault-aware additions):
- read_subscriptions_dict() -> dict[vault, {subscribed, ssh_writes}]
- write_subscriptions_dict(data) — atomic write, vault-keyed format
- resolve_vault_for_project(name) -> str
- vault_path(vault) / project_md_path(name, vault=None) /
  decision_md_path(decision_id, vault)
- add_subscription_to_vault(vault, name) / remove_subscription_from_vault(vault, name)
- claim_ssh_host(vault, host) / release_ssh_host(vault, host)
- default_vault() -> str

The subscription file supports two on-disk shapes during the Path B
transition: the legacy flat ``{"subscribed": [...]}`` and the new
``{<vault>: {"subscribed": [...], "ssh_writes": [...]}}``. Legacy ops
preserve the legacy shape; vault-aware ops migrate it on first write.

All failure modes raise ProjectResolutionError; callers translate to
their own user-facing error type.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from datetime import date
from pathlib import Path

HOME = Path.home()
KNOWLEDGE_PROJECTS_DIR = HOME / "agents" / "knowledge" / "projects"
SUBSCRIPTIONS_PATH = HOME / ".claude" / "dashboard-subscriptions.json"
HOST_NAME_PATH = HOME / ".claude" / "host-name"
VAULTS_BASE = HOME / "vaults"

DEFAULT_VAULT_ENV = "AGENTS_DEFAULT_VAULT"
DEFAULT_VAULT_FALLBACK = "JNS-Personal-Vault"


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
    """Projects known to this machine, sorted.

    Source of truth depends on what's present:
    - If the legacy YAML registry has entries, filter them by subscriptions
      (legacy behavior — used by the test fixtures that monkeypatch
      KNOWLEDGE_PROJECTS_DIR to a tmp dir).
    - If the registry is empty or missing (Path B post-archival), return the
      subscription list directly (aggregated across all vaults).
    """
    subs = read_subscriptions()
    if KNOWLEDGE_PROJECTS_DIR.exists():
        all_registered = sorted(p.stem for p in KNOWLEDGE_PROJECTS_DIR.glob("*.yaml"))
        if all_registered:
            if not subs:
                return all_registered
            filtered = [p for p in all_registered if p in subs]
            return filtered if filtered else all_registered
    return sorted(subs)


def register_project(name: str, owner: str = "jason", host: str | None = None) -> Path:
    """Write a default YAML to knowledge/projects/<name>.yaml + subscribe this machine.

    `host` declares which host owns this project (Phase 7.1; see
    specs/cross-device-state.md). If None, autodetected via get_host_name().

    Raises FileExistsError if YAML already exists. Returns the YAML path.
    """
    yaml_path = project_yaml_path(name)
    if yaml_path.exists():
        raise FileExistsError(f"project yaml already exists: {yaml_path}")
    today_str = date.today().isoformat()
    host_str = host if host is not None else get_host_name()
    content = (
        f"schema_version: 1\n"
        f"project: {name}\n"
        f"host: {host_str}\n"
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


# ---------- per-machine host name ----------

def get_host_name() -> str:
    """Read the canonical host name for this machine.

    Reads `~/.claude/host-name` (one line). Falls back to a sanitized
    `socket.gethostname()` if the file is absent — lowercased, first
    segment only (strips `.local`, `.localdomain`, `.lan`, etc.).

    Phase 7.1 — see specs/cross-device-state.md for context.
    """
    try:
        text = HOST_NAME_PATH.read_text().strip()
        if text:
            return text
    except FileNotFoundError:
        pass
    fallback = socket.gethostname() or "unknown"
    return fallback.lower().split(".")[0]


def set_host_name(name: str) -> None:
    """Write the canonical host name to `~/.claude/host-name`. Idempotent."""
    name = name.strip()
    if not name:
        raise ValueError("host name must be non-empty")
    HOST_NAME_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOST_NAME_PATH.write_text(name + "\n")


# ---------- subscriptions ----------
#
# The subscription file at ~/.claude/dashboard-subscriptions.json supports
# two on-disk shapes during the Path B transition:
#   legacy:      {"subscribed": ["proj1", "proj2"]}
#   vault-keyed: {"VAULT": {"subscribed": [...], "ssh_writes": [...]}, ...}
# Legacy ops preserve legacy on writes; vault-aware ops migrate on first write.

def default_vault() -> str:
    """Vault name for new vault-aware writes when none is specified."""
    return os.environ.get(DEFAULT_VAULT_ENV, DEFAULT_VAULT_FALLBACK)


def vault_path(vault: str, vaults_base: Path | None = None) -> Path:
    """Path to a vault's directory."""
    base = vaults_base if vaults_base is not None else VAULTS_BASE
    return base / vault


def _read_raw_subscriptions() -> dict:
    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_legacy_format(data: dict) -> bool:
    """True iff data is the legacy ``{"subscribed": [...]}`` shape."""
    return isinstance(data.get("subscribed"), list)


def _write_raw_subscriptions(data: dict) -> None:
    """Atomic JSON write of the subscription file."""
    SUBSCRIPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=SUBSCRIPTIONS_PATH.name + ".",
        suffix=".tmp",
        dir=str(SUBSCRIPTIONS_PATH.parent),
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, SUBSCRIPTIONS_PATH)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _normalize_vault_keyed(raw: dict) -> dict:
    """Coerce a vault-keyed dict into the canonical ``{vault: {subscribed, ssh_writes}}`` form."""
    out: dict = {}
    for vault, vdata in raw.items():
        if not isinstance(vdata, dict):
            continue
        out[vault] = {
            "subscribed": [
                s for s in (vdata.get("subscribed") or []) if isinstance(s, str)
            ],
            "ssh_writes": [
                h for h in (vdata.get("ssh_writes") or []) if isinstance(h, str)
            ],
        }
    return out


def _migrate_legacy_to_vault_keyed(raw: dict, vault: str) -> dict:
    """Move legacy ``subscribed: [...]`` into ``{vault: {subscribed, ssh_writes: []}}``."""
    legacy = [s for s in (raw.get("subscribed") or []) if isinstance(s, str)]
    return {vault: {"subscribed": legacy, "ssh_writes": []}}


def read_subscriptions() -> list[str]:
    """Aggregated subscribed project names across both formats. Sorted by insertion order."""
    raw = _read_raw_subscriptions()
    if not raw:
        return []
    if _is_legacy_format(raw):
        return [s for s in (raw.get("subscribed") or []) if isinstance(s, str)]
    seen: set[str] = set()
    out: list[str] = []
    for vdata in _normalize_vault_keyed(raw).values():
        for name in vdata["subscribed"]:
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def add_subscription(name: str) -> None:
    """Subscribe ``name`` (machine-local). Preserves on-disk format.

    - Empty/missing/legacy file: writes legacy shape with ``name`` appended.
    - Vault-keyed file: no-op if already subscribed in any vault; otherwise
      appends to default vault's ``subscribed`` list.
    Idempotent — re-adding ``name`` is a no-op regardless of which vault holds it.
    """
    raw = _read_raw_subscriptions()
    if not raw or _is_legacy_format(raw):
        subs = [s for s in (raw.get("subscribed") or []) if isinstance(s, str)]
        if name not in subs:
            subs.append(name)
        _write_raw_subscriptions({"subscribed": subs})
        return
    # Vault-keyed: only add if not already subscribed somewhere
    data = _normalize_vault_keyed(raw)
    if any(name in vdata["subscribed"] for vdata in data.values()):
        return
    add_subscription_to_vault(default_vault(), name)


def remove_subscription(name: str) -> None:
    """Drop ``name`` from any vault that has it. No-op if absent or file missing."""
    raw = _read_raw_subscriptions()
    if not raw:
        return
    if _is_legacy_format(raw):
        subs = [s for s in (raw.get("subscribed") or []) if isinstance(s, str)]
        if name in subs:
            subs.remove(name)
            _write_raw_subscriptions({"subscribed": subs})
        return
    data = _normalize_vault_keyed(raw)
    changed = False
    for vdata in data.values():
        if name in vdata["subscribed"]:
            vdata["subscribed"].remove(name)
            changed = True
    if changed:
        _write_raw_subscriptions(data)


# ---------- vault-aware subscription operations ----------

def read_subscriptions_dict() -> dict[str, dict]:
    """Vault-keyed subscriptions. Synthesizes a default-vault view of legacy files (no rewrite)."""
    raw = _read_raw_subscriptions()
    if not raw:
        return {}
    if _is_legacy_format(raw):
        return _migrate_legacy_to_vault_keyed(raw, default_vault())
    return _normalize_vault_keyed(raw)


def write_subscriptions_dict(data: dict[str, dict]) -> None:
    """Atomic write of vault-keyed subscriptions (forces vault-keyed format on disk)."""
    _write_raw_subscriptions(_normalize_vault_keyed(data))


def add_subscription_to_vault(vault: str, name: str) -> None:
    """Subscribe ``name`` in ``vault``. Migrates legacy file → vault-keyed if needed. Idempotent."""
    raw = _read_raw_subscriptions()
    if _is_legacy_format(raw):
        data = _migrate_legacy_to_vault_keyed(raw, default_vault())
    else:
        data = _normalize_vault_keyed(raw) if raw else {}
    vdata = data.setdefault(vault, {"subscribed": [], "ssh_writes": []})
    if name not in vdata["subscribed"]:
        vdata["subscribed"].append(name)
    _write_raw_subscriptions(data)


def remove_subscription_from_vault(vault: str, name: str) -> None:
    """Drop ``name`` from ``vault.subscribed``. No-op if absent. Migrates legacy → vault-keyed."""
    raw = _read_raw_subscriptions()
    if _is_legacy_format(raw):
        data = _migrate_legacy_to_vault_keyed(raw, default_vault())
    else:
        data = _normalize_vault_keyed(raw) if raw else {}
    if vault not in data:
        return
    if name in data[vault]["subscribed"]:
        data[vault]["subscribed"].remove(name)
        _write_raw_subscriptions(data)


def claim_ssh_host(vault: str, host: str) -> None:
    """Add ``host`` to ``vault.ssh_writes``. Idempotent. Migrates legacy → vault-keyed."""
    raw = _read_raw_subscriptions()
    if _is_legacy_format(raw):
        data = _migrate_legacy_to_vault_keyed(raw, default_vault())
    else:
        data = _normalize_vault_keyed(raw) if raw else {}
    vdata = data.setdefault(vault, {"subscribed": [], "ssh_writes": []})
    if host not in vdata["ssh_writes"]:
        vdata["ssh_writes"].append(host)
    _write_raw_subscriptions(data)


def release_ssh_host(vault: str, host: str) -> None:
    """Drop ``host`` from ``vault.ssh_writes``. No-op if absent. Migrates legacy → vault-keyed."""
    raw = _read_raw_subscriptions()
    if _is_legacy_format(raw):
        data = _migrate_legacy_to_vault_keyed(raw, default_vault())
    else:
        data = _normalize_vault_keyed(raw) if raw else {}
    if vault not in data:
        return
    if host in data[vault]["ssh_writes"]:
        data[vault]["ssh_writes"].remove(host)
        _write_raw_subscriptions(data)


# ---------- vault / project / decision paths ----------

def resolve_vault_for_project(name: str) -> str:
    """Find which vault has ``name`` subscribed. Errors if zero or many matches."""
    subs = read_subscriptions_dict()
    matches = [v for v, vdata in subs.items() if name in vdata["subscribed"]]
    if not matches:
        raise ProjectResolutionError(
            f"project {name!r} not subscribed in any vault. "
            f"Run: project {name} --subscribe (or --subscribe-to-vault VAULT)"
        )
    if len(matches) > 1:
        raise ProjectResolutionError(
            f"project {name!r} subscribed in multiple vaults: {', '.join(matches)}. "
            f"Pick one and unsubscribe from the others."
        )
    return matches[0]


def project_md_path(
    name: str,
    vault: str | None = None,
    vaults_base: Path | None = None,
) -> Path:
    """Path to ``<vault>/Projects/<name>.md``. Resolves vault if not given."""
    if vault is None:
        vault = resolve_vault_for_project(name)
    return vault_path(vault, vaults_base) / "Projects" / f"{name}.md"


def decision_md_path(
    decision_id: str,
    vault: str,
    vaults_base: Path | None = None,
) -> Path:
    """Path to ``<vault>/Decisions/D-NNN.md``."""
    return vault_path(vault, vaults_base) / "Decisions" / f"{decision_id}.md"


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
