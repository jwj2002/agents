from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lib import agent_parity


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "claude-config" / "CLAUDE.md", "line\n")
    _write(repo / "claude-config" / "rules" / "core.md", "---\npaths: [\"**\"]\n---\nrule\n")
    _write(repo / "claude-config" / "settings.json", json.dumps({"hooks": {"Stop": []}}))
    _write(repo / "claude-config" / "install.sh", "#!/bin/sh\n")
    _write(repo / "claude-config" / "commands" / "orchestrate.md", "# Orchestrate\n")
    _write(repo / "claude-config" / "agents" / "patch.md", "# PATCH\n")
    _write(repo / "claude-config" / "hooks" / "verify.py", "print('ok')\n")
    _write(repo / "codex-config" / "install.sh", "#!/bin/sh\n")
    _write(repo / "codex-config" / "AGENTS.md", "# Codex\n")
    _write(repo / "codex-config" / "config.toml.example", "model = 'x'\n")
    _write(repo / "codex-config" / "rules" / "shared.rules", "# rules\n")
    _write(repo / "codex-config" / "skills" / "native" / "SKILL.md", "---\nname: native\n---\n")
    _write(repo / "new-project-agents.sh", "#!/bin/sh\n")
    _write(repo / ".github" / "workflows" / "validate.yml", "name: validate\n")
    _write(
        repo / "docs" / "AGENT-CAPABILITIES.md",
        "Codex hooks are not ported from Claude hooks.\n",
    )

    lint = repo / "claude-config" / "scripts" / "check-skill-portability.sh"
    _write(
        lint,
        "#!/bin/sh\n"
        "if grep -q 'Task tool' \"$1\"; then\n"
        "  echo task-only\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
    )
    lint.chmod(0o755)
    _write(repo / "claude-config" / "skills" / "portable" / "SKILL.md", "portable\n")
    _write(repo / "claude-config" / "skills" / "claude-only" / "SKILL.md", "Task tool\n")
    return repo


def test_skill_parity_enforces_installed_links(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    home = tmp_path / "home"
    for root in (home / ".codex" / "skills", home / ".agents" / "skills"):
        root.mkdir(parents=True)
        os.symlink(repo / "claude-config" / "skills" / "portable", root / "portable")
        os.symlink(repo / "codex-config" / "skills" / "native", root / "native")

    result = agent_parity.skill_parity_check(repo, home)

    assert result.status == "pass"
    assert result.details["portable_claude_skills"] == ["portable"]


def test_skill_parity_fails_missing_installed_link(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    home = tmp_path / "home"
    (home / ".codex" / "skills").mkdir(parents=True)
    (home / ".agents" / "skills").mkdir(parents=True)

    result = agent_parity.skill_parity_check(repo, home)

    assert result.status == "fail"


def test_skill_parity_fails_lint_usage_errors(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "claude-config" / "scripts" / "check-skill-portability.sh").unlink()

    result = agent_parity.skill_parity_check(repo)

    assert result.status == "fail"
    assert "lint" in result.message


def test_workflow_tree_detects_active_legacy_duplicate(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write(repo / "orchestrate-workflow" / "orchestrate.md", "legacy\n")

    result = agent_parity.workflow_tree_check(repo)

    assert result.status == "fail"
    assert "legacy" in result.message


def test_budget_headroom_reports_remaining_lines(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = agent_parity.budget_check(repo)

    assert result.status == "pass"
    assert result.details["claude_headroom"] == agent_parity.CLAUDE_MD_BUDGET - 1
    assert result.details["rules_headroom"] < agent_parity.RULES_BUDGET


def test_one_sided_hooks_are_warning_when_gap_is_documented(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = agent_parity.one_sided_hooks_check(repo)

    assert result.status == "warn"
    assert result.details["codex_gap_documented"] is True


def test_cli_json_runs_against_current_repo() -> None:
    repo = Path(__file__).resolve().parents[2]
    script = repo / "bin" / "agent-parity"

    completed = subprocess.run(
        [sys.executable, str(script), "check", "--repo", str(repo), "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert any(check["name"] == "skill_parity" for check in payload["checks"])
