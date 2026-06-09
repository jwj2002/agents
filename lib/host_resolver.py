"""host_resolver — read repo state for pulse sidecars.

Two modes:

- **local**: runs ``git`` / ``gh`` against a path on this device.
- **ssh**:   runs the same commands on a remote host via
  ``ssh <host> '<command>'``. The remote path convention matches local
  (e.g. ``~/agents`` for the agents project).

A 5-minute in-process cache keyed by ``(ssh_host, repo_path, gh_slug)``
avoids redundant SSH trips on rapid ``pulse refresh`` calls. Clear with
``clear_cache()``.

Timeouts: 5s SSH connect, 10s per command. Failures (missing repo, SSH
timeout, ``gh`` unauthenticated) downgrade individual fields rather than
raising — callers always get a populated ``RepoState`` and can write the
sidecar even if some fields are unknown.
"""
from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CACHE_TTL_SECONDS = 300
SSH_CONNECT_TIMEOUT = 5
COMMAND_TIMEOUT = 10


@dataclass
class RepoState:
    """Sidecar payload for one (project, host) pair."""

    reachable: bool = True
    reason: str | None = None
    last_reachable_at: str | None = None

    # Activity
    last_commit_at: str | None = None
    last_commit_subject: str | None = None
    last_commit_sha: str | None = None
    commits_24h: int = 0
    commits_7d: int = 0

    # ACTIONS.md (-1 = file missing or unparseable; sidecar renders as "—")
    open_actions: int = -1
    closed_actions_24h: int = 0

    # gh (None = gh unavailable / unauthenticated)
    open_issues: int | None = None
    closed_issues_24h: int | None = None

    # Git hygiene
    branch: str | None = None
    ahead_origin: int = 0
    behind_origin: int = 0
    dirty: bool = False
    stale_local_branches: list = field(default_factory=list)
    unpushed_branches: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Render as a plain dict for YAML frontmatter serialization."""
        out: dict = {
            "reachable": self.reachable,
            "last_commit_at": self.last_commit_at,
            "last_commit_subject": self.last_commit_subject,
            "last_commit_sha": self.last_commit_sha,
            "commits_24h": self.commits_24h,
            "commits_7d": self.commits_7d,
            "open_actions": self.open_actions,
            "closed_actions_24h": self.closed_actions_24h,
            "open_issues": self.open_issues,
            "closed_issues_24h": self.closed_issues_24h,
            "branch": self.branch,
            "ahead_origin": self.ahead_origin,
            "behind_origin": self.behind_origin,
            "dirty": self.dirty,
            "stale_local_branches": list(self.stale_local_branches),
            "unpushed_branches": list(self.unpushed_branches),
        }
        if self.reason:
            out["reason"] = self.reason
        if self.last_reachable_at:
            out["last_reachable_at"] = self.last_reachable_at
        return out


# ---------- command execution ----------

def _run_local(
    cmd: list[str], *, cwd: str | Path | None = None, timeout: int = COMMAND_TIMEOUT,
) -> tuple[int, str, str]:
    """Run a command. Returns ``(rc, stdout, stderr)``. Never raises."""
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd) if cwd is not None else None,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return (r.returncode, r.stdout, r.stderr)
    except subprocess.TimeoutExpired:
        return (-1, "", "timeout")
    except (OSError, FileNotFoundError) as e:
        return (-1, "", str(e))


def _run_ssh(host: str, remote_cmd: str, *, timeout: int = COMMAND_TIMEOUT) -> tuple[int, str, str]:
    cmd = [
        "ssh",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-o", "BatchMode=yes",
        host, remote_cmd,
    ]
    return _run_local(cmd, timeout=timeout)


def _git(args: list[str], *, repo_path: str, ssh_host: str | None) -> tuple[int, str]:
    """Run ``git -C <repo_path> <args>`` locally or via ssh. Returns ``(rc, stdout)``."""
    if ssh_host is None:
        rc, out, _ = _run_local(["git", "-C", repo_path, *args])
    else:
        cmd_str = "git -C " + shlex.quote(repo_path) + " " + " ".join(shlex.quote(a) for a in args)
        rc, out, _ = _run_ssh(ssh_host, cmd_str)
    return rc, out.strip()


def _gh(args: list[str], *, ssh_host: str | None) -> tuple[int, str]:
    if ssh_host is None:
        rc, out, _ = _run_local(["gh", *args])
    else:
        cmd_str = "gh " + " ".join(shlex.quote(a) for a in args)
        rc, out, _ = _run_ssh(ssh_host, cmd_str)
    return rc, out.strip()


# ---------- field extractors ----------

def _try_int(text: str) -> int | None:
    try:
        return int(text)
    except (ValueError, TypeError):
        return None


def _read_git_state(repo_path: str, ssh_host: str | None) -> dict:
    """Return a dict of git-derived fields. Empty dict on unreachable repo."""
    rc, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path=repo_path, ssh_host=ssh_host)
    if rc != 0:
        return {}
    state: dict = {"branch": branch}

    # Default branch (origin/HEAD) — fall back to "main"
    rc, default_ref = _git(
        ["symbolic-ref", "refs/remotes/origin/HEAD"],
        repo_path=repo_path, ssh_host=ssh_host,
    )
    default_branch = default_ref.split("/")[-1] if rc == 0 and default_ref else "main"

    rc, out = _git(
        ["rev-list", "--count", f"origin/{default_branch}..HEAD"],
        repo_path=repo_path, ssh_host=ssh_host,
    )
    if rc == 0 and _try_int(out) is not None:
        state["ahead_origin"] = int(out)
    rc, out = _git(
        ["rev-list", "--count", f"HEAD..origin/{default_branch}"],
        repo_path=repo_path, ssh_host=ssh_host,
    )
    if rc == 0 and _try_int(out) is not None:
        state["behind_origin"] = int(out)

    rc, out = _git(["status", "--porcelain"], repo_path=repo_path, ssh_host=ssh_host)
    if rc == 0:
        state["dirty"] = bool(out.strip())

    rc, out = _git(
        ["log", "-1", "--format=%aI|%H|%s"],
        repo_path=repo_path, ssh_host=ssh_host,
    )
    if rc == 0 and out:
        parts = out.split("|", 2)
        if len(parts) == 3:
            state["last_commit_at"] = parts[0]
            state["last_commit_sha"] = parts[1][:7]
            state["last_commit_subject"] = parts[2]

    for field_name, since in (("commits_24h", "24 hours ago"), ("commits_7d", "7 days ago")):
        rc, out = _git(
            ["log", f"--since={since}", "--oneline"],
            repo_path=repo_path, ssh_host=ssh_host,
        )
        if rc == 0:
            state[field_name] = len([line for line in out.split("\n") if line.strip()])

    rc, out = _git(["branch", "--merged", default_branch], repo_path=repo_path, ssh_host=ssh_host)
    if rc == 0:
        stale = []
        for line in out.split("\n"):
            line = line.strip().lstrip("*").strip()
            if not line or line == default_branch or line.startswith("("):
                continue
            stale.append(line)
        state["stale_local_branches"] = stale

    rc, out = _git(
        ["for-each-ref", "--format=%(refname:short) %(upstream:track)", "refs/heads/"],
        repo_path=repo_path, ssh_host=ssh_host,
    )
    if rc == 0:
        unpushed = []
        for line in out.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "[gone]" in line or "ahead" in line.lower():
                unpushed.append(line.split()[0])
        state["unpushed_branches"] = unpushed

    return state


_GH_PATTERNS = (
    re.compile(r"git@github\.com:([^/]+/[^/.]+?)(?:\.git)?/?$"),
    re.compile(r"https?://github\.com/([^/]+/[^/.]+?)(?:\.git)?/?$"),
)


def derive_gh_slug(remote_url: str) -> str | None:
    """Extract ``owner/repo`` from a GitHub remote URL. Returns None if not GitHub."""
    if not remote_url:
        return None
    for pat in _GH_PATTERNS:
        m = pat.match(remote_url.strip())
        if m:
            return m.group(1)
    return None


def _read_gh_state(gh_slug: str | None, ssh_host: str | None) -> dict:
    """Read issue counts via ``gh``. Returns dict with ``open_issues`` / ``closed_issues_24h``."""
    if not gh_slug:
        return {}
    state: dict = {}
    rc, out = _gh(
        ["-R", gh_slug, "issue", "list", "--state", "open", "--json", "number", "--jq", "length"],
        ssh_host=ssh_host,
    )
    if rc == 0 and _try_int(out) is not None:
        state["open_issues"] = int(out)
    rc, out = _gh(
        ["-R", gh_slug, "issue", "list", "--state", "closed",
         "--search", "closed:>1d", "--json", "number", "--jq", "length"],
        ssh_host=ssh_host,
    )
    if rc == 0 and _try_int(out) is not None:
        state["closed_issues_24h"] = int(out)
    return state


def _read_actions_state(actions_path: Path) -> dict:
    """Read open/closed counts from a project's ACTIONS.md.

    Returns ``{"open": N, "closed_24h": M}``. On missing / unparseable file
    returns ``{"open": -1, "closed_24h": 0}`` so the sidecar renders as "—".
    Local-only; SSH-side ACTIONS.md reading is out of scope for v1.
    """
    if not actions_path.is_file():
        return {"open": -1, "closed_24h": 0}
    try:
        from lib.actions_md import MarkdownParseError, parse_file  # local import; lazy load
    except ImportError:
        return {"open": -1, "closed_24h": 0}
    try:
        model = parse_file(actions_path)
    except (OSError, MarkdownParseError, ValueError):
        return {"open": -1, "closed_24h": 0}
    open_count = len(model.open_rows())
    cutoff = (date.today() - timedelta(days=1)).isoformat()
    closed_24h = sum(
        1 for row in model.closed_rows() if str(row.get("Closed", "")) >= cutoff
    )
    return {"open": open_count, "closed_24h": closed_24h}


# ---------- cache ----------

_CACHE: dict[tuple, tuple[float, RepoState]] = {}


def clear_cache() -> None:
    """Drop all cached states (test hook / forced refresh)."""
    _CACHE.clear()


# ---------- public entry point ----------

def read_repo_state(
    repo_path: str,
    *,
    ssh_host: str | None = None,
    gh_slug: str | None = None,
    actions_path: Path | None = None,
    use_cache: bool = True,
    now: float | None = None,
) -> RepoState:
    """Build a RepoState for a (repo_path, host) pair.

    - ``ssh_host``: if set, run git/gh via SSH against that host.
    - ``gh_slug``: ``owner/repo`` for ``gh issue list`` calls. Derive with
      ``derive_gh_slug`` from the project's ``repo_remote`` frontmatter.
    - ``actions_path``: local path to the project's ACTIONS.md (local mode only).
    - ``use_cache``: skip the 5-minute cache when False (forces a fresh read).
    """
    now_ts = now if now is not None else time.time()
    cache_key = (ssh_host, repo_path, gh_slug)
    if use_cache and cache_key in _CACHE:
        cached_ts, cached_state = _CACHE[cache_key]
        if now_ts - cached_ts < CACHE_TTL_SECONDS:
            return cached_state

    state = RepoState(reachable=True)
    git_fields = _read_git_state(repo_path, ssh_host=ssh_host)
    if not git_fields:
        state.reachable = False
        state.reason = "no-clone-or-unreachable"
    else:
        for k, v in git_fields.items():
            setattr(state, k, v)

    if state.reachable:
        for k, v in _read_gh_state(gh_slug, ssh_host=ssh_host).items():
            setattr(state, k, v)
        if ssh_host is None and actions_path is not None:
            actions = _read_actions_state(actions_path)
            state.open_actions = actions["open"]
            state.closed_actions_24h = actions["closed_24h"]

    _CACHE[cache_key] = (now_ts, state)
    return state


def utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 with seconds (no microseconds)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
