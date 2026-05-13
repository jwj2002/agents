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


# ---------- sidecar reading ----------

def list_sidecars(
    vault: str, project: str, *, vaults_base: Path | None = None,
) -> list[tuple[Path, dict]]:
    """Return [(path, frontmatter), ...] for every <project>--<host>.md sidecar."""
    base = vaults_base if vaults_base is not None else _vaults_base()
    pulse_dir = base / vault / "Projects" / "_pulse"
    if not pulse_dir.is_dir():
        return []
    out = []
    for p in sorted(pulse_dir.glob(f"{project}--*.md")):
        try:
            fm, _ = obsidian_md.load(p)
        except obsidian_md.ObsidianMdError:
            continue
        out.append((p, fm))
    return out


# ---------- report ----------

def render_report(
    vault: str, project: str, *, vaults_base: Path | None = None,
) -> str:
    """Markdown report for one project: frontmatter summary + per-host sidecar table."""
    note = project_note_path(vault, project, vaults_base=vaults_base)
    if not note.exists():
        return f"# {project}\n\n_Project note not found at_ `{note}`\n"
    fm, _ = obsidian_md.load(note)
    lines = [
        f"# {project}",
        "",
        f"**Status**: {(fm.get('status') or '?').upper()} · "
        f"**Host**: {fm.get('host', '?')} · "
        f"**Updated**: {fm.get('status_updated', '?')}",
        "",
        f"**Focus**: {fm.get('focus') or '_(not set)_'}",
        "",
    ]

    blockers = fm.get("blockers") or []
    if blockers:
        lines.append("## Blockers")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    next_steps = fm.get("next_steps") or []
    if next_steps:
        lines.append("## Next steps")
        for i, s in enumerate(next_steps, 1):
            lines.append(f"{i}. {s}")
        lines.append("")

    questions = fm.get("open_questions") or []
    if questions:
        lines.append("## Open questions")
        for q in questions:
            lines.append(f"- {q}")
        lines.append("")

    sidecars = list_sidecars(vault, project, vaults_base=vaults_base)
    if sidecars:
        lines.append("## Activity (per host)")
        lines.append("")
        lines.append("| Host | Last pulse | Last commit | 24h | 7d | Open A | Open I |")
        lines.append("|---|---|---|---:|---:|---:|---:|")
        for _, sfm in sidecars:
            actions = sfm.get("open_actions")
            actions_cell = "—" if actions in (None, -1) else str(actions)
            issues = sfm.get("open_issues")
            issues_cell = "—" if issues is None else str(issues)
            commit = sfm.get("last_commit_subject") or "—"
            if len(commit) > 50:
                commit = commit[:47] + "…"
            lines.append(
                f"| {sfm.get('host', '?')} | "
                f"{sfm.get('pulled_at', '?')} | "
                f"{commit} | "
                f"{sfm.get('commits_24h', 0)} | "
                f"{sfm.get('commits_7d', 0)} | "
                f"{actions_cell} | "
                f"{issues_cell} |"
            )
        lines.append("")

        # Git hygiene block — one line per host with non-clean state
        hygiene_lines = []
        for _, sfm in sidecars:
            parts = []
            if sfm.get("dirty"):
                parts.append("dirty")
            ahead = sfm.get("ahead_origin", 0) or 0
            behind = sfm.get("behind_origin", 0) or 0
            if ahead:
                parts.append(f"{ahead}↑")
            if behind:
                parts.append(f"{behind}↓")
            stale = sfm.get("stale_local_branches") or []
            if stale:
                parts.append(f"stale local: {len(stale)}")
            unpushed = sfm.get("unpushed_branches") or []
            if unpushed:
                parts.append(f"unpushed: {len(unpushed)}")
            if not sfm.get("reachable", True):
                parts.append("UNREACHABLE")
            if parts:
                hygiene_lines.append(f"- **{sfm.get('host', '?')}**: " + " · ".join(parts))
        if hygiene_lines:
            lines.append("## Git — needs attention")
            lines.extend(hygiene_lines)
            lines.append("")
    else:
        lines.append("_(no sidecars yet — run `pulse refresh` first)_")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------- digest ----------

def render_vault_digest(
    vault: str, *, vaults_base: Path | None = None, window: str = "daily",
) -> str:
    """Cross-project digest for one vault, suitable for terminal or email body."""
    subs = pr.read_subscriptions_dict()
    if vault not in subs:
        return f"# {vault}\n\n_Vault not in subscription file._\n"
    base = vaults_base if vaults_base is not None else _vaults_base()
    today = hr.utc_now_iso().split("T")[0]
    lines = [
        f"# {vault} — digest ({window}, {today})",
        "",
    ]

    projects = subs[vault].get("subscribed", [])
    if not projects:
        lines.append("_No subscribed projects in this vault._")
        return "\n".join(lines) + "\n"

    for project in projects:
        note = base / vault / "Projects" / f"{project}.md"
        if not note.exists():
            lines.append(f"## {project} — _(no project note)_")
            lines.append("")
            continue
        try:
            fm, _ = obsidian_md.load(note)
        except obsidian_md.ObsidianMdError:
            lines.append(f"## {project} — _(unreadable project note)_")
            lines.append("")
            continue
        status = (fm.get("status") or "?").lower()
        lines.append(f"## {project} — {status}")
        focus = fm.get("focus") or ""
        if focus:
            lines.append(f"**Focus**: {focus}")
        # Activity from sidecars
        sidecars = list_sidecars(vault, project, vaults_base=base)
        if sidecars:
            for _, sfm in sidecars:
                host = sfm.get("host", "?")
                commit = sfm.get("last_commit_subject") or "_(no commit)_"
                if len(commit) > 60:
                    commit = commit[:57] + "…"
                c24 = sfm.get("commits_24h", 0)
                c7 = sfm.get("commits_7d", 0)
                actions = sfm.get("open_actions")
                actions_cell = "—" if actions in (None, -1) else str(actions)
                issues = sfm.get("open_issues")
                issues_cell = "—" if issues is None else str(issues)
                reach = "" if sfm.get("reachable", True) else " · UNREACHABLE"
                lines.append(
                    f"- **{host}**: {commit} · "
                    f"{c24}c/24h · {c7}c/7d · "
                    f"{actions_cell}A · {issues_cell}I{reach}"
                )
        # Blockers
        blockers = fm.get("blockers") or []
        if blockers:
            lines.append("**Blockers**: " + "; ".join(str(b) for b in blockers))
        lines.append("")

    lines.append("---")
    lines.append(f"Generated: {hr.utc_now_iso()}")
    return "\n".join(lines) + "\n"


def render_all_vaults_digest(
    *, vaults_base: Path | None = None, window: str = "daily",
) -> str:
    """Cross-vault digest. jns-mac only (Codex F4 guardrail)."""
    local_host = pr.get_host_name()
    if local_host != "jns-mac":
        raise PulseError(
            f"--all-vaults is jns-mac-only (this device is '{local_host}'). "
            f"Refusing to render cross-vault digest on a client laptop "
            f"(spec §6.5 #2 / Codex F4)."
        )
    subs = pr.read_subscriptions_dict()
    parts = []
    for vault in subs:
        parts.append(render_vault_digest(vault, vaults_base=vaults_base, window=window))
    return "\n".join(parts)


# ---------- audit ----------
#
# Cross-vault hygiene scan (spec §6.5 #5). Read-only.
#
# Checks:
# - vault → client mapping (opt-in via ~/.claude/vault-clients.yaml): every
#   project note in vault V has client: <expected> matching the config
# - sidecar filename consistency: <project>--<host>.md must have frontmatter
#   project: and host: that match the filename
# - subscription file vs on-disk: every vault key has a real directory
# - git remote allowlist (opt-in via ~/.claude/vault-remotes.yaml from #164):
#   vault's origin URL must match the configured value

from dataclasses import dataclass  # noqa: E402

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"
_LEVEL_RANK = {LEVEL_INFO: 0, LEVEL_WARNING: 1, LEVEL_ERROR: 2}

VAULT_CLIENTS_PATH = Path.home() / ".claude" / "vault-clients.yaml"
VAULT_REMOTES_PATH = Path.home() / ".claude" / "vault-remotes.yaml"


@dataclass
class AuditFinding:
    level: str  # info | warning | error
    vault: str  # "" for global findings
    check: str  # short identifier
    message: str


def _load_vault_yaml_map(path: Path) -> dict[str, str]:
    """Parse a simple ``key: value`` YAML file. Lines starting with ``#`` or blank are skipped."""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def audit_client_match(
    vault: str, vault_dir: Path, expected_client: str,
) -> list[AuditFinding]:
    """Every project note in vault must have client: <expected>."""
    findings: list[AuditFinding] = []
    projects_dir = vault_dir / "Projects"
    if not projects_dir.is_dir():
        return findings
    for note in sorted(projects_dir.glob("*.md")):
        try:
            fm, _ = obsidian_md.load(note)
        except obsidian_md.ObsidianMdError:
            findings.append(AuditFinding(
                LEVEL_WARNING, vault, "unreadable-note",
                f"could not parse {note.name}",
            ))
            continue
        actual = fm.get("client")
        if not actual:
            findings.append(AuditFinding(
                LEVEL_WARNING, vault, "client-missing",
                f"{note.name} has no `client:` field (expected {expected_client!r})",
            ))
        elif actual != expected_client:
            findings.append(AuditFinding(
                LEVEL_ERROR, vault, "client-mismatch",
                f"{note.name} has client={actual!r}, expected {expected_client!r}",
            ))
    return findings


def audit_sidecar_consistency(vault: str, vault_dir: Path) -> list[AuditFinding]:
    """Each <project>--<host>.md sidecar's frontmatter must agree with its filename."""
    findings: list[AuditFinding] = []
    pulse_dir = vault_dir / "Projects" / "_pulse"
    if not pulse_dir.is_dir():
        return findings
    for sidecar in sorted(pulse_dir.glob("*.md")):
        stem = sidecar.stem
        if "--" not in stem:
            findings.append(AuditFinding(
                LEVEL_WARNING, vault, "sidecar-bad-name",
                f"{sidecar.name} doesn't match <project>--<host>.md naming",
            ))
            continue
        expected_project, expected_host = stem.split("--", 1)
        try:
            fm, _ = obsidian_md.load(sidecar)
        except obsidian_md.ObsidianMdError:
            findings.append(AuditFinding(
                LEVEL_WARNING, vault, "sidecar-unreadable",
                f"could not parse {sidecar.name}",
            ))
            continue
        actual_project = fm.get("project")
        actual_host = fm.get("host")
        if actual_project != expected_project:
            findings.append(AuditFinding(
                LEVEL_ERROR, vault, "sidecar-project-mismatch",
                f"{sidecar.name}: filename says {expected_project!r}, "
                f"frontmatter says {actual_project!r}",
            ))
        if actual_host != expected_host:
            findings.append(AuditFinding(
                LEVEL_ERROR, vault, "sidecar-host-mismatch",
                f"{sidecar.name}: filename says {expected_host!r}, "
                f"frontmatter says {actual_host!r}",
            ))
    return findings


def audit_git_remote_allowlist(
    vault: str, vault_dir: Path, expected_remote: str,
) -> list[AuditFinding]:
    """Vault's git remote must match the configured allowlist URL."""
    findings: list[AuditFinding] = []
    if not (vault_dir / ".git").exists():
        # Vault is not a git repo yet — not an error, just informational
        findings.append(AuditFinding(
            LEVEL_INFO, vault, "no-git",
            f"{vault} is not a git repository (skipping remote check)",
        ))
        return findings
    import subprocess
    try:
        r = subprocess.run(
            ["git", "-C", str(vault_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (subprocess.SubprocessError, OSError) as e:
        findings.append(AuditFinding(
            LEVEL_WARNING, vault, "git-error",
            f"could not read git remote: {e}",
        ))
        return findings
    if r.returncode != 0:
        findings.append(AuditFinding(
            LEVEL_WARNING, vault, "no-origin",
            f"{vault} has no `origin` remote configured (expected {expected_remote!r})",
        ))
        return findings
    actual = r.stdout.strip()
    if actual != expected_remote:
        findings.append(AuditFinding(
            LEVEL_ERROR, vault, "remote-mismatch",
            f"{vault} origin is {actual!r}, expected {expected_remote!r}",
        ))
    return findings


def audit_subscription_vs_disk(
    vaults_base: Path,
) -> list[AuditFinding]:
    """Every vault in the subscription file should have a directory on disk."""
    findings: list[AuditFinding] = []
    subs = pr.read_subscriptions_dict()
    for vault in subs:
        if not (vaults_base / vault).is_dir():
            findings.append(AuditFinding(
                LEVEL_WARNING, vault, "stale-subscription",
                f"vault listed in subscriptions but {vaults_base / vault} not on disk",
            ))
    return findings


def audit_all(
    *,
    vaults_base: Path | None = None,
    vault_clients_path: Path | None = None,
    vault_remotes_path: Path | None = None,
) -> list[AuditFinding]:
    """Run every check across every subscribed vault. Returns findings list."""
    base = vaults_base if vaults_base is not None else _vaults_base()
    clients = _load_vault_yaml_map(
        vault_clients_path if vault_clients_path is not None else VAULT_CLIENTS_PATH
    )
    remotes = _load_vault_yaml_map(
        vault_remotes_path if vault_remotes_path is not None else VAULT_REMOTES_PATH
    )

    findings: list[AuditFinding] = []
    findings.extend(audit_subscription_vs_disk(base))

    subs = pr.read_subscriptions_dict()
    for vault in subs:
        vault_dir = base / vault
        if not vault_dir.is_dir():
            continue  # already flagged by audit_subscription_vs_disk
        if vault in clients:
            findings.extend(audit_client_match(vault, vault_dir, clients[vault]))
        else:
            findings.append(AuditFinding(
                LEVEL_INFO, vault, "no-client-mapping",
                f"no entry in vault-clients.yaml for {vault} — skipping client check",
            ))
        findings.extend(audit_sidecar_consistency(vault, vault_dir))
        if vault in remotes:
            findings.extend(audit_git_remote_allowlist(vault, vault_dir, remotes[vault]))
        else:
            findings.append(AuditFinding(
                LEVEL_INFO, vault, "no-remote-mapping",
                f"no entry in vault-remotes.yaml for {vault} — skipping remote check",
            ))
    return findings


def render_audit(findings: list[AuditFinding]) -> str:
    """Format findings for terminal output. Groups by vault, then by level."""
    if not findings:
        return "pulse audit: clean ✓\n"
    lines = ["pulse audit findings:", ""]
    by_vault: dict[str, list[AuditFinding]] = {}
    for f in findings:
        by_vault.setdefault(f.vault or "(global)", []).append(f)
    for vault in sorted(by_vault):
        lines.append(f"▸ {vault}")
        # Sort within a vault: errors first, then warnings, then info
        for f in sorted(by_vault[vault], key=lambda x: -_LEVEL_RANK[x.level]):
            marker = {"error": "✗", "warning": "⚠", "info": "·"}.get(f.level, "?")
            lines.append(f"  {marker} [{f.level}] {f.check}: {f.message}")
        lines.append("")
    errs = sum(1 for f in findings if f.level == LEVEL_ERROR)
    warns = sum(1 for f in findings if f.level == LEVEL_WARNING)
    infos = sum(1 for f in findings if f.level == LEVEL_INFO)
    lines.append(f"summary: errors={errs} warnings={warns} info={infos}")
    return "\n".join(lines) + "\n"


# ---------- argparse + main ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pulse",
        description="Refresh / report / digest per-host project sidecars (Path B).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    refresh = sub.add_parser("refresh", help="Refresh sidecars")
    refresh.add_argument("--vault", help="Limit to one vault")
    refresh.add_argument("--project", help="Limit to one project")
    refresh.add_argument("--vaults-base", default=None,
                         help="Vault base dir (default: pr.VAULTS_BASE)")
    refresh.add_argument("--no-cache", action="store_true",
                         help="Bypass the host_resolver 5-min cache")

    report = sub.add_parser("report", help="Single-project markdown report")
    report.add_argument("--project", required=True, help="Project name")
    report.add_argument("--vault", help="Vault (default: auto-resolve from subscription)")
    report.add_argument("--vaults-base", default=None)

    digest = sub.add_parser("digest", help="Cross-project markdown digest")
    g = digest.add_mutually_exclusive_group(required=True)
    g.add_argument("--vault", help="Render one vault's digest")
    g.add_argument("--all-vaults", action="store_true",
                   help="Render every vault's digest (jns-mac only)")
    digest.add_argument("--window", default="daily",
                        choices=["daily", "weekly", "monthly", "full"],
                        help="Window scope (v1 always emits 24h+7d commit counts)")
    digest.add_argument("--vaults-base", default=None)

    audit = sub.add_parser("audit", help="Cross-vault hygiene scan (spec §6.5 #5)")
    audit.add_argument("--vaults-base", default=None)
    audit.add_argument("--vault-clients", default=None,
                       help="Path to vault→client mapping YAML (default: ~/.claude/vault-clients.yaml)")
    audit.add_argument("--vault-remotes", default=None,
                       help="Path to vault→remote URL mapping YAML (default: ~/.claude/vault-remotes.yaml)")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)
        vaults_base = Path(args.vaults_base) if args.vaults_base else None

        if args.cmd == "refresh":
            refresh_all(
                vault_filter=args.vault,
                project_filter=args.project,
                vaults_base=vaults_base,
                use_cache=not args.no_cache,
            )
            return 0

        if args.cmd == "report":
            vault = args.vault or pr.resolve_vault_for_project(args.project)
            sys.stdout.write(render_report(vault, args.project, vaults_base=vaults_base))
            return 0

        if args.cmd == "digest":
            if args.all_vaults:
                sys.stdout.write(render_all_vaults_digest(
                    vaults_base=vaults_base, window=args.window,
                ))
            else:
                sys.stdout.write(render_vault_digest(
                    args.vault, vaults_base=vaults_base, window=args.window,
                ))
            return 0

        if args.cmd == "audit":
            findings = audit_all(
                vaults_base=vaults_base,
                vault_clients_path=Path(args.vault_clients) if args.vault_clients else None,
                vault_remotes_path=Path(args.vault_remotes) if args.vault_remotes else None,
            )
            sys.stdout.write(render_audit(findings))
            # Exit non-zero on any errors so cron surfaces them.
            return 1 if any(f.level == LEVEL_ERROR for f in findings) else 0

        raise PulseError(f"unknown subcommand: {args.cmd}")
    except (PulseError, pr.ProjectResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
