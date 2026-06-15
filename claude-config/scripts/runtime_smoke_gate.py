"""Runtime-smoke obligation helper for PROVE Level 5 (issue #463, AC5 of #458).

Usage (from any project repo):
  python3 ~/agents/claude-config/scripts/runtime_smoke_gate.py \
      [--diff-range origin/main...HEAD] [--repo .] \
      [--smoke-sh path/to/smoke.sh] [--timeout 60]

Maps a git changeset to a set of smoke OBLIGATIONS (backend_http, cli, worker,
frontend), discovers a project-local `smoke.sh`, runs it under a timeout, and —
when an obligation exists but no `smoke.sh` is found — prints the obligation
list plus the documented uvicorn/health recipe as an advisory.

Exit codes:
  0  no obligation (n/a) OR smoke.sh ran and PASSED
  1  obligation detected but no smoke.sh (advisory — prints obligations + recipe)
  2  operational error (could not read the diff, or smoke.sh failed to launch)
  3  smoke.sh ran and FAILED (non-zero exit, incl. timeout)

This is a HELPER — it determines obligations and runs a discovered smoke.sh.
It does NOT block merges; enforcement of the recorded `runtime_smoke` block
stays in `prove_gate.py` (#460).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evals.common import ChangeSet, DiffError, changeset_from_git  # noqa: E402


class SmokeObligation(str, Enum):
    BACKEND_HTTP = "backend_http"
    CLI = "cli"
    WORKER = "worker"
    FRONTEND = "frontend"


# Backend HTTP smoke recipe — embedded verbatim from
# rules/post-merge-verification.md lines 27-31, with a placeholder caveat. The
# app module path and health route are PROJECT-SPECIFIC placeholders.
BACKEND_HTTP_RECIPE = """\
# Backend HTTP smoke — project-specific placeholders: app.main:app, /api/v1/health
timeout 15 python3 -m uvicorn app.main:app --host 127.0.0.1 --port 9999 &
sleep 5
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9999/api/v1/health 2>/dev/null)
kill %1 2>/dev/null
# HTTP_CODE should be 200 — replace app.main:app and /api/v1/health for your project
"""

# --- path patterns -----------------------------------------------------------
_BACKEND_PATH_RE = re.compile(r"(^|/)routers/|(^|/)app/|(^|/)main\.py$|^main\.py$")
_CLI_RE = re.compile(r"(^|/)bin/|(^|/)cli\.py$|(^|/)__main__\.py$")
_WORKER_PATH_RE = re.compile(r"(^|/)services/|(^|/)workers/")
_FRONTEND_PATH_RE = re.compile(r"(^|/)(pages|routes|app)/")
_FRONTEND_EXT_RE = re.compile(r"\.(tsx|jsx)$")

# --- content patterns (added lines / file text) ------------------------------
_BACKEND_CONTENT_RE = re.compile(
    r"FastAPI\(|@(app|router)\.(get|post|put|delete|patch)\b"
)
# WORKER content marker fires on a lifespan/service DEFINITION or REGISTRATION
# (not a bare prose/comment/regex mention) so docs and this tool's own source
# that merely name the words don't false-positive. Patterns:
#   - `def lifespan` / `async def lifespan` (a lifespan handler)
#   - `lifespan=`                            (FastAPI lifespan kwarg wiring)
#   - `ServiceContainer(`                    (instantiating the container)
#   - `_workers[`                            (registering in the worker dict)
_WORKER_CONTENT_RE = re.compile(
    r"\b(async\s+)?def\s+lifespan\b|\blifespan\s*=|\bServiceContainer\s*\(|\b_workers\["
)


# Test files are exercised by the test runner, never booted as a runnable
# surface — and their fixtures intentionally contain route/worker/CLI example
# strings, so they must be excluded from obligation detection.
_TEST_PATH_RE = re.compile(r"(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.py$|\.spec\.(t|j)sx?$|\.test\.(t|j)sx?$")


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def _added_text(cs: ChangeSet, path: str) -> str:
    """Added-line text, excluding comment-only lines (never an obligation)."""
    return "\n".join(
        text
        for _, text in cs.added_lines(path)
        if not text.lstrip().startswith("#")
    )


def _content_matches(cs: ChangeSet, path: str, pattern: re.Pattern[str]) -> bool:
    """True if PATTERN hits the added lines, or (fallback) the whole file text.

    The file-text fallback catches the case where the route/marker lives
    elsewhere in a file whose changed lines don't themselves contain it.
    """
    if pattern.search(_added_text(cs, path)):
        return True
    return bool(pattern.search(cs.file_text(path) or ""))


def _backend_http_hit(cs: ChangeSet, path: str) -> bool:
    """BACKEND_HTTP requires BOTH a backend path AND FastAPI content.

    Path alone must NOT fire — this is what keeps ``app/``-shaped tooling and
    this repo's own ``claude-config/scripts/*.py`` from resolving to
    BACKEND_HTTP (the central anti-false-positive design point).
    """
    if not _BACKEND_PATH_RE.search(path):
        return False
    return _content_matches(cs, path, _BACKEND_CONTENT_RE)


def _worker_hit(cs: ChangeSet, path: str) -> bool:
    if _WORKER_PATH_RE.search(path):
        return True
    # Content marker is a secondary trigger: only on Python source, and only on
    # ADDED lines (no whole-file fallback) — a worker entrypoint is being added,
    # not merely mentioned in a doc or comment elsewhere in the file.
    if not path.endswith(".py"):
        return False
    return bool(_WORKER_CONTENT_RE.search(_added_text(cs, path)))


def _frontend_hit(path: str) -> bool:
    return bool(_FRONTEND_EXT_RE.search(path) and _FRONTEND_PATH_RE.search(path))


def obligations(cs: ChangeSet) -> set[str]:
    """Map a changeset to the set of SmokeObligation values. Empty set = n/a."""
    obs: set[str] = set()
    for path in cs.paths:
        if _is_test_path(path):
            continue
        if _backend_http_hit(cs, path):
            obs.add(SmokeObligation.BACKEND_HTTP.value)
        if _CLI_RE.search(path):
            obs.add(SmokeObligation.CLI.value)
        if _worker_hit(cs, path):
            obs.add(SmokeObligation.WORKER.value)
        if _frontend_hit(path):
            obs.add(SmokeObligation.FRONTEND.value)
    return obs


def discover_smoke_sh(repo: Path, override: Path | None = None) -> Path | None:
    """Resolve a smoke.sh: override (if a file) → {repo}/smoke.sh → {repo}/scripts/smoke.sh."""
    if override is not None and override.is_file():
        return override
    for candidate in (repo / "smoke.sh", repo / "scripts" / "smoke.sh"):
        if candidate.is_file():
            return candidate
    return None


def run_smoke(smoke_sh: Path, repo: Path, timeout: int) -> tuple[int, str]:
    """Run `bash <smoke_sh>` in cwd=repo. Return (exit_code, combined output).

    A TimeoutExpired is mapped to a non-zero exit so the caller treats it as a
    FAIL. OSError (e.g. bash missing) is propagated for the caller's exit-2 path.
    """
    try:
        proc = subprocess.run(
            ["bash", str(smoke_sh)],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "")
        return 124, f"{out}\nsmoke.sh timed out after {timeout}s"
    return proc.returncode, proc.stdout + proc.stderr


def _report(obs: set[str], smoke_sh: Path | None, result: tuple[int, str] | None) -> None:
    listed = ", ".join(sorted(obs))
    if not obs:
        print("smoke: no runnable surface detected — runtime_smoke: n/a")
        return
    if smoke_sh is None:
        print(
            f"smoke: OBLIGATION [{listed}] but no smoke.sh found — "
            "run ad-hoc and record runtime_smoke; recipe below:"
        )
        if SmokeObligation.BACKEND_HTTP.value in obs:
            print(BACKEND_HTTP_RECIPE)
        return
    code, out = result if result is not None else (0, "")
    if code == 0:
        print(f"smoke: PASS via {smoke_sh} (obligations: {listed})")
    else:
        print(f"smoke: FAIL via {smoke_sh} (exit {code}) (obligations: {listed})")
    if out.strip():
        print(out.rstrip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="runtime_smoke_gate", description=__doc__.splitlines()[0]
    )
    ap.add_argument("--diff-range", default="origin/main...HEAD")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--smoke-sh", type=Path, default=None)
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args(argv)

    repo = args.repo.resolve()
    try:
        cs = changeset_from_git(repo, args.diff_range)
    except DiffError as exc:
        print(f"smoke: ERROR — {exc}", file=sys.stderr)
        return 2

    obs = obligations(cs)
    if not obs:
        _report(obs, None, None)
        return 0

    smoke_sh = discover_smoke_sh(repo, args.smoke_sh)
    if smoke_sh is None:
        _report(obs, None, None)
        return 1

    try:
        code, out = run_smoke(smoke_sh, repo, args.timeout)
    except OSError as exc:
        print(f"smoke: ERROR — could not run {smoke_sh}: {exc}", file=sys.stderr)
        return 2

    _report(obs, smoke_sh, (code, out))
    return 0 if code == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
