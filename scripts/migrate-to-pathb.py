#!/usr/bin/env python3
"""migrate-to-pathb.py — one-shot YAML → Obsidian migration for Path B.

Reads project YAMLs from ``<repo>/knowledge/projects/*.yaml`` and writes each
as ``<vaults-base>/<vault>/Projects/<name>.md`` with frontmatter mapped per
``_archived/migration-manifest-2026-05-09.md`` and body sections from the
Project.md template. Also force-migrates the per-machine subscription file
``~/.claude/dashboard-subscriptions.json`` from the legacy flat shape to
vault-keyed shape if needed.

Decisions are NOT converted by this script — they archive-only via
``scripts/run-pathb-archival.sh``.

Usage::

    migrate-to-pathb.py --vault JNS-Personal-Vault [--dry-run]
    migrate-to-pathb.py --vault JNS-Personal-Vault --client personal \\
        --vaults-base /tmp/pathb-smoke

Heuristics:
- ``kind: engineering-tool`` for the ``agents`` project; ``kind: personal`` otherwise
- ``client: personal`` (override via ``--client``)
- ``repo_path``: ``~/agents`` for ``agents``; ``~/projects/<name>`` otherwise
- ``repo_remote``: ``git -C <repo_path> remote get-url origin`` if the dir exists

Idempotent: re-running on a state that's already migrated is a no-op (no writes,
no errors) UNLESS ``--force`` is set, in which case existing destination MD files
are overwritten. The subscription cutover writes a backup at
``dashboard-subscriptions-pre-pathb.json`` once, and never overwrites the backup.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# Import obsidian_md for atomic frontmatter writes.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import obsidian_md  # noqa: E402

# Frontmatter ordering for migrated project notes — matches project/cli.py.
PROJECT_FIELDS_ORDER = [
    "project", "host", "client", "kind", "status", "focus", "status_updated",
    "blockers", "next_steps", "open_questions",
    "stack", "repo_path", "repo_remote",
]

# Source-YAML field → destination frontmatter key. Locked per migration manifest.
SOURCE_TO_DEST = {
    "project": "project",
    "host": "host",
    "status": "status",
    "focus": "focus",
    "next_steps": "next_steps",
    "blockers": "blockers",
    "open_questions": "open_questions",
    "updated_at": "status_updated",
}
DROPPED_SOURCE_FIELDS = {"schema_version", "specs", "dependencies", "updated_by"}

# Kind heuristic — overrideable per project. agents is the engineering tool;
# everything else defaults to personal.
KIND_HEURISTIC = {"agents": "engineering-tool"}


class MigrationError(Exception):
    """User-facing error → stderr + exit 1."""


# ---------- helpers ----------

def kind_for(name: str) -> str:
    return KIND_HEURISTIC.get(name, "personal")


def detect_repo_path(name: str, home: Path | None = None) -> Path:
    home = home or Path.home()
    if name == "agents":
        return home / "agents"
    return home / "projects" / name


def detect_repo_remote(repo_path: Path) -> str:
    """Best-effort: read ``git -C <repo_path> remote get-url origin``."""
    if not (repo_path / ".git").exists():
        return ""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.SubprocessError, OSError):
        return ""


# ---------- body rendering ----------

_BODY_TEMPLATE = """# {name}

## Purpose
*(one sentence — what this project exists for)*

## Stack
*(languages, frameworks, key dependencies)*

## Repository
- Path: `{repo_path}`
- Remote: `{repo_remote}`

*(Add more sections as needed.)*

---

## Status (live)

```dataview
TABLE WITHOUT ID
  upper(string(this.status)) as "Status",
  this.host as "Host",
  this.focus as "Focus"
FROM ""
WHERE file.name = this.file.name
```

## Activity (rolled up across all hosts that pulse this project)

```dataview
TABLE WITHOUT ID
  host as "Host",
  pulled_at as "Last Pulse",
  last_commit_subject as "Last Commit",
  commits_7d as "Commits 7d",
  open_actions as "Open A",
  open_issues as "Open I"
FROM "Projects/_pulse"
WHERE project = this.project
SORT pulled_at DESC
```

## Decisions linked

```dataview
LIST FROM "Decisions"
WHERE project = this.project
SORT created_at DESC
LIMIT 5
```

## Git on this device

```dataview
LIST WITHOUT ID
  branch +
    choice(dirty, " · dirty", "") +
    choice(ahead_origin > 0, " · " + string(ahead_origin) + "↑", "") +
    choice(behind_origin > 0, " · " + string(behind_origin) + "↓", "") +
    choice(length(stale_local_branches) > 0,
           " · stale local: " + string(length(stale_local_branches)), "")
FROM "Projects/_pulse"
WHERE project = this.project AND host = this.host
```

## Notes / journal
*(your free-form area)*
"""


def render_body(name: str, repo_path: Path, repo_remote: str) -> str:
    return _BODY_TEMPLATE.format(
        name=name,
        repo_path=str(repo_path).replace(str(Path.home()), "~"),
        repo_remote=repo_remote,
    )


# ---------- migration core ----------

def build_frontmatter(
    source: dict,
    *,
    name: str,
    client: str,
    home: Path | None = None,
) -> dict:
    """Map source YAML to destination frontmatter dict (no I/O)."""
    repo_path = detect_repo_path(name, home=home)
    fm: dict = {}
    # 1:1 / renamed fields from source. YAML may parse unquoted dates as
    # datetime objects; coerce to ISO strings for stable frontmatter output.
    for src_key, dest_key in SOURCE_TO_DEST.items():
        if src_key in source:
            value = source[src_key]
            if isinstance(value, (dt.date, dt.datetime)):
                value = value.isoformat()
            fm[dest_key] = value
    # Ensure project key is present even if source omitted it
    fm.setdefault("project", name)
    # Destination-only fields
    fm["client"] = client
    fm["kind"] = kind_for(name)
    fm.setdefault("stack", [])
    fm["repo_path"] = str(repo_path).replace(str(home or Path.home()), "~")
    fm["repo_remote"] = detect_repo_remote(repo_path)
    # Ensure list-typed fields are lists (defaults if source had nulls)
    for list_field in ("next_steps", "blockers", "open_questions", "stack"):
        if fm.get(list_field) is None:
            fm[list_field] = []
    return fm


def migrate_project(
    source_yaml: Path,
    vault_dir: Path,
    *,
    client: str,
    dry_run: bool,
    force: bool,
    home: Path | None = None,
) -> tuple[str, Path]:
    """Migrate one project YAML → vault MD.

    Returns ``(action, dest_path)`` where action is one of
    ``"wrote"``, ``"skipped-exists"``, ``"dry-run-would-write"``.
    """
    name = source_yaml.stem
    try:
        source = yaml.safe_load(source_yaml.read_text()) or {}
    except yaml.YAMLError as e:
        raise MigrationError(f"malformed YAML in {source_yaml.name}: {e}") from e
    if not isinstance(source, dict):
        raise MigrationError(f"{source_yaml.name}: expected mapping at top level")

    fm = build_frontmatter(source, name=name, client=client, home=home)
    body = render_body(name, detect_repo_path(name, home=home), fm["repo_remote"])
    dest = vault_dir / "Projects" / f"{name}.md"

    if dest.exists() and not force:
        return ("skipped-exists", dest)
    if dry_run:
        return ("dry-run-would-write", dest)

    obsidian_md.write(dest, fm, body, field_order=PROJECT_FIELDS_ORDER)
    return ("wrote", dest)


# ---------- subscription cutover ----------

def migrate_subscription_file(
    path: Path,
    target_vault: str,
    *,
    dry_run: bool,
) -> tuple[str, str]:
    """Convert legacy ``{"subscribed": [...]}`` → vault-keyed dict.

    Idempotent. Writes a backup at ``dashboard-subscriptions-pre-pathb.json``
    once (never overwrites an existing backup). Returns ``(status, detail)``.
    """
    if not path.exists():
        return ("no-op", "subscription file doesn't exist; nothing to migrate")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise MigrationError(f"malformed JSON in {path}: {e}") from e
    if not isinstance(data, dict):
        raise MigrationError(f"{path}: expected JSON object at top level")

    # Already vault-keyed if it has no top-level "subscribed" list but does
    # have vault-shaped values.
    if not isinstance(data.get("subscribed"), list):
        return ("ok", "already vault-keyed")

    legacy_subs = [s for s in data["subscribed"] if isinstance(s, str)]
    new_data = {
        target_vault: {
            "subscribed": legacy_subs,
            "ssh_writes": [],
        }
    }

    if dry_run:
        return (
            "dry-run-would-migrate",
            f"{len(legacy_subs)} subscriptions → vault {target_vault}",
        )

    backup_path = path.parent / "dashboard-subscriptions-pre-pathb.json"
    if not backup_path.exists():
        backup_path.write_text(path.read_text())

    _atomic_write_json(path, new_data)
    return ("migrated", f"{len(legacy_subs)} subscriptions → vault {target_vault}")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


# ---------- orchestration ----------

def ensure_vault_dir(
    vault_dir: Path,
    *,
    dry_run: bool,
    noninteractive: bool,
) -> bool:
    """Ensure ``<vault>/Projects/`` exists. Returns True if proceeding, False otherwise."""
    projects_dir = vault_dir / "Projects"
    if projects_dir.is_dir():
        return True
    if dry_run:
        print(f"  (dry-run) would create: {projects_dir}")
        return True
    if not noninteractive:
        prompt = f"Create vault dir at {vault_dir}? [y/N]: "
        try:
            ans = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans not in ("y", "yes"):
            print(f"  refused — skipping migration. (Re-run with --noninteractive to auto-create.)")
            return False
    projects_dir.mkdir(parents=True, exist_ok=True)
    print(f"  created: {projects_dir}")
    return True


def run_migration(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    home = Path(args.home) if args.home else Path.home()
    projects_dir = Path(args.projects_dir) if args.projects_dir else repo_root / "knowledge" / "projects"
    vaults_base = Path(args.vaults_base) if args.vaults_base else home / "vaults"
    subscriptions = Path(args.subscriptions) if args.subscriptions else home / ".claude" / "dashboard-subscriptions.json"
    vault_dir = vaults_base / args.vault

    print(f"=== migrate-to-pathb {'(DRY RUN)' if args.dry_run else ''} ===")
    print(f"source projects:  {projects_dir}")
    print(f"destination:      {vault_dir}/Projects")
    print(f"subscription:     {subscriptions}")
    print(f"client (default): {args.client}")
    print()

    if not projects_dir.is_dir():
        print(f"ERROR: source projects dir not found: {projects_dir}", file=sys.stderr)
        return 2

    yamls = sorted(projects_dir.glob("*.yaml"))
    if not yamls:
        print(f"  no project YAMLs found in {projects_dir}")
        return 0

    print(f"▸ project YAML migration ({len(yamls)} files)")
    if not ensure_vault_dir(vault_dir, dry_run=args.dry_run, noninteractive=args.noninteractive):
        return 1

    summary = {"wrote": 0, "skipped-exists": 0, "dry-run-would-write": 0}
    try:
        for source_yaml in yamls:
            action, dest = migrate_project(
                source_yaml, vault_dir,
                client=args.client,
                dry_run=args.dry_run,
                force=args.force,
                home=home,
            )
            summary[action] = summary.get(action, 0) + 1
            display = str(dest).replace(str(home), "~")
            print(f"  {action}: {source_yaml.name} → {display}")
    except MigrationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print()
    print("▸ subscription file format cutover")
    try:
        status, detail = migrate_subscription_file(
            subscriptions, args.vault, dry_run=args.dry_run,
        )
        print(f"  {status}: {detail}")
    except MigrationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print()
    print("▸ summary")
    for k, v in summary.items():
        if v:
            print(f"  {k}: {v}")
    if args.dry_run:
        print()
        print("Re-run without --dry-run to apply.")
    else:
        print()
        print("Migration complete. Next: scripts/run-pathb-archival.sh --dry-run")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="One-shot YAML → Obsidian migration for Path B.")
    p.add_argument("--vault", required=True, help="Destination vault name (e.g. JNS-Personal-Vault)")
    p.add_argument("--client", default="personal", help="Default client field for migrated projects")
    p.add_argument("--vaults-base", default=None, help="Vault base dir (default: ~/vaults)")
    p.add_argument("--projects-dir", default=None,
                   help="Source projects dir (default: <repo>/knowledge/projects)")
    p.add_argument("--subscriptions", default=None,
                   help="Subscription file path (default: ~/.claude/dashboard-subscriptions.json)")
    p.add_argument("--home", default=None, help="Override $HOME (testing)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print intended changes; write nothing")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing destination MD files")
    p.add_argument("--noninteractive", action="store_true",
                   help="Auto-create vault dirs without prompting")
    args = p.parse_args(argv)
    try:
        return run_migration(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
