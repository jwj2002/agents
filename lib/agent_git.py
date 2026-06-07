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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-git")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_preflight_parser(subparsers)
    add_readiness_parser(subparsers)

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
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_readiness_text(result), end="")
        return 0 if result.ok else 1

    parser.error(f"unknown command: {args.command}")
    return 2
