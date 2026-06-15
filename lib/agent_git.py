"""Shared git workflow checks for agent-managed projects."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


GENERATED_PARTS = {
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "telemetry",
}
GENERATED_SUFFIXES = {
    ".coverage",
    ".log",
    ".pyc",
    ".pyo",
    ".tmp",
    ".tsbuildinfo",
}


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class DirtyFile:
    path: str
    status: str
    kind: str
    generated: bool
    conflict: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "kind": self.kind,
            "generated": self.generated,
            "conflict": self.conflict,
        }


@dataclass
class PreflightResult:
    repo: str
    branch: str | None
    default_branch: str
    upstream: str | None
    fetched: bool
    behind_default: int | None
    dirty_files: list[DirtyFile] = field(default_factory=list)
    open_prs: list[dict[str, Any]] = field(default_factory=list)
    overlapping_prs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo": self.repo,
            "branch": self.branch,
            "default_branch": self.default_branch,
            "upstream": self.upstream,
            "fetched": self.fetched,
            "behind_default": self.behind_default,
            "dirty_files": [item.to_dict() for item in self.dirty_files],
            "open_prs": self.open_prs,
            "overlapping_prs": self.overlapping_prs,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class ReadinessResult:
    repo: str
    stage: str
    branch: str | None
    default_branch: str
    issue: int | None
    commits: list[str]
    changed_files: list[str]
    summary: str | None
    test_evidence: list[str]
    pr_body: str | None = None
    validation_log_status: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo": self.repo,
            "stage": self.stage,
            "branch": self.branch,
            "default_branch": self.default_branch,
            "issue": self.issue,
            "commits": self.commits,
            "changed_files": self.changed_files,
            "summary": self.summary,
            "test_evidence": self.test_evidence,
            "pr_body": self.pr_body,
            "validation_log_status": self.validation_log_status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class ShipResult:
    repo: str
    branch: str | None
    issue: int | None
    dry_run: bool
    stopped: bool
    stop_reason: str | None
    steps: list[str]
    preflight: dict[str, Any]
    readiness: dict[str, Any]
    pr_number: int | None = None
    pr_url: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.stopped and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo": self.repo,
            "branch": self.branch,
            "issue": self.issue,
            "dry_run": self.dry_run,
            "stopped": self.stopped,
            "stop_reason": self.stop_reason,
            "steps": self.steps,
            "preflight": self.preflight,
            "readiness": self.readiness,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class CleanupResult:
    repo: str
    default_branch: str
    dry_run: bool
    branch: str | None
    deleted_branches: list[str]
    skipped_branches: list[str]
    steps: list[str]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo": self.repo,
            "default_branch": self.default_branch,
            "dry_run": self.dry_run,
            "branch": self.branch,
            "deleted_branches": self.deleted_branches,
            "skipped_branches": self.skipped_branches,
            "steps": self.steps,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class WorktreeResult:
    repo: str
    action: str
    path: str
    branch: str | None
    dry_run: bool
    steps: list[str]
    preflight: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo": self.repo,
            "action": self.action,
            "path": self.path,
            "branch": self.branch,
            "dry_run": self.dry_run,
            "steps": self.steps,
            "preflight": self.preflight,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class Runner:
    def __call__(self, args: list[str], cwd: Path) -> CommandResult:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


BRANCH_RE = re.compile(
    r"^(feature|fix|docs|test|chore|perf|refactor)/issue-(?P<issue>\d+)-[a-z0-9][a-z0-9-]*$"
)
COMMIT_RE = re.compile(
    r"^(feat|fix|docs|test|chore|perf|refactor|ci|style)(\([a-z0-9_.-]+\))?: [a-z0-9].{0,70}$"
)
RUNNABLE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb",
    ".java", ".kt", ".c", ".cpp", ".h", ".sh",
}
VALIDATION_CMD_RE = re.compile(
    r"(?im)^\s*(?:[$>]|\+\s*)?\s*"
    r"(?:python\s+-m\s+pytest|pytest|ruff\s+(?:check|format)|npm\s+(?:test|run\s+(?:build|lint)))(?:\s|$)"
)


def is_generated_path(path: str) -> bool:
    parts = set(Path(path).parts)
    if parts & GENERATED_PARTS:
        return True
    suffix = Path(path).suffix
    if suffix in GENERATED_SUFFIXES:
        return True
    return path.endswith(".jsonl")


def parse_status(output: str) -> list[DirtyFile]:
    files: list[DirtyFile] = []
    conflict_codes = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}

    for raw in output.splitlines():
        if not raw:
            continue
        status = raw[:2]
        path = raw[3:] if len(raw) > 3 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1]

        if status == "??":
            kind = "untracked"
        elif status == "!!":
            kind = "ignored"
        else:
            kind = "tracked"

        conflict = status in conflict_codes or "U" in status
        files.append(
            DirtyFile(
                path=path,
                status=status,
                kind=kind,
                generated=is_generated_path(path),
                conflict=conflict,
            )
        )
    return files


def run_git(runner: Runner, repo: Path, args: list[str]) -> CommandResult:
    return runner(["git", *args], repo)


def detect_default_branch(runner: Runner, repo: Path) -> str:
    symbolic = run_git(runner, repo, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if symbolic.returncode == 0 and symbolic.stdout.strip().startswith("origin/"):
        return symbolic.stdout.strip().split("/", 1)[1]

    for candidate in ("main", "master"):
        exists = run_git(runner, repo, ["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{candidate}"])
        if exists.returncode == 0:
            return candidate
    return "main"


def get_upstream(runner: Runner, repo: Path) -> str | None:
    upstream = run_git(runner, repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if upstream.returncode != 0:
        return None
    return upstream.stdout.strip() or None


def count_behind_default(runner: Runner, repo: Path, default_branch: str) -> int | None:
    remote_ref = f"origin/{default_branch}"
    exists = run_git(runner, repo, ["show-ref", "--verify", "--quiet", f"refs/remotes/{remote_ref}"])
    if exists.returncode != 0:
        return None
    count = run_git(runner, repo, ["rev-list", "--count", f"HEAD..{remote_ref}"])
    if count.returncode != 0:
        return None
    try:
        return int(count.stdout.strip())
    except ValueError:
        return None


def list_open_prs(runner: Runner, repo: Path, warnings: list[str]) -> list[dict[str, Any]]:
    if shutil.which("gh") is None:
        warnings.append("GitHub CLI not found; skipped open PR overlap check.")
        return []

    prs = runner(
        ["gh", "pr", "list", "--state", "open", "--json", "number,title,headRefName"],
        repo,
    )
    if prs.returncode != 0:
        warnings.append("Could not list open GitHub PRs; skipped overlap check.")
        return []

    try:
        data = json.loads(prs.stdout or "[]")
    except json.JSONDecodeError:
        warnings.append("Could not parse open GitHub PR list; skipped overlap check.")
        return []

    return data if isinstance(data, list) else []


def add_pr_files(runner: Runner, repo: Path, prs: list[dict[str, Any]], warnings: list[str]) -> None:
    for pr in prs:
        number = pr.get("number")
        if number is None:
            continue
        details = runner(["gh", "pr", "view", str(number), "--json", "files"], repo)
        if details.returncode != 0:
            warnings.append(f"Could not inspect files for PR #{number}.")
            continue
        try:
            payload = json.loads(details.stdout or "{}")
        except json.JSONDecodeError:
            warnings.append(f"Could not parse files for PR #{number}.")
            continue
        files = payload.get("files") or []
        pr["files"] = [item.get("path") for item in files if item.get("path")]


def find_overlaps(prs: list[dict[str, Any]], paths: list[str]) -> list[dict[str, Any]]:
    wanted = set(paths)
    overlaps: list[dict[str, Any]] = []
    for pr in prs:
        files = set(pr.get("files") or [])
        common = sorted(wanted & files)
        if common:
            overlaps.append(
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "headRefName": pr.get("headRefName"),
                    "files": common,
                }
            )
    return overlaps


def preflight(
    repo: Path,
    *,
    allow_main: bool = False,
    include_ignored: bool = False,
    no_fetch: bool = False,
    paths: list[str] | None = None,
    runner: Runner | None = None,
) -> PreflightResult:
    runner = runner or Runner()
    repo = repo.resolve()
    paths = paths or []

    inside = run_git(runner, repo, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0:
        return PreflightResult(
            repo=str(repo),
            branch=None,
            default_branch="main",
            upstream=None,
            fetched=False,
            behind_default=None,
            errors=[f"Not a git repository: {repo}"],
        )

    branch_result = run_git(runner, repo, ["branch", "--show-current"])
    branch = branch_result.stdout.strip() or None
    default_branch = detect_default_branch(runner, repo)
    upstream = get_upstream(runner, repo)
    warnings: list[str] = []
    errors: list[str] = []

    fetched = False
    if not no_fetch:
        fetch = run_git(runner, repo, ["fetch", "origin", "--prune"])
        fetched = fetch.returncode == 0
        if fetch.returncode != 0:
            warnings.append("Could not fetch origin; freshness checks may be stale.")

    behind_default = count_behind_default(runner, repo, default_branch)
    status_args = ["status", "--porcelain=v1"]
    if include_ignored:
        status_args.append("--ignored=matching")
    status = run_git(runner, repo, status_args)
    dirty_files = parse_status(status.stdout if status.returncode == 0 else "")

    if branch == default_branch and not allow_main:
        errors.append(f"Current branch is {default_branch}; create an issue branch before implementation work.")

    if behind_default and behind_default > 0:
        errors.append(f"Branch is behind origin/{default_branch} by {behind_default} commit(s).")

    for item in dirty_files:
        if item.conflict:
            errors.append(f"Unresolved conflict in {item.path}.")
        elif item.kind != "ignored" and not item.generated:
            errors.append(f"Unsafe dirty file: {item.path} ({item.status}).")
        elif item.kind != "ignored" and item.generated:
            warnings.append(f"Generated or runtime dirty file present: {item.path} ({item.status}).")

    open_prs = list_open_prs(runner, repo, warnings)
    if paths and open_prs:
        add_pr_files(runner, repo, open_prs, warnings)
    overlapping_prs = find_overlaps(open_prs, paths) if paths else []
    for pr in overlapping_prs:
        errors.append(f"Open PR #{pr['number']} overlaps requested path(s): {', '.join(pr['files'])}.")

    return PreflightResult(
        repo=str(repo),
        branch=branch,
        default_branch=default_branch,
        upstream=upstream,
        fetched=fetched,
        behind_default=behind_default,
        dirty_files=dirty_files,
        open_prs=open_prs,
        overlapping_prs=overlapping_prs,
        errors=errors,
        warnings=warnings,
    )


def render_preflight_text(result: PreflightResult) -> str:
    lines = [
        f"preflight: {'pass' if result.ok else 'fail'}",
        f"repo: {result.repo}",
        f"branch: {result.branch or '(detached)'}",
        f"default_branch: {result.default_branch}",
        f"upstream: {result.upstream or '(none)'}",
        f"fetched: {str(result.fetched).lower()}",
        f"behind_default: {result.behind_default if result.behind_default is not None else '(unknown)'}",
        f"dirty_files: {len([item for item in result.dirty_files if item.kind != 'ignored'])}",
        f"open_prs: {len(result.open_prs)}",
        f"overlapping_prs: {len(result.overlapping_prs)}",
    ]

    if result.errors:
        lines.append("")
        lines.append("errors:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines) + "\n"


def extract_issue_from_branch(branch: str | None) -> int | None:
    if not branch:
        return None
    match = BRANCH_RE.match(branch)
    if not match:
        return None
    return int(match.group("issue"))


def list_commits(runner: Runner, repo: Path, default_branch: str) -> list[str]:
    log = run_git(runner, repo, ["log", "--format=%s", f"origin/{default_branch}..HEAD"])
    if log.returncode != 0:
        return []
    return [line for line in log.stdout.splitlines() if line.strip()]


def list_changed_files(runner: Runner, repo: Path, default_branch: str) -> list[str]:
    diff = run_git(runner, repo, ["diff", "--name-only", f"origin/{default_branch}...HEAD"])
    if diff.returncode != 0:
        return []
    return [line for line in diff.stdout.splitlines() if line.strip()]


def build_pr_body(issue: int | None, summary: str | None, test_evidence: list[str], local_only: bool) -> str:
    summary_lines = [f"- {summary}"] if summary else ["- "]
    test_lines = [f"- {item}" for item in test_evidence] or ["- "]
    issue_line = "Local-only exception." if local_only else f"Closes #{issue}"
    return "\n".join(
        [
            "## Summary",
            *summary_lines,
            "",
            "## Test Plan",
            *test_lines,
            "",
            issue_line,
            "",
        ]
    )


def _is_runnable_change(changed_files: list[str]) -> bool:
    """True iff any changed path has a code suffix (see RUNNABLE_SUFFIXES)."""
    return any(Path(p).suffix.lower() in RUNNABLE_SUFFIXES for p in changed_files)


def _validate_log(
    validation_log: str | None,
    runnable: bool,
    runner: Runner,
    repo: Path,
) -> tuple[list[str], str | None]:
    """Validate a runnable change's --validation-log.

    Returns (errors, status). status is one of
    "ok"|"missing"|"absent"|"stale"|"no_commands"|None (non-runnable).
    """
    if not runnable:
        return [], None
    if not validation_log:
        return (
            ["Runnable change requires --validation-log "
             "(a file with test/lint output)."],
            "absent",
        )
    log_path = Path(validation_log)
    if not log_path.is_absolute():
        log_path = (Path.cwd() / log_path).resolve()
    if not log_path.is_file():
        return ([f"Validation log not found: {validation_log}"], "missing")
    text = log_path.read_text(encoding="utf-8", errors="replace")

    # Freshness: mtime >= HEAD commit epoch, OR HEAD short sha appears in log.
    head_ct = run_git(runner, repo, ["show", "-s", "--format=%ct", "HEAD"])
    short_sha = run_git(runner, repo, ["rev-parse", "--short", "HEAD"])
    sha = short_sha.stdout.strip()
    fresh = False
    if head_ct.returncode == 0 and head_ct.stdout.strip().isdigit():
        fresh = int(log_path.stat().st_mtime) >= int(head_ct.stdout.strip())
    if not fresh and sha and sha in text:
        fresh = True
    if not fresh:
        return (
            ["Validation log is stale (older than HEAD and does not "
             "reference the HEAD commit). Re-run tests after committing."],
            "stale",
        )

    if not VALIDATION_CMD_RE.search(text):
        return (
            ["Validation log does not contain a recognized test/lint command "
             "(pytest, ruff check, ruff format, npm test/run build/run lint)."],
            "no_commands",
        )
    return [], "ok"


def readiness(
    repo: Path,
    *,
    stage: str = "open",
    issue: int | None = None,
    local_only: bool = False,
    summary: str | None = None,
    test_evidence: list[str] | None = None,
    allowed_paths: list[str] | None = None,
    generate_pr_body: bool = False,
    validation_log: str | None = None,
    runner: Runner | None = None,
) -> ReadinessResult:
    runner = runner or Runner()
    repo = repo.resolve()
    test_evidence = test_evidence or []
    allowed_paths = allowed_paths or []
    errors: list[str] = []
    warnings: list[str] = []

    inside = run_git(runner, repo, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0:
        return ReadinessResult(
            repo=str(repo),
            stage=stage,
            branch=None,
            default_branch="main",
            issue=issue,
            commits=[],
            changed_files=[],
            summary=summary,
            test_evidence=test_evidence,
            validation_log_status=None,
            errors=[f"Not a git repository: {repo}"],
        )

    branch_result = run_git(runner, repo, ["branch", "--show-current"])
    branch = branch_result.stdout.strip() or None
    default_branch = detect_default_branch(runner, repo)
    branch_issue = extract_issue_from_branch(branch)
    resolved_issue = issue or branch_issue

    if not branch or not BRANCH_RE.match(branch):
        errors.append("Branch name must match <type>/issue-<number>-<slug>.")
    if issue and branch_issue and issue != branch_issue:
        errors.append(f"Provided issue #{issue} does not match branch issue #{branch_issue}.")
    if not local_only and resolved_issue is None:
        errors.append("Issue linkage is required unless --local-only is used.")

    status = parse_status(run_git(runner, repo, ["status", "--porcelain=v1"]).stdout)
    for item in status:
        if item.kind != "ignored" and not item.generated:
            errors.append(f"Working tree is not ready: {item.path} ({item.status}).")
        elif item.kind != "ignored" and item.generated:
            warnings.append(f"Generated or runtime dirty file present: {item.path} ({item.status}).")

    commits = list_commits(runner, repo, default_branch)
    if not commits:
        errors.append(f"No commits found relative to origin/{default_branch}.")
    for commit in commits:
        if not COMMIT_RE.match(commit):
            errors.append(f"Commit summary is not Conventional Commits format: {commit}")

    changed_files = list_changed_files(runner, repo, default_branch)
    if not changed_files:
        errors.append("No changed files found relative to default branch.")

    if allowed_paths:
        allowed = tuple(allowed_paths)
        outside = [path for path in changed_files if not path.startswith(allowed)]
        for path in outside:
            errors.append(f"Changed file outside allowed scope: {path}")
    else:
        warnings.append("No allowed paths provided; changed-file scope was not constrained.")

    if not summary or not summary.strip():
        errors.append("Summary evidence is required.")
    if not test_evidence:
        errors.append("Test Plan evidence is required.")

    runnable = _is_runnable_change(changed_files)
    log_errors, validation_log_status = _validate_log(
        validation_log, runnable, runner, repo
    )
    errors.extend(log_errors)

    if stage == "merge":
        warnings.append("Merge-stage readiness currently validates local branch evidence only; CI state is handled by GitHub checks.")

    body = build_pr_body(resolved_issue, summary, test_evidence, local_only) if generate_pr_body else None

    return ReadinessResult(
        repo=str(repo),
        stage=stage,
        branch=branch,
        default_branch=default_branch,
        issue=resolved_issue,
        commits=commits,
        changed_files=changed_files,
        summary=summary,
        test_evidence=test_evidence,
        pr_body=body,
        validation_log_status=validation_log_status,
        errors=errors,
        warnings=warnings,
    )


def render_readiness_text(result: ReadinessResult) -> str:
    lines = [
        f"readiness: {'pass' if result.ok else 'fail'}",
        f"stage: {result.stage}",
        f"repo: {result.repo}",
        f"branch: {result.branch or '(detached)'}",
        f"default_branch: {result.default_branch}",
        f"issue: {result.issue if result.issue is not None else '(none)'}",
        f"commits: {len(result.commits)}",
        f"changed_files: {len(result.changed_files)}",
        f"test_evidence: {len(result.test_evidence)}",
        f"validation_log: {result.validation_log_status or '(n/a)'}",
    ]
    if result.pr_body:
        lines.extend(["", "pr_body:", result.pr_body.rstrip()])
    if result.errors:
        lines.append("")
        lines.append("errors:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines) + "\n"


def latest_commit_subject(runner: Runner, repo: Path) -> str:
    subject = run_git(runner, repo, ["log", "-1", "--format=%s"])
    if subject.returncode != 0 or not subject.stdout.strip():
        return "chore: ship agent-owned issue"
    return subject.stdout.strip()


def local_branch_exists(runner: Runner, repo: Path, branch: str) -> bool:
    result = run_git(runner, repo, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
    return result.returncode == 0


def merged_branches(runner: Runner, repo: Path, default_branch: str) -> list[str]:
    result = run_git(runner, repo, ["branch", "--merged", default_branch, "--format=%(refname:short)"])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def cleanup(
    repo: Path,
    *,
    branch: str | None = None,
    dry_run: bool = False,
    no_pull: bool = False,
    squash_merged_branch: bool = False,
    runner: Runner | None = None,
) -> CleanupResult:
    runner = runner or Runner()
    repo = repo.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    steps: list[str] = []
    deleted: list[str] = []
    skipped: list[str] = []

    inside = run_git(runner, repo, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0:
        return CleanupResult(
            repo=str(repo),
            default_branch="main",
            dry_run=dry_run,
            branch=branch,
            deleted_branches=[],
            skipped_branches=[],
            steps=[],
            errors=[f"Not a git repository: {repo}"],
        )

    default_branch = detect_default_branch(runner, repo)
    current = run_git(runner, repo, ["branch", "--show-current"]).stdout.strip() or None
    status = parse_status(run_git(runner, repo, ["status", "--porcelain=v1"]).stdout)
    for item in status:
        if item.kind != "ignored" and not item.generated:
            errors.append(f"Unsafe dirty file blocks cleanup: {item.path} ({item.status}).")
        elif item.kind != "ignored" and item.generated:
            warnings.append(f"Generated or runtime dirty file present: {item.path} ({item.status}).")
    if errors:
        return CleanupResult(str(repo), default_branch, dry_run, branch, deleted, skipped, steps, errors, warnings)

    steps.append(f"switch {default_branch}")
    if not dry_run and current != default_branch:
        switched = run_git(runner, repo, ["switch", default_branch])
        if switched.returncode != 0:
            errors.append(f"Could not switch to {default_branch}: {switched.stderr.strip()}")
            return CleanupResult(str(repo), default_branch, dry_run, branch, deleted, skipped, steps, errors, warnings)

    if not no_pull:
        steps.append("pull --ff-only")
        if not dry_run:
            pulled = run_git(runner, repo, ["pull", "--ff-only"])
            if pulled.returncode != 0:
                errors.append(f"Could not fast-forward {default_branch}: {pulled.stderr.strip() or pulled.stdout.strip()}")
                return CleanupResult(str(repo), default_branch, dry_run, branch, deleted, skipped, steps, errors, warnings)

    steps.append("fetch --prune origin")
    if not dry_run:
        pruned = run_git(runner, repo, ["fetch", "--prune", "origin"])
        if pruned.returncode != 0:
            warnings.append("Could not prune origin; continuing with local branch cleanup.")

    candidates: list[str]
    if branch:
        candidates = [branch]
    else:
        candidates = [
            item
            for item in merged_branches(runner, repo, default_branch)
            if item != default_branch and item != current
        ]

    merged = set(merged_branches(runner, repo, default_branch))
    for candidate in candidates:
        if candidate == default_branch:
            skipped.append(candidate)
            warnings.append(f"Refusing to delete default branch: {candidate}.")
            continue
        if not local_branch_exists(runner, repo, candidate):
            skipped.append(candidate)
            warnings.append(f"Local branch does not exist: {candidate}.")
            continue
        if candidate not in merged and not squash_merged_branch:
            skipped.append(candidate)
            errors.append(f"Branch is not safely merged: {candidate}.")
            continue
        # Use -D only after our own safety check. `git branch -d` can refuse
        # branches whose configured upstream is not merged even when the branch
        # is merged into the local default branch we just verified.
        delete_flag = "-D"
        steps.append(f"branch {delete_flag} {candidate}")
        if dry_run:
            deleted.append(candidate)
            continue
        deleted_result = run_git(runner, repo, ["branch", delete_flag, candidate])
        if deleted_result.returncode == 0:
            deleted.append(candidate)
        else:
            skipped.append(candidate)
            errors.append(f"Could not delete {candidate}: {deleted_result.stderr.strip() or deleted_result.stdout.strip()}")

    return CleanupResult(str(repo), default_branch, dry_run, branch, deleted, skipped, steps, errors, warnings)


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "work"


def worktree_add(
    repo: Path,
    *,
    issue: int,
    slug: str,
    path: str | None = None,
    branch: str | None = None,
    changed_paths: list[str] | None = None,
    dry_run: bool = False,
    no_fetch: bool = False,
    runner: Runner | None = None,
) -> WorktreeResult:
    runner = runner or Runner()
    repo = repo.resolve()
    safe_slug = slugify(slug)
    branch = branch or f"feature/issue-{issue}-{safe_slug}"
    path = path or str(repo / ".worktrees" / f"issue-{issue}-{safe_slug}")
    steps: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    preflight_result = preflight(
        repo,
        allow_main=True,
        no_fetch=no_fetch,
        paths=changed_paths or [],
        runner=runner,
    )
    warnings.extend(preflight_result.warnings)
    if not preflight_result.ok:
        errors.extend(preflight_result.errors)
        return WorktreeResult(
            repo=str(repo),
            action="add",
            path=path,
            branch=branch,
            dry_run=dry_run,
            steps=steps,
            preflight=preflight_result.to_dict(),
            errors=errors,
            warnings=warnings,
        )

    if local_branch_exists(runner, repo, branch):
        errors.append(f"Local branch already exists: {branch}.")

    target = Path(path)
    if target.exists():
        errors.append(f"Worktree path already exists: {target}.")

    default_ref = f"origin/{preflight_result.default_branch}"
    steps.append(f"git worktree add -b {branch} {target} {default_ref}")
    if errors or dry_run:
        return WorktreeResult(
            repo=str(repo),
            action="add",
            path=str(target),
            branch=branch,
            dry_run=dry_run,
            steps=steps,
            preflight=preflight_result.to_dict(),
            errors=errors,
            warnings=warnings,
        )

    added = run_git(runner, repo, ["worktree", "add", "-b", branch, str(target), default_ref])
    if added.returncode != 0:
        errors.append(f"Could not create worktree: {added.stderr.strip() or added.stdout.strip()}")

    return WorktreeResult(
        repo=str(repo),
        action="add",
        path=str(target),
        branch=branch,
        dry_run=dry_run,
        steps=steps,
        preflight=preflight_result.to_dict(),
        errors=errors,
        warnings=warnings,
    )


def worktree_remove(
    repo: Path,
    *,
    path: str,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> WorktreeResult:
    runner = runner or Runner()
    repo = repo.resolve()
    target = Path(path)
    steps = [f"git worktree remove {target}"]
    errors: list[str] = []

    if not target.exists():
        errors.append(f"Worktree path does not exist: {target}.")
    if errors or dry_run:
        return WorktreeResult(str(repo), "remove", str(target), None, dry_run, steps, errors=errors)

    removed = run_git(runner, repo, ["worktree", "remove", str(target)])
    if removed.returncode != 0:
        errors.append(f"Could not remove worktree: {removed.stderr.strip() or removed.stdout.strip()}")

    return WorktreeResult(str(repo), "remove", str(target), None, dry_run, steps, errors=errors)


def current_pr(runner: Runner, repo: Path) -> tuple[int | None, str | None]:
    result = runner(["gh", "pr", "view", "--json", "number,url"], repo)
    if result.returncode != 0:
        return None, None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None, None
    number = payload.get("number")
    url = payload.get("url")
    return (int(number), url) if number is not None else (None, url)


def create_pr(runner: Runner, repo: Path, title: str, body: str) -> tuple[int | None, str | None, str | None]:
    result = runner(["gh", "pr", "create", "--title", title, "--body", body], repo)
    if result.returncode != 0:
        return None, None, result.stderr.strip() or result.stdout.strip()
    url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else None
    number = None
    if url and "/" in url:
        try:
            number = int(url.rstrip("/").split("/")[-1])
        except ValueError:
            number = None
    return number, url, None


def post_comment(runner: Runner, repo: Path, issue_or_pr: int, body: str) -> None:
    runner(["gh", "issue", "comment", str(issue_or_pr), "--body", body], repo)


def stop_comment(result: ShipResult) -> str:
    errors = "\n".join(f"- {item}" for item in result.errors) or "- none"
    warnings = "\n".join(f"- {item}" for item in result.warnings) or "- none"
    return "\n".join(
        [
            "## Agent ship stopped",
            "",
            f"Branch: `{result.branch or '(detached)'}`",
            f"Stop reason: {result.stop_reason or 'unknown'}",
            "",
            "Errors:",
            errors,
            "",
            "Warnings:",
            warnings,
            "",
            "Next action: resolve the stop gate, rerun validation, then rerun `agent-git ship`.",
        ]
    )


def ship(
    repo: Path,
    *,
    issue: int | None = None,
    summary: str | None = None,
    test_evidence: list[str] | None = None,
    allowed_paths: list[str] | None = None,
    dry_run: bool = False,
    no_fetch: bool = False,
    skip_checks_wait: bool = False,
    comment_on_stop: bool = False,
    validation_log: str | None = None,
    runner: Runner | None = None,
) -> ShipResult:
    runner = runner or Runner()
    repo = repo.resolve()
    steps: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    def add_warnings(items: list[str]) -> None:
        for item in items:
            if item not in warnings:
                warnings.append(item)

    branch_result = run_git(runner, repo, ["branch", "--show-current"])
    branch = branch_result.stdout.strip() or None

    steps.append("preflight")
    preflight_result = preflight(repo, no_fetch=no_fetch, runner=runner)
    add_warnings(preflight_result.warnings)
    if not preflight_result.ok:
        errors.extend(preflight_result.errors)
        result = ShipResult(
            repo=str(repo),
            branch=branch,
            issue=issue or extract_issue_from_branch(branch),
            dry_run=dry_run,
            stopped=True,
            stop_reason="preflight failed",
            steps=steps,
            preflight=preflight_result.to_dict(),
            readiness={},
            errors=errors,
            warnings=warnings,
        )
        if comment_on_stop and result.issue:
            post_comment(runner, repo, result.issue, stop_comment(result))
        return result

    steps.append("readiness")
    readiness_result = readiness(
        repo,
        stage="merge",
        issue=issue,
        summary=summary,
        test_evidence=test_evidence,
        allowed_paths=allowed_paths,
        generate_pr_body=True,
        validation_log=validation_log,
        runner=runner,
    )
    add_warnings(readiness_result.warnings)
    resolved_issue = readiness_result.issue
    if not readiness_result.ok:
        errors.extend(readiness_result.errors)
        result = ShipResult(
            repo=str(repo),
            branch=branch,
            issue=resolved_issue,
            dry_run=dry_run,
            stopped=True,
            stop_reason="readiness failed",
            steps=steps,
            preflight=preflight_result.to_dict(),
            readiness=readiness_result.to_dict(),
            errors=errors,
            warnings=warnings,
        )
        if comment_on_stop and result.issue:
            post_comment(runner, repo, result.issue, stop_comment(result))
        return result

    planned = ["create_or_reuse_pr", "wait_for_checks", "squash_merge", "sync_main", "prune", "delete_branch"]
    steps.extend(planned)
    if dry_run:
        return ShipResult(
            repo=str(repo),
            branch=branch,
            issue=resolved_issue,
            dry_run=True,
            stopped=False,
            stop_reason=None,
            steps=steps,
            preflight=preflight_result.to_dict(),
            readiness=readiness_result.to_dict(),
            warnings=warnings,
        )

    if shutil.which("gh") is None:
        errors.append("GitHub CLI not found; cannot create or merge PR.")
        return ShipResult(
            repo=str(repo),
            branch=branch,
            issue=resolved_issue,
            dry_run=False,
            stopped=True,
            stop_reason="missing GitHub CLI",
            steps=steps,
            preflight=preflight_result.to_dict(),
            readiness=readiness_result.to_dict(),
            errors=errors,
            warnings=warnings,
        )

    pr_number, pr_url = current_pr(runner, repo)
    if pr_number is None:
        title = latest_commit_subject(runner, repo)
        pr_number, pr_url, create_error = create_pr(runner, repo, title, readiness_result.pr_body or "")
        if create_error:
            errors.append(f"Could not create PR: {create_error}")
            result = ShipResult(
                repo=str(repo),
                branch=branch,
                issue=resolved_issue,
                dry_run=False,
                stopped=True,
                stop_reason="PR creation failed",
                steps=steps,
                preflight=preflight_result.to_dict(),
                readiness=readiness_result.to_dict(),
                errors=errors,
                warnings=warnings,
            )
            if comment_on_stop and resolved_issue:
                post_comment(runner, repo, resolved_issue, stop_comment(result))
            return result

    if pr_number is None:
        errors.append("Could not determine PR number.")
        return ShipResult(
            repo=str(repo),
            branch=branch,
            issue=resolved_issue,
            dry_run=False,
            stopped=True,
            stop_reason="PR number unavailable",
            steps=steps,
            preflight=preflight_result.to_dict(),
            readiness=readiness_result.to_dict(),
            errors=errors,
            warnings=warnings,
            pr_url=pr_url,
        )

    if not skip_checks_wait:
        checks = runner(["gh", "pr", "checks", str(pr_number), "--watch", "--interval", "10"], repo)
        if checks.returncode != 0:
            errors.append("PR checks failed or could not be verified.")
            result = ShipResult(
                repo=str(repo),
                branch=branch,
                issue=resolved_issue,
                dry_run=False,
                stopped=True,
                stop_reason="checks failed",
                steps=steps,
                preflight=preflight_result.to_dict(),
                readiness=readiness_result.to_dict(),
                errors=errors,
                warnings=warnings,
                pr_number=pr_number,
                pr_url=pr_url,
            )
            if comment_on_stop:
                post_comment(runner, repo, pr_number, stop_comment(result))
            return result

    merge = runner(["gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch"], repo)
    if merge.returncode != 0:
        errors.append(f"PR merge failed: {merge.stderr.strip() or merge.stdout.strip()}")
        result = ShipResult(
            repo=str(repo),
            branch=branch,
            issue=resolved_issue,
            dry_run=False,
            stopped=True,
            stop_reason="merge failed",
            steps=steps,
            preflight=preflight_result.to_dict(),
            readiness=readiness_result.to_dict(),
            errors=errors,
            warnings=warnings,
            pr_number=pr_number,
            pr_url=pr_url,
        )
        if comment_on_stop:
            post_comment(runner, repo, pr_number, stop_comment(result))
        return result

    cleanup_result = cleanup(repo, branch=branch, squash_merged_branch=True, runner=runner)
    warnings.extend(item for item in cleanup_result.warnings if item not in warnings)
    if not cleanup_result.ok:
        errors.extend(cleanup_result.errors)
        return ShipResult(
            repo=str(repo),
            branch=branch,
            issue=resolved_issue,
            dry_run=False,
            stopped=True,
            stop_reason="cleanup failed",
            steps=steps,
            preflight=preflight_result.to_dict(),
            readiness=readiness_result.to_dict(),
            errors=errors,
            warnings=warnings,
            pr_number=pr_number,
            pr_url=pr_url,
        )

    return ShipResult(
        repo=str(repo),
        branch=branch,
        issue=resolved_issue,
        dry_run=False,
        stopped=False,
        stop_reason=None,
        steps=steps,
        preflight=preflight_result.to_dict(),
        readiness=readiness_result.to_dict(),
        pr_number=pr_number,
        pr_url=pr_url,
        warnings=warnings,
    )


def render_ship_text(result: ShipResult) -> str:
    lines = [
        f"ship: {'pass' if result.ok else 'stopped'}",
        f"repo: {result.repo}",
        f"branch: {result.branch or '(detached)'}",
        f"issue: {result.issue if result.issue is not None else '(none)'}",
        f"dry_run: {str(result.dry_run).lower()}",
        f"stopped: {str(result.stopped).lower()}",
        f"stop_reason: {result.stop_reason or '(none)'}",
        "steps:",
        *[f"- {step}" for step in result.steps],
    ]
    if result.pr_number:
        lines.append(f"pr: #{result.pr_number}")
    if result.pr_url:
        lines.append(f"pr_url: {result.pr_url}")
    if result.errors:
        lines.append("")
        lines.append("errors:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines) + "\n"


def render_cleanup_text(result: CleanupResult) -> str:
    lines = [
        f"cleanup: {'pass' if result.ok else 'fail'}",
        f"repo: {result.repo}",
        f"default_branch: {result.default_branch}",
        f"branch: {result.branch or '(auto)'}",
        f"dry_run: {str(result.dry_run).lower()}",
        "steps:",
        *[f"- {step}" for step in result.steps],
        f"deleted_branches: {len(result.deleted_branches)}",
        *[f"- {branch}" for branch in result.deleted_branches],
        f"skipped_branches: {len(result.skipped_branches)}",
        *[f"- {branch}" for branch in result.skipped_branches],
    ]
    if result.errors:
        lines.append("")
        lines.append("errors:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines) + "\n"


def render_worktree_text(result: WorktreeResult) -> str:
    lines = [
        f"worktree {result.action}: {'pass' if result.ok else 'fail'}",
        f"repo: {result.repo}",
        f"path: {result.path}",
        f"branch: {result.branch or '(none)'}",
        f"dry_run: {str(result.dry_run).lower()}",
        "steps:",
        *[f"- {step}" for step in result.steps],
    ]
    if result.errors:
        lines.append("")
        lines.append("errors:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines) + "\n"


def add_preflight_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("preflight", help="inspect git state before agent-owned edits")
    parser.add_argument("--repo", default=".", help="repository path")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--allow-main", action="store_true", help="do not fail when current branch is default")
    parser.add_argument("--include-ignored", action="store_true", help="include ignored files in dirty file output")
    parser.add_argument("--no-fetch", action="store_true", help="skip git fetch origin --prune")
    parser.add_argument("--path", action="append", default=[], help="intended changed path for open PR overlap checks")


def add_readiness_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("readiness", help="verify a branch is ready to open or merge a PR")
    parser.add_argument("--repo", default=".", help="repository path")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--stage", choices=["open", "merge"], default="open", help="readiness stage")
    parser.add_argument("--issue", type=int, help="linked GitHub issue number")
    parser.add_argument("--local-only", action="store_true", help="allow no issue linkage")
    parser.add_argument("--summary", help="summary evidence for the PR body")
    parser.add_argument("--test-evidence", action="append", default=[], help="test plan evidence; repeatable")
    parser.add_argument("--allowed-path", action="append", default=[], help="allowed changed-file prefix; repeatable")
    parser.add_argument("--generate-pr-body", action="store_true", help="include generated PR body in output")
    parser.add_argument(
        "--validation-log",
        dest="validation_log",
        help="path to a file containing test/lint output (required for runnable code changes)",
    )


def add_ship_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("ship", help="ship an agent-owned issue through PR, merge, and cleanup")
    parser.add_argument("--repo", default=".", help="repository path")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--issue", type=int, help="linked GitHub issue number")
    parser.add_argument("--summary", required=True, help="summary evidence for the PR body")
    parser.add_argument("--test-evidence", action="append", default=[], required=True, help="test plan evidence; repeatable")
    parser.add_argument("--allowed-path", action="append", default=[], help="allowed changed-file prefix; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="exercise ship gates without creating or merging a PR")
    parser.add_argument("--no-fetch", action="store_true", help="skip git fetch origin --prune during preflight")
    parser.add_argument("--skip-checks-wait", action="store_true", help="do not wait for gh pr checks before merge")
    parser.add_argument("--comment-on-stop", action="store_true", help="comment on the linked issue or PR when stopped")
    parser.add_argument(
        "--validation-log",
        dest="validation_log",
        help="path to a file containing test/lint output (required for runnable code changes)",
    )


def add_cleanup_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("cleanup", help="sync main, prune remotes, and delete safely merged branches")
    parser.add_argument("--repo", default=".", help="repository path")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--branch", help="specific local branch to delete")
    parser.add_argument("--dry-run", action="store_true", help="show cleanup actions without changing git state")
    parser.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only")
    parser.add_argument(
        "--squash-merged-branch",
        action="store_true",
        help="delete the named branch with -D after its squash-merged PR has been verified",
    )


def add_worktree_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("worktree", help="create or remove isolated agent worktrees")
    worktree_sub = parser.add_subparsers(dest="worktree_command", required=True)

    add_parser = worktree_sub.add_parser("add", help="create an isolated issue worktree")
    add_parser.add_argument("--repo", default=".", help="repository path")
    add_parser.add_argument("--json", action="store_true", help="emit JSON")
    add_parser.add_argument("--issue", type=int, required=True, help="issue number")
    add_parser.add_argument("--slug", required=True, help="branch/worktree slug")
    add_parser.add_argument("--path", help="worktree path; defaults to .worktrees/issue-N-slug")
    add_parser.add_argument("--branch", help="branch name; defaults to feature/issue-N-slug")
    add_parser.add_argument("--changed-path", action="append", default=[], help="intended changed path for open PR overlap checks")
    add_parser.add_argument("--dry-run", action="store_true", help="show worktree command without creating it")
    add_parser.add_argument("--no-fetch", action="store_true", help="skip git fetch origin --prune during preflight")

    remove_parser = worktree_sub.add_parser("remove", help="remove a completed worktree")
    remove_parser.add_argument("--repo", default=".", help="repository path")
    remove_parser.add_argument("--json", action="store_true", help="emit JSON")
    remove_parser.add_argument("--path", required=True, help="worktree path to remove")
    remove_parser.add_argument("--dry-run", action="store_true", help="show removal command without removing")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-git")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_preflight_parser(subparsers)
    add_readiness_parser(subparsers)
    add_ship_parser(subparsers)
    add_cleanup_parser(subparsers)
    add_worktree_parser(subparsers)

    args = parser.parse_args(argv)

    if args.command == "preflight":
        result = preflight(
            Path(args.repo),
            allow_main=args.allow_main,
            include_ignored=args.include_ignored,
            no_fetch=args.no_fetch,
            paths=args.path,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_preflight_text(result), end="")
        return 0 if result.ok else 1

    if args.command == "worktree":
        if args.worktree_command == "add":
            result = worktree_add(
                Path(args.repo),
                issue=args.issue,
                slug=args.slug,
                path=args.path,
                branch=args.branch,
                changed_paths=args.changed_path,
                dry_run=args.dry_run,
                no_fetch=args.no_fetch,
            )
        else:
            result = worktree_remove(
                Path(args.repo),
                path=args.path,
                dry_run=args.dry_run,
            )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_worktree_text(result), end="")
        return 0 if result.ok else 1

    if args.command == "cleanup":
        result = cleanup(
            Path(args.repo),
            branch=args.branch,
            dry_run=args.dry_run,
            no_pull=args.no_pull,
            squash_merged_branch=args.squash_merged_branch,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_cleanup_text(result), end="")
        return 0 if result.ok else 1

    if args.command == "ship":
        result = ship(
            Path(args.repo),
            issue=args.issue,
            summary=args.summary,
            test_evidence=args.test_evidence,
            allowed_paths=args.allowed_path,
            dry_run=args.dry_run,
            no_fetch=args.no_fetch,
            skip_checks_wait=args.skip_checks_wait,
            comment_on_stop=args.comment_on_stop,
            validation_log=args.validation_log,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_ship_text(result), end="")
        return 0 if result.ok else 1

    if args.command == "readiness":
        result = readiness(
            Path(args.repo),
            stage=args.stage,
            issue=args.issue,
            local_only=args.local_only,
            summary=args.summary,
            test_evidence=args.test_evidence,
            allowed_paths=args.allowed_path,
            generate_pr_body=args.generate_pr_body,
            validation_log=args.validation_log,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_readiness_text(result), end="")
        return 0 if result.ok else 1

    parser.error(f"unknown command: {args.command}")
    return 2
