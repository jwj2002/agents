#!/usr/bin/env python3
"""pulse — refresh / report / digest per-host project sidecars.

Iterates ``(vault, project, host)`` triples derived from the per-machine
subscription file (``~/.claude/dashboard-subscriptions.json``) and writes one
sidecar at ``<vault>/Projects/_pulse/<project>--<host>.md`` per triple.

Single-writer-per-host (Codex F3 fix): each device only refreshes hosts
listed in its own ``ssh_writes``. The local host is always refreshed
locally. Hosts owned by another device are skipped silently — pulse on
that other device will refresh them and the sidecars sync via vault git.

Subcommands:

- ``pulse refresh [--project NAME] [--vault NAME]`` — refresh sidecars.
- ``pulse report --project NAME`` — render a single-project markdown report
  (added in a follow-up commit; the ``refresh`` slice ships first).
- ``pulse digest --vault NAME | --all-vaults`` — cross-project digest
  (added in a follow-up commit).

This CLI does NOT touch the human-edited project note (``Projects/<name>.md``).
Pulse owns the sidecars exclusively; the project note is owned by the user
(or by the ``project`` CLI's frontmatter mutations).

Alias: ``alias pulse='python3 ~/agents/pulse/cli.py'``
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Repo root for lib imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import host_resolver as hr  # noqa: E402
from lib import obsidian_md  # noqa: E402
from lib import project_resolver as pr  # noqa: E402

SIDECAR_FIELDS_ORDER = [
    "project", "host", "pulled_at", "reachable", "reason", "last_reachable_at",
    "last_commit_at", "last_commit_subject", "last_commit_sha",
    "commits_24h", "commits_7d",
    "open_actions", "closed_actions_24h",
    "open_issues", "closed_issues_24h",
    "branch", "ahead_origin", "behind_origin", "dirty",
    "stale_local_branches", "unpushed_branches",
]

SIDECAR_BODY = "*(file body unused — sidecars are pure frontmatter)*\n"


class PulseError(Exception):
    """User-facing error → stderr + exit 1."""


# ---------- path helpers ----------

def _vaults_base() -> Path:
    return pr.VAULTS_BASE


def project_note_path(vault: str, project: str, *, vaults_base: Path | None = None) -> Path:
    base = vaults_base if vaults_base is not None else _vaults_base()
    return base / vault / "Projects" / f"{project}.md"


def sidecar_path(
    vault: str, project: str, host: str, *, vaults_base: Path | None = None,
) -> Path:
    base = vaults_base if vaults_base is not None else _vaults_base()
    return base / vault / "Projects" / "_pulse" / f"{project}--{host}.md"


def _expand_repo_path(raw: str, home: Path | None = None) -> str:
    """Expand ``~/...`` to the absolute home path. Empty/None passes through."""
    if not raw:
        return raw
    home = home if home is not None else Path.home()
    if raw.startswith("~/"):
        return str(home / raw[2:])
    if raw == "~":
        return str(home)
    return raw


# ---------- sidecar write ----------

def write_sidecar(
    path: Path,
    project: str,
    host: str,
    state: hr.RepoState,
    *,
    last_reachable_at: str | None = None,
    now_iso: str | None = None,
) -> None:
    """Atomic write of a sidecar from a RepoState."""
    fm: dict = {
        "project": project,
        "host": host,
        "pulled_at": now_iso or hr.utc_now_iso(),
    }
    fm.update(state.to_dict())
    if last_reachable_at and not state.reachable:
        fm["last_reachable_at"] = last_reachable_at
    obsidian_md.write(path, fm, SIDECAR_BODY, field_order=SIDECAR_FIELDS_ORDER)


def _prior_last_reachable_at(path: Path) -> str | None:
    """If the sidecar already exists and was reachable, return its pulled_at."""
    if not path.is_file():
        return None
    try:
        fm, _ = obsidian_md.load(path)
    except obsidian_md.ObsidianMdError:
        return None
    if fm.get("reachable"):
        return fm.get("pulled_at")
    # Sidecar is currently unreachable — propagate its existing last_reachable_at
    return fm.get("last_reachable_at")


# ---------- single-project refresh ----------

def refresh_one(
    vault: str,
    project: str,
    ssh_writes: list[str],
    local_host: str,
    *,
    vaults_base: Path | None = None,
    home: Path | None = None,
    use_cache: bool = True,
) -> tuple[str, Path | None]:
    """Refresh the sidecar for one (vault, project) pair.

    Returns ``(status, sidecar_path | None)`` where status is one of:
    - ``"wrote"``
    - ``"wrote-unreachable"``
    - ``"skipped-no-note"``
    - ``"skipped-no-host"``
    - ``"skipped-not-owned"``
    """
    note = project_note_path(vault, project, vaults_base=vaults_base)
    if not note.exists():
        return ("skipped-no-note", None)
    try:
        fm, _ = obsidian_md.load(note)
    except obsidian_md.ObsidianMdError as e:
        raise PulseError(f"reading {note}: {e}") from e

    host = fm.get("host")
    if not host:
        return ("skipped-no-host", None)

    if host == local_host:
        ssh_host = None
    elif host in ssh_writes:
        ssh_host = host
    else:
        return ("skipped-not-owned", None)

    repo_path = _expand_repo_path(fm.get("repo_path", ""), home=home)
    gh_slug = hr.derive_gh_slug(fm.get("repo_remote", ""))
    actions_path = (
        Path(repo_path) / "ACTIONS.md"
        if repo_path and ssh_host is None
        else None
    )

    state = hr.read_repo_state(
        repo_path=repo_path,
        ssh_host=ssh_host,
        gh_slug=gh_slug,
        actions_path=actions_path,
        use_cache=use_cache,
    )

    out_path = sidecar_path(vault, project, host, vaults_base=vaults_base)
    last_reachable = _prior_last_reachable_at(out_path) if not state.reachable else None
    write_sidecar(out_path, project, host, state, last_reachable_at=last_reachable)
    return (("wrote" if state.reachable else "wrote-unreachable"), out_path)


# ---------- vault iteration ----------

def refresh_vault(
    vault: str,
    vault_data: dict,
    local_host: str,
    *,
    project_filter: str | None = None,
    vaults_base: Path | None = None,
    home: Path | None = None,
    use_cache: bool = True,
) -> dict:
    """Refresh every project in a single vault. Returns a per-status counter dict."""
    summary: dict = {}
    subscribed = vault_data.get("subscribed", []) if isinstance(vault_data, dict) else []
    ssh_writes = vault_data.get("ssh_writes", []) if isinstance(vault_data, dict) else []
    for project in subscribed:
        if project_filter and project != project_filter:
            continue
        status, path = refresh_one(
            vault, project, ssh_writes, local_host,
            vaults_base=vaults_base, home=home, use_cache=use_cache,
        )
        summary[status] = summary.get(status, 0) + 1
        rel = ""
        if path is not None:
            try:
                rel = str(path.relative_to(home or Path.home()))
                rel = "~/" + rel
            except (ValueError, AttributeError):
                rel = str(path)
        print(f"  [{vault}/{project}] {status}{(' → ' + rel) if rel else ''}")
    return summary


def refresh_all(
    *,
    vault_filter: str | None = None,
    project_filter: str | None = None,
    vaults_base: Path | None = None,
    home: Path | None = None,
    use_cache: bool = True,
) -> dict:
    """Refresh every subscribed (vault, project) pair on this device."""
    subs = pr.read_subscriptions_dict()
    local_host = pr.get_host_name()
    print(f"=== pulse refresh ===")
    print(f"local host: {local_host}")
    print(f"vaults base: {vaults_base or _vaults_base()}")
    print()

    summary: dict = {}
    for vault, vault_data in subs.items():
        if vault_filter and vault != vault_filter:
            continue
        print(f"▸ vault {vault}")
        v_summary = refresh_vault(
            vault, vault_data, local_host,
            project_filter=project_filter,
            vaults_base=vaults_base, home=home, use_cache=use_cache,
        )
        for k, v in v_summary.items():
            summary[k] = summary.get(k, 0) + v

    print()
    print("▸ summary")
    for k in sorted(summary):
        print(f"  {k}: {summary[k]}")
    return summary


# ---------- argparse + main ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pulse",
        description="Refresh per-host project sidecars (Path B).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    refresh = sub.add_parser("refresh", help="Refresh sidecars")
    refresh.add_argument("--vault", help="Limit to one vault")
    refresh.add_argument("--project", help="Limit to one project")
    refresh.add_argument("--vaults-base", default=None,
                         help="Vault base dir (default: pr.VAULTS_BASE)")
    refresh.add_argument("--no-cache", action="store_true",
                         help="Bypass the host_resolver 5-min cache")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)
        if args.cmd == "refresh":
            refresh_all(
                vault_filter=args.vault,
                project_filter=args.project,
                vaults_base=Path(args.vaults_base) if args.vaults_base else None,
                use_cache=not args.no_cache,
            )
            return 0
        raise PulseError(f"unknown subcommand: {args.cmd}")
    except PulseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
