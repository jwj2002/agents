"""Mechanical Claude/Codex parity checks."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CLAUDE_MD_BUDGET = 200
RULES_BUDGET = 450


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ParityReport:
    repo: str
    checks: list[CheckResult]

    @property
    def errors(self) -> list[str]:
        return [check.message for check in self.checks if check.status == "fail"]

    @property
    def warnings(self) -> list[str]:
        return [check.message for check in self.checks if check.status == "warn"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo": self.repo,
            "checks": [check.to_dict() for check in self.checks],
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _repo_root(path: Path) -> Path:
    return path.resolve()


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    raw = text[4:end]
    try:
        import yaml
    except ImportError:
        return None
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else {}


def _is_always_load_rule(path: Path) -> bool:
    fm = _frontmatter(path)
    if fm is None:
        return True
    paths = fm.get("paths")
    if paths is None:
        return True
    return paths == ["**"]


def budget_check(repo: Path) -> CheckResult:
    claude_md = repo / "claude-config" / "CLAUDE.md"
    rules_dir = repo / "claude-config" / "rules"
    details: dict[str, Any] = {
        "claude_budget": CLAUDE_MD_BUDGET,
        "rules_budget": RULES_BUDGET,
    }
    errors: list[str] = []

    if not claude_md.is_file():
        errors.append(f"missing {claude_md}")
    else:
        claude_lines = _line_count(claude_md)
        details["claude_lines"] = claude_lines
        details["claude_headroom"] = CLAUDE_MD_BUDGET - claude_lines
        if claude_lines > CLAUDE_MD_BUDGET:
            errors.append(
                f"CLAUDE.md exceeds budget by {claude_lines - CLAUDE_MD_BUDGET} lines"
            )

    if not rules_dir.is_dir():
        errors.append(f"missing {rules_dir}")
    else:
        counted: dict[str, int] = {}
        total = 0
        for rule in sorted(rules_dir.glob("*.md")):
            if not _is_always_load_rule(rule):
                continue
            lines = _line_count(rule)
            counted[rule.name] = lines
            total += lines
        details["always_load_rules"] = counted
        details["rules_lines"] = total
        details["rules_headroom"] = RULES_BUDGET - total
        if total > RULES_BUDGET:
            errors.append(f"always-load rules exceed budget by {total - RULES_BUDGET} lines")

    if errors:
        return CheckResult("budget_headroom", "fail", "; ".join(errors), details)
    return CheckResult("budget_headroom", "pass", "context budgets within limits", details)


def _skill_name(path: Path) -> str:
    return path.parent.name


def _run_portability_lint(repo: Path, skill_md: Path) -> int:
    lint = repo / "claude-config" / "scripts" / "check-skill-portability.sh"
    if not lint.is_file():
        return 2
    result = subprocess.run(
        [str(lint), str(skill_md)],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode


def expected_portable_claude_skills(repo: Path) -> tuple[list[str], list[str]]:
    portable: list[str] = []
    skipped: list[str] = []
    for skill_md in sorted((repo / "claude-config" / "skills").glob("*/SKILL.md")):
        rc = _run_portability_lint(repo, skill_md)
        name = _skill_name(skill_md)
        if rc == 0:
            portable.append(name)
        elif rc == 1:
            skipped.append(name)
        else:
            skipped.append(f"{name} (lint-error)")
    return portable, skipped


def codex_native_skills(repo: Path) -> list[str]:
    return [
        _skill_name(path)
        for path in sorted((repo / "codex-config" / "skills").glob("*/SKILL.md"))
    ]


def _expected_link_target(repo: Path, skill: str) -> Path:
    claude_skill = repo / "claude-config" / "skills" / skill
    if claude_skill.is_dir():
        return claude_skill
    return repo / "codex-config" / "skills" / skill


def skill_parity_check(repo: Path, home: Path | None = None) -> CheckResult:
    portable, skipped = expected_portable_claude_skills(repo)
    native = codex_native_skills(repo)
    lint_errors = [name for name in skipped if name.endswith(" (lint-error)")]
    details: dict[str, Any] = {
        "portable_claude_skills": portable,
        "claude_only_skills": skipped,
        "codex_native_skills": native,
    }
    missing: list[str] = []

    if home is not None:
        link_checks: dict[str, dict[str, str]] = {}
        for skill in sorted(set(portable + native)):
            expected_target = _expected_link_target(repo, skill).resolve()
            for root in (home / ".codex" / "skills", home / ".agents" / "skills"):
                link = root / skill
                label = str(link)
                if not link.is_symlink():
                    missing.append(f"{label} is not a symlink")
                    continue
                actual = link.resolve()
                link_checks[label] = {
                    "target": str(actual),
                    "expected": str(expected_target),
                }
                if actual != expected_target:
                    missing.append(f"{label} points to {actual}, expected {expected_target}")
        details["installed_links"] = link_checks

    if lint_errors:
        return CheckResult(
            "skill_parity",
            "fail",
            "skill portability lint failed",
            {**details, "lint_errors": lint_errors},
        )
    if missing:
        return CheckResult("skill_parity", "fail", "Codex skill links are incomplete", details)

    message = "portable skills enumerated"
    if home is not None:
        message = "portable and native Codex skills are linked"
    return CheckResult("skill_parity", "pass", message, details)


CAPABILITY_PATHS = {
    "claude_install": "claude-config/install.sh",
    "claude_guidance": "claude-config/CLAUDE.md",
    "claude_commands": "claude-config/commands",
    "claude_agents": "claude-config/agents",
    "claude_hooks": "claude-config/hooks",
    "claude_settings": "claude-config/settings.json",
    "codex_install": "codex-config/install.sh",
    "codex_guidance": "codex-config/AGENTS.md",
    "codex_config_template": "codex-config/config.toml.example",
    "codex_rules": "codex-config/rules",
    "codex_skills": "codex-config/skills",
    "project_bootstrap": "new-project-agents.sh",
    "parity_cli": "bin/agent-parity",
    "validate_workflow": ".github/workflows/validate.yml",
}


def capability_docs_check(repo: Path) -> CheckResult:
    doc = repo / "docs" / "AGENT-CAPABILITIES.md"
    missing = [
        f"{key}: {rel}"
        for key, rel in CAPABILITY_PATHS.items()
        if not (repo / rel).exists()
    ]
    details = {"checked_paths": CAPABILITY_PATHS}
    if not doc.is_file():
        missing.append("docs/AGENT-CAPABILITIES.md")
    if missing:
        return CheckResult(
            "capability_docs",
            "fail",
            "documented capability paths are missing",
            {**details, "missing": missing},
        )
    return CheckResult(
        "capability_docs",
        "pass",
        "documented capability paths exist",
        details,
    )


def workflow_tree_check(repo: Path) -> CheckResult:
    active_legacy = repo / "orchestrate-workflow"
    archived_legacy = repo / "_archived" / "orchestrate-workflow-legacy"
    canonical = repo / "claude-config" / "commands" / "orchestrate.md"
    details = {
        "canonical": str(canonical),
        "active_legacy_exists": active_legacy.exists(),
        "archived_legacy_exists": archived_legacy.exists(),
    }
    if active_legacy.exists():
        return CheckResult(
            "workflow_tree",
            "fail",
            "active legacy orchestrate-workflow tree exists beside canonical Claude command",
            details,
        )
    if not canonical.is_file():
        return CheckResult("workflow_tree", "fail", "canonical orchestrate command missing", details)
    return CheckResult("workflow_tree", "pass", "no active duplicate workflow tree", details)


def one_sided_hooks_check(repo: Path) -> CheckResult:
    settings = repo / "claude-config" / "settings.json"
    capabilities = repo / "docs" / "AGENT-CAPABILITIES.md"
    details: dict[str, Any] = {}
    if not settings.is_file():
        return CheckResult("one_sided_hooks", "fail", "Claude settings.json is missing", details)

    try:
        payload = json.loads(settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("one_sided_hooks", "fail", f"settings.json is invalid: {exc}", details)

    hooks = payload.get("hooks") or {}
    details["claude_hook_events"] = sorted(hooks)
    documented = capabilities.is_file() and "Codex hooks are not ported" in capabilities.read_text(
        encoding="utf-8"
    )
    details["codex_gap_documented"] = documented
    if hooks and not documented:
        return CheckResult(
            "one_sided_hooks",
            "fail",
            "Claude hooks exist but the Codex hook gap is not documented",
            details,
        )
    if hooks:
        return CheckResult(
            "one_sided_hooks",
            "warn",
            "Claude hooks exist; Codex hook gap is documented",
            details,
        )
    return CheckResult("one_sided_hooks", "pass", "no one-sided hooks detected", details)


def run_checks(repo: Path, home: Path | None = None) -> ParityReport:
    repo = _repo_root(repo)
    checks = [
        skill_parity_check(repo, home),
        capability_docs_check(repo),
        workflow_tree_check(repo),
        budget_check(repo),
        one_sided_hooks_check(repo),
    ]
    return ParityReport(str(repo), checks)


def render_text(report: ParityReport) -> str:
    lines = [f"agent-parity: {'pass' if report.ok else 'fail'}", f"repo: {report.repo}"]
    for check in report.checks:
        lines.append("")
        lines.append(f"{check.name}: {check.status}")
        lines.append(f"  {check.message}")
        if check.name == "budget_headroom":
            lines.append(
                "  headroom: "
                f"CLAUDE.md {check.details.get('claude_headroom', 'n/a')} lines, "
                f"always-load rules {check.details.get('rules_headroom', 'n/a')} lines"
            )
        if check.name == "skill_parity":
            lines.append(
                "  portable Claude skills: "
                f"{len(check.details.get('portable_claude_skills', []))}"
            )
            lines.append(
                "  Codex-native skills: "
                f"{len(check.details.get('codex_native_skills', []))}"
            )
        if check.name == "one_sided_hooks":
            events = ", ".join(check.details.get("claude_hook_events", [])) or "(none)"
            lines.append(f"  Claude hook events: {events}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-parity")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="report Claude/Codex parity drift")
    check.add_argument("--repo", type=Path, default=Path.cwd(), help="repo root")
    check.add_argument("--home", type=Path, help="installed HOME to verify skill links")
    check.add_argument("--json", action="store_true", help="emit JSON")

    args = parser.parse_args(argv)
    if args.cmd == "check":
        report = run_checks(args.repo, args.home)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_text(report), end="")
        return 0 if report.ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
