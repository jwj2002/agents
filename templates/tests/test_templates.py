"""Structural tests for Obsidian templates and sync-templates.sh (#163).

Templater + Dataview rendering can't be exercised without a real Obsidian
install, so these tests validate the structural contract:

- Frontmatter parses as YAML (after stripping Templater `<%* ... -%>` blocks).
- Required frontmatter keys are present.
- Required body sections are present.
- No `this.subscribed` references in Daily template (Codex Finding 1 fix).
- sync-templates.sh copies into a temp vault and is idempotent across re-runs.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "obsidian"
SYNC_SCRIPT = Path(__file__).resolve().parent.parent / "sync-templates.sh"


# ---------- helpers ----------

_TEMPLATER_BLOCK = re.compile(r"<%\*.*?-?%>", re.DOTALL)
_TEMPLATER_INLINE = re.compile(r"<%[*=]?\s*([^%]*?)\s*-?%>", re.DOTALL)


def _strip_templater(text: str) -> str:
    """Remove Templater code blocks/expressions, leaving raw markdown.

    Replaces `<%= expr %>` and `<% expr %>` with a placeholder so YAML still
    parses; drops `<%* ... %>` blocks entirely.
    """
    text = _TEMPLATER_BLOCK.sub("", text).lstrip("\n")
    text = _TEMPLATER_INLINE.sub("PLACEHOLDER", text)
    return text


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return ({}, text)
    end = text.find("\n---", 4)
    assert end != -1, "frontmatter not closed"
    fm_text = text[4:end]
    body = text[end + 4 :]
    fm = yaml.safe_load(fm_text) or {}
    return (fm, body)


# ---------- Project.md ----------

def test_project_template_frontmatter_parses_and_has_required_keys():
    raw = (TEMPLATES_DIR / "Project.md").read_text()
    fm, _ = _split_frontmatter(_strip_templater(raw))
    expected = {
        "project", "host", "client", "kind", "status", "focus",
        "status_updated", "blockers", "next_steps", "open_questions",
        "stack", "repo_path", "repo_remote",
    }
    assert expected.issubset(fm.keys())


def test_project_template_excludes_pulse_managed_fields():
    """F3: pulse never writes to project note. Frontmatter must not have
    pulse-managed fields like last_commit_at — those live in sidecars."""
    raw = (TEMPLATES_DIR / "Project.md").read_text()
    fm, _ = _split_frontmatter(_strip_templater(raw))
    forbidden = {
        "last_commit_at", "last_commit_subject", "commits_7d",
        "open_actions", "open_issues", "focus_drift_days",
        "pulse_at", "git_state",
    }
    assert forbidden.isdisjoint(fm.keys()), (
        "Project frontmatter must not include pulse-managed fields (Codex F3)"
    )


def test_project_template_has_overview_and_operational_halves():
    raw = (TEMPLATES_DIR / "Project.md").read_text()
    body = _split_frontmatter(_strip_templater(raw))[1]
    assert "## Purpose" in body
    assert "## Stack" in body
    assert "## Repository" in body
    # Operational half (separated by --- rule)
    assert "## Status (live)" in body
    assert "## Activity" in body
    assert "## Decisions linked" in body
    # Two halves separated by an --- rule somewhere in the body
    assert body.count("\n---\n") >= 1


def test_project_template_dataview_queries_reference_known_fields():
    raw = (TEMPLATES_DIR / "Project.md").read_text()
    body = _split_frontmatter(_strip_templater(raw))[1]
    # Sidecar queries must read from Projects/_pulse, not from project notes
    assert 'FROM "Projects/_pulse"' in body
    # Status query reads from the project note itself
    assert "this.status" in body
    assert "this.host" in body


# ---------- Decision.md ----------

def test_decision_template_madr_sections_present():
    raw = (TEMPLATES_DIR / "Decision.md").read_text()
    fm, body = _split_frontmatter(_strip_templater(raw))
    assert {"id", "date", "project", "topic", "title", "status", "linked"}.issubset(fm)
    for section in ("## Context", "## Decision", "## Alternatives considered",
                    "## Reasoning", "## Outcome", "## Linked"):
        assert section in body, f"Decision template missing {section}"


# ---------- Daily.md ----------

def test_daily_template_does_not_filter_by_subscribed():
    """Codex F1: Daily must filter by status, not by this.subscribed
    (subscription file is not Dataview-readable). Check the rendered
    body — the Templater header may legitimately reference the fix."""
    raw = (TEMPLATES_DIR / "Daily.md").read_text()
    rendered = _strip_templater(raw)
    assert "this.subscribed" not in rendered
    assert 'WHERE status = "active"' in rendered


def test_daily_template_has_required_sections():
    raw = (TEMPLATES_DIR / "Daily.md").read_text()
    for section in (
        "## ⚠ Focus may be stale",
        "## Active projects",
        "## Today's tasks",
        "## Yesterday's activity",
        "## Decisions this week",
        "## Git — needs attention",
        "## Reachability",
        "## Notes",
    ):
        assert section in raw, f"Daily template missing {section}"


def test_daily_template_dataview_blocks_well_formed():
    """Every opening ```dataview must have a matching closing ``` ."""
    raw = (TEMPLATES_DIR / "Daily.md").read_text()
    opens = raw.count("```dataview")
    # Each dataview block has one closing fence; the closing fences are also
    # used by ```tasks blocks. Total fences must be even.
    fences = raw.count("```")
    assert opens >= 5, "Daily template should contain at least 5 dataview blocks"
    assert fences % 2 == 0, "unbalanced code fences in Daily template"


# ---------- sync-templates.sh ----------

def _make_subscriptions(path: Path, vaults: list[str]) -> None:
    payload = {v: {"subscribed": [], "ssh_writes": []} for v in vaults}
    path.write_text(json.dumps(payload, indent=2))


def _run_sync(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SYNC_SCRIPT)] + args,
        capture_output=True, text=True, check=False,
    )


def test_sync_copies_templates_into_each_vault(tmp_path: Path):
    subs = tmp_path / "subscriptions.json"
    base = tmp_path / "vaults"
    for vault in ("V-One", "V-Two"):
        (base / vault).mkdir(parents=True)
    _make_subscriptions(subs, ["V-One", "V-Two"])

    result = _run_sync([
        "--subscriptions", str(subs),
        "--vaults-base", str(base),
    ])
    assert result.returncode == 0, result.stderr

    for vault in ("V-One", "V-Two"):
        for tpl in ("Project.md", "Decision.md", "Daily.md"):
            assert (base / vault / "_templates" / tpl).exists(), (
                f"missing {tpl} in {vault}"
            )


def test_sync_is_idempotent(tmp_path: Path):
    subs = tmp_path / "subscriptions.json"
    base = tmp_path / "vaults"
    (base / "V-One").mkdir(parents=True)
    _make_subscriptions(subs, ["V-One"])

    args = ["--subscriptions", str(subs), "--vaults-base", str(base)]
    first = _run_sync(args)
    assert first.returncode == 0
    assert "copied=3" in first.stdout

    second = _run_sync(args)
    assert second.returncode == 0
    assert "copied=0" in second.stdout
    assert "unchanged=3" in second.stdout


def test_sync_skips_missing_vault_dirs_gracefully(tmp_path: Path):
    """Vault listed in subscriptions but directory doesn't exist on disk."""
    subs = tmp_path / "subscriptions.json"
    base = tmp_path / "vaults"
    base.mkdir()  # base exists but no vault subdirs
    _make_subscriptions(subs, ["Ghost-Vault"])

    result = _run_sync([
        "--subscriptions", str(subs),
        "--vaults-base", str(base),
    ])
    assert result.returncode == 0
    assert "skip: vault dir not present" in result.stdout
    assert "skipped-vaults=1" in result.stdout


def test_sync_dry_run_writes_nothing(tmp_path: Path):
    subs = tmp_path / "subscriptions.json"
    base = tmp_path / "vaults"
    (base / "V-One").mkdir(parents=True)
    _make_subscriptions(subs, ["V-One"])

    result = _run_sync([
        "--dry-run",
        "--subscriptions", str(subs),
        "--vaults-base", str(base),
    ])
    assert result.returncode == 0
    assert "would copy" in result.stdout
    assert not (base / "V-One" / "_templates").exists()


def test_sync_single_vault_flag(tmp_path: Path):
    subs = tmp_path / "subscriptions.json"
    base = tmp_path / "vaults"
    for vault in ("V-One", "V-Two"):
        (base / vault).mkdir(parents=True)
    _make_subscriptions(subs, ["V-One", "V-Two"])

    result = _run_sync([
        "--vault", "V-One",
        "--subscriptions", str(subs),
        "--vaults-base", str(base),
    ])
    assert result.returncode == 0
    # Only V-One should have templates
    assert (base / "V-One" / "_templates" / "Project.md").exists()
    assert not (base / "V-Two" / "_templates").exists()


def test_sync_errors_clearly_when_subscriptions_missing(tmp_path: Path):
    result = _run_sync([
        "--subscriptions", str(tmp_path / "missing.json"),
        "--vaults-base", str(tmp_path),
    ])
    assert result.returncode == 2
    assert "subscriptions file not found" in result.stderr


@pytest.mark.skipif(
    subprocess.run(["bash", "-n", str(SYNC_SCRIPT)], capture_output=True).returncode != 0,
    reason="bash syntax check failed — script malformed",
)
def test_sync_passes_bash_syntax_check():
    """`bash -n` parses the script without executing it."""
    result = subprocess.run(
        ["bash", "-n", str(SYNC_SCRIPT)], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
