"""Tests for pulse/cli.py refresh subcommand (#161)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import pulse.cli as cli
from lib import host_resolver as hr
from lib import obsidian_md
from lib import project_resolver as pr


@pytest.fixture(autouse=True)
def _reset():
    hr.clear_cache()
    yield
    hr.clear_cache()


# ---------- vault scaffold ----------

def _write_project_note(
    vaults_base: Path, vault: str, project: str, *,
    host: str = "jns-mac",
    repo_path: str = "~/agents",
    repo_remote: str = "https://github.com/jwj2002/agents.git",
) -> Path:
    projects = vaults_base / vault / "Projects"
    projects.mkdir(parents=True, exist_ok=True)
    fm = {
        "project": project,
        "host": host,
        "client": "personal",
        "kind": "engineering-tool",
        "status": "active",
        "focus": "test focus",
        "status_updated": "2026-05-13",
        "blockers": [],
        "next_steps": [],
        "open_questions": [],
        "stack": [],
        "repo_path": repo_path,
        "repo_remote": repo_remote,
    }
    body = f"# {project}\n\n## Purpose\n\n## Notes\n"
    note = projects / f"{project}.md"
    obsidian_md.write(note, fm, body)
    return note


def _setup(
    monkeypatch, tmp_path: Path, *,
    vaults: dict[str, dict],   # {vault: {"subscribed": [...], "ssh_writes": [...]}}
    local_host: str = "jns-mac",
    projects: list[tuple[str, str, str]] = (),   # (vault, project, host_override)
) -> Path:
    """Standard fixture: subs file, vault dirs, project notes, patched lib paths."""
    vaults_base = tmp_path / "vaults"
    subs_file = tmp_path / "subs.json"
    subs_file.write_text(json.dumps(vaults))

    monkeypatch.setattr(pr, "VAULTS_BASE", vaults_base)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(pr, "get_host_name", lambda: local_host)

    for vault, project, host in projects:
        _write_project_note(vaults_base, vault, project, host=host)
    return vaults_base


def _install_mock_runner(monkeypatch, responses: dict | None = None):
    """Mock subprocess for host_resolver so refresh has predictable git output."""
    calls = []

    def fake_run_local(cmd, *, cwd=None, timeout=10):
        calls.append(list(cmd))
        joined = " ".join(cmd)
        if responses:
            for needle, resp in responses.items():
                if needle in joined:
                    return resp
        return (0, "", "")
    monkeypatch.setattr(hr, "_run_local", fake_run_local)
    return calls


_DEFAULT_GIT_RESPONSES = {
    "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
    "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
    "rev-list": (0, "0\n", ""),
    "status --porcelain": (0, "", ""),
    "log -1 --format": (0, "2026-05-13T10:00:00-07:00|abc1234|test commit\n", ""),
    "--since=24 hours ago": (0, "x\nx\n", ""),
    "--since=7 days ago": (0, "x\nx\nx\nx\n", ""),
    "branch --merged": (0, "  main\n", ""),
    "for-each-ref": (0, "main \n", ""),
    "issue list": (0, "3\n", ""),
}


# ---------- path helpers ----------

def test_project_note_path(tmp_path):
    p = cli.project_note_path("V", "agents", vaults_base=tmp_path)
    assert p == tmp_path / "V" / "Projects" / "agents.md"


def test_sidecar_path(tmp_path):
    p = cli.sidecar_path("V", "agents", "jns-mac", vaults_base=tmp_path)
    assert p == tmp_path / "V" / "Projects" / "_pulse" / "agents--jns-mac.md"


def test_expand_repo_path():
    assert cli._expand_repo_path("~/agents", home=Path("/home/x")) == "/home/x/agents"
    assert cli._expand_repo_path("~", home=Path("/home/x")) == "/home/x"
    assert cli._expand_repo_path("/abs/path", home=Path("/home/x")) == "/abs/path"
    assert cli._expand_repo_path("") == ""


# ---------- refresh_one ----------

def test_refresh_one_local_writes_sidecar(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["agents"], "ssh_writes": []}},
        projects=[("V", "agents", "jns-mac")],
    )
    _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)

    status, path = cli.refresh_one(
        "V", "agents", ssh_writes=[], local_host="jns-mac",
        vaults_base=vaults_base, home=tmp_path,
    )
    assert status == "wrote"
    assert path is not None
    fm, body = obsidian_md.load(path)
    assert fm["project"] == "agents"
    assert fm["host"] == "jns-mac"
    assert fm["reachable"] is True
    assert fm["branch"] == "main"
    assert fm["last_commit_sha"] == "abc1234"
    assert "pulled_at" in fm
    assert fm["open_issues"] == 3
    assert "file body unused" in body


def test_refresh_one_ssh_path(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["agents"], "ssh_writes": ["jbox06"]}},
        projects=[("V", "agents", "jbox06")],
        local_host="jns-mac",
    )
    runner_calls = _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)

    status, path = cli.refresh_one(
        "V", "agents", ssh_writes=["jbox06"], local_host="jns-mac",
        vaults_base=vaults_base, home=tmp_path,
    )
    assert status == "wrote"
    assert path is not None
    fm, _ = obsidian_md.load(path)
    assert fm["host"] == "jbox06"
    # First subprocess call routed through ssh
    assert runner_calls[0][0] == "ssh"
    assert "jbox06" in runner_calls[0]


def test_refresh_one_skipped_when_host_not_owned(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["agents"], "ssh_writes": []}},
        projects=[("V", "agents", "et01")],
        local_host="jns-mac",
    )
    _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)
    status, path = cli.refresh_one(
        "V", "agents", ssh_writes=[], local_host="jns-mac",
        vaults_base=vaults_base, home=tmp_path,
    )
    assert status == "skipped-not-owned"
    assert path is None


def test_refresh_one_skipped_when_note_missing(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["ghost"], "ssh_writes": []}},
        projects=[],
    )
    status, path = cli.refresh_one(
        "V", "ghost", ssh_writes=[], local_host="jns-mac",
        vaults_base=vaults_base, home=tmp_path,
    )
    assert status == "skipped-no-note"
    assert path is None


def test_refresh_one_skipped_when_host_unset(monkeypatch, tmp_path):
    vaults_base = tmp_path / "vaults"
    (vaults_base / "V" / "Projects").mkdir(parents=True)
    note = vaults_base / "V" / "Projects" / "x.md"
    # frontmatter with no host
    obsidian_md.write(note, {"project": "x", "status": "active"}, "body\n")
    monkeypatch.setattr(pr, "VAULTS_BASE", vaults_base)
    monkeypatch.setattr(pr, "get_host_name", lambda: "jns-mac")
    status, path = cli.refresh_one(
        "V", "x", ssh_writes=[], local_host="jns-mac",
        vaults_base=vaults_base, home=tmp_path,
    )
    assert status == "skipped-no-host"


def test_refresh_one_unreachable_writes_sidecar_with_reachable_false(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["agents"], "ssh_writes": []}},
        projects=[("V", "agents", "jns-mac")],
    )
    _install_mock_runner(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (128, "", "fatal: not a git repo"),
    })
    status, path = cli.refresh_one(
        "V", "agents", ssh_writes=[], local_host="jns-mac",
        vaults_base=vaults_base, home=tmp_path,
    )
    assert status == "wrote-unreachable"
    fm, _ = obsidian_md.load(path)
    assert fm["reachable"] is False
    assert "reason" in fm


def test_refresh_one_preserves_last_reachable_at(monkeypatch, tmp_path):
    """When a previously-reachable sidecar becomes unreachable, capture old pulled_at."""
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["agents"], "ssh_writes": []}},
        projects=[("V", "agents", "jns-mac")],
    )
    # Seed an existing reachable sidecar
    side = cli.sidecar_path("V", "agents", "jns-mac", vaults_base=vaults_base)
    side.parent.mkdir(parents=True, exist_ok=True)
    obsidian_md.write(side, {
        "project": "agents", "host": "jns-mac",
        "pulled_at": "2026-05-12T08:00:00Z",
        "reachable": True,
    }, cli.SIDECAR_BODY)
    # Now simulate unreachability
    _install_mock_runner(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (128, "", "fatal"),
    })
    cli.refresh_one(
        "V", "agents", ssh_writes=[], local_host="jns-mac",
        vaults_base=vaults_base, home=tmp_path,
    )
    fm, _ = obsidian_md.load(side)
    assert fm["reachable"] is False
    assert fm["last_reachable_at"] == "2026-05-12T08:00:00Z"


# ---------- write_sidecar / sidecar shape ----------

def test_write_sidecar_includes_all_fields(tmp_path):
    state = hr.RepoState(reachable=True, branch="main", commits_24h=2,
                          commits_7d=10, open_issues=3, ahead_origin=1)
    path = tmp_path / "_pulse" / "p--h.md"
    cli.write_sidecar(path, "p", "h", state, now_iso="2026-05-13T10:00:00Z")
    fm, body = obsidian_md.load(path)
    assert fm["project"] == "p"
    assert fm["host"] == "h"
    assert fm["pulled_at"] == "2026-05-13T10:00:00Z"
    assert fm["branch"] == "main"
    assert fm["commits_24h"] == 2
    assert fm["commits_7d"] == 10
    assert fm["open_issues"] == 3
    assert fm["ahead_origin"] == 1
    assert "stale_local_branches" in fm
    assert "file body unused" in body


def test_sidecar_field_order(tmp_path):
    state = hr.RepoState(reachable=True, branch="main")
    path = tmp_path / "sidecar.md"
    cli.write_sidecar(path, "p", "h", state, now_iso="2026-05-13T10:00:00Z")
    text = path.read_text()
    # project < host < pulled_at < reachable
    assert text.index("project:") < text.index("host:") < text.index("pulled_at:")
    assert text.index("pulled_at:") < text.index("reachable:")


def test_sidecar_omits_reason_when_reachable(tmp_path):
    state = hr.RepoState(reachable=True)
    path = tmp_path / "s.md"
    cli.write_sidecar(path, "p", "h", state)
    fm, _ = obsidian_md.load(path)
    assert "reason" not in fm


def test_sidecar_atomic_no_tmp(tmp_path):
    state = hr.RepoState(reachable=True)
    path = tmp_path / "side" / "s.md"
    cli.write_sidecar(path, "p", "h", state)
    assert not list(path.parent.glob("*.tmp*"))


# ---------- refresh_vault / refresh_all ----------

def test_refresh_vault_processes_all_subscribed(monkeypatch, tmp_path, capsys):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["a", "b"], "ssh_writes": []}},
        projects=[("V", "a", "jns-mac"), ("V", "b", "jns-mac")],
    )
    _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)
    summary = cli.refresh_vault(
        "V", {"subscribed": ["a", "b"], "ssh_writes": []},
        local_host="jns-mac", vaults_base=vaults_base, home=tmp_path,
    )
    assert summary.get("wrote") == 2
    pulse_dir = vaults_base / "V" / "Projects" / "_pulse"
    assert (pulse_dir / "a--jns-mac.md").exists()
    assert (pulse_dir / "b--jns-mac.md").exists()


def test_refresh_vault_project_filter(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["a", "b"], "ssh_writes": []}},
        projects=[("V", "a", "jns-mac"), ("V", "b", "jns-mac")],
    )
    _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)
    summary = cli.refresh_vault(
        "V", {"subscribed": ["a", "b"], "ssh_writes": []},
        local_host="jns-mac", project_filter="a",
        vaults_base=vaults_base, home=tmp_path,
    )
    assert summary.get("wrote") == 1
    assert (vaults_base / "V" / "Projects" / "_pulse" / "a--jns-mac.md").exists()
    assert not (vaults_base / "V" / "Projects" / "_pulse" / "b--jns-mac.md").exists()


def test_refresh_all_aggregates_across_vaults(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={
            "V1": {"subscribed": ["a"], "ssh_writes": []},
            "V2": {"subscribed": ["b"], "ssh_writes": []},
        },
        projects=[("V1", "a", "jns-mac"), ("V2", "b", "jns-mac")],
    )
    _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)
    summary = cli.refresh_all(vaults_base=vaults_base, home=tmp_path)
    assert summary.get("wrote") == 2


def test_refresh_all_vault_filter(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={
            "V1": {"subscribed": ["a"], "ssh_writes": []},
            "V2": {"subscribed": ["b"], "ssh_writes": []},
        },
        projects=[("V1", "a", "jns-mac"), ("V2", "b", "jns-mac")],
    )
    _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)
    summary = cli.refresh_all(vault_filter="V1", vaults_base=vaults_base, home=tmp_path)
    assert summary.get("wrote") == 1


# ---------- main() integration ----------

def test_main_refresh_invocation(monkeypatch, tmp_path, capsys):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["a"], "ssh_writes": []}},
        projects=[("V", "a", "jns-mac")],
    )
    _install_mock_runner(monkeypatch, _DEFAULT_GIT_RESPONSES)
    rc = cli.main(["refresh", "--vaults-base", str(vaults_base)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wrote: 1" in out


def test_main_no_subcommand_errors():
    """argparse with `required=True` subparser raises SystemExit(2) on empty args."""
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


# ---------- list_sidecars ----------

def test_list_sidecars_returns_all_hosts_for_project(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["x"], "ssh_writes": []}},
        projects=[("V", "x", "jns-mac")],
    )
    # Drop two sidecars for the same project on different hosts
    pulse_dir = vaults_base / "V" / "Projects" / "_pulse"
    pulse_dir.mkdir(parents=True)
    for host in ("jns-mac", "jbox06"):
        obsidian_md.write(pulse_dir / f"x--{host}.md", {
            "project": "x", "host": host, "pulled_at": "2026-05-13T10:00:00Z",
            "reachable": True, "branch": "main",
        }, cli.SIDECAR_BODY)
    out = cli.list_sidecars("V", "x", vaults_base=vaults_base)
    hosts = [fm["host"] for _, fm in out]
    assert hosts == ["jbox06", "jns-mac"]


def test_list_sidecars_filters_to_project(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["x", "y"], "ssh_writes": []}},
        projects=[],
    )
    pulse_dir = vaults_base / "V" / "Projects" / "_pulse"
    pulse_dir.mkdir(parents=True)
    for p, h in [("x", "jns-mac"), ("y", "jns-mac")]:
        obsidian_md.write(pulse_dir / f"{p}--{h}.md", {
            "project": p, "host": h, "pulled_at": "2026-05-13T10:00:00Z",
            "reachable": True,
        }, cli.SIDECAR_BODY)
    out = cli.list_sidecars("V", "x", vaults_base=vaults_base)
    assert len(out) == 1
    assert out[0][1]["project"] == "x"


def test_list_sidecars_empty_when_no_pulse_dir(monkeypatch, tmp_path):
    vaults_base = _setup(monkeypatch, tmp_path, vaults={"V": {}}, projects=[])
    assert cli.list_sidecars("V", "anything", vaults_base=vaults_base) == []


# ---------- render_report ----------

def test_render_report_basic(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["agents"], "ssh_writes": []}},
        projects=[("V", "agents", "jns-mac")],
    )
    pulse_dir = vaults_base / "V" / "Projects" / "_pulse"
    pulse_dir.mkdir(parents=True)
    obsidian_md.write(pulse_dir / "agents--jns-mac.md", {
        "project": "agents", "host": "jns-mac",
        "pulled_at": "2026-05-13T17:00:00Z",
        "reachable": True,
        "last_commit_subject": "feat: x",
        "commits_24h": 4, "commits_7d": 12,
        "open_actions": 1, "open_issues": 5,
        "branch": "main", "ahead_origin": 0, "behind_origin": 0,
        "dirty": False, "stale_local_branches": [], "unpushed_branches": [],
    }, cli.SIDECAR_BODY)

    out = cli.render_report("V", "agents", vaults_base=vaults_base)
    assert "# agents" in out
    assert "**Status**: ACTIVE" in out
    assert "**Focus**: test focus" in out
    assert "## Activity (per host)" in out
    assert "feat: x" in out
    assert "jns-mac" in out


def test_render_report_missing_note(monkeypatch, tmp_path):
    vaults_base = _setup(monkeypatch, tmp_path, vaults={"V": {}}, projects=[])
    out = cli.render_report("V", "ghost", vaults_base=vaults_base)
    assert "ghost" in out
    assert "Project note not found" in out


def test_render_report_no_sidecars_yet(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["x"], "ssh_writes": []}},
        projects=[("V", "x", "jns-mac")],
    )
    out = cli.render_report("V", "x", vaults_base=vaults_base)
    assert "no sidecars yet" in out


def test_render_report_includes_blockers_and_questions(monkeypatch, tmp_path):
    vaults_base = tmp_path / "vaults"
    (vaults_base / "V" / "Projects").mkdir(parents=True)
    obsidian_md.write(vaults_base / "V" / "Projects" / "x.md", {
        "project": "x", "host": "jns-mac", "status": "blocked",
        "focus": "stuck",
        "blockers": ["waiting on infra"],
        "next_steps": ["call infra"],
        "open_questions": ["which region?"],
    }, "body\n")
    monkeypatch.setattr(pr, "VAULTS_BASE", vaults_base)
    out = cli.render_report("V", "x", vaults_base=vaults_base)
    assert "## Blockers" in out
    assert "waiting on infra" in out
    assert "## Next steps" in out
    assert "call infra" in out
    assert "## Open questions" in out
    assert "which region?" in out


def test_render_report_git_hygiene_section_appears(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["x"], "ssh_writes": []}},
        projects=[("V", "x", "jns-mac")],
    )
    pulse_dir = vaults_base / "V" / "Projects" / "_pulse"
    pulse_dir.mkdir(parents=True)
    obsidian_md.write(pulse_dir / "x--jns-mac.md", {
        "project": "x", "host": "jns-mac", "pulled_at": "2026-05-13T17:00:00Z",
        "reachable": True, "branch": "main",
        "dirty": True, "ahead_origin": 3, "behind_origin": 0,
        "stale_local_branches": ["old"], "unpushed_branches": [],
    }, cli.SIDECAR_BODY)
    out = cli.render_report("V", "x", vaults_base=vaults_base)
    assert "## Git — needs attention" in out
    assert "dirty" in out
    assert "3↑" in out
    assert "stale local: 1" in out


# ---------- render_vault_digest ----------

def test_render_vault_digest_lists_projects(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["a", "b"], "ssh_writes": []}},
        projects=[("V", "a", "jns-mac"), ("V", "b", "jns-mac")],
    )
    pulse_dir = vaults_base / "V" / "Projects" / "_pulse"
    pulse_dir.mkdir(parents=True)
    for p in ("a", "b"):
        obsidian_md.write(pulse_dir / f"{p}--jns-mac.md", {
            "project": p, "host": "jns-mac",
            "pulled_at": "2026-05-13T17:00:00Z", "reachable": True,
            "last_commit_subject": f"latest in {p}",
            "commits_24h": 1, "commits_7d": 5,
            "open_actions": 0, "open_issues": 2,
        }, cli.SIDECAR_BODY)

    out = cli.render_vault_digest("V", vaults_base=vaults_base, window="weekly")
    assert "# V — digest (weekly" in out
    assert "## a — active" in out
    assert "## b — active" in out
    assert "latest in a" in out
    assert "latest in b" in out


def test_render_vault_digest_handles_missing_subscription(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, vaults={"V": {}}, projects=[])
    out = cli.render_vault_digest("Other", vaults_base=tmp_path / "vaults", window="daily")
    assert "Vault not in subscription" in out


def test_render_vault_digest_no_subscribed_projects(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, vaults={"V": {"subscribed": [], "ssh_writes": []}}, projects=[])
    out = cli.render_vault_digest("V", vaults_base=tmp_path / "vaults", window="daily")
    assert "No subscribed projects" in out


# ---------- render_all_vaults_digest ----------

def test_all_vaults_digest_jns_mac_only(monkeypatch, tmp_path):
    _setup(
        monkeypatch, tmp_path,
        vaults={"V1": {"subscribed": [], "ssh_writes": []}},
        projects=[],
        local_host="vitalai-laptop",
    )
    with pytest.raises(cli.PulseError, match="jns-mac-only"):
        cli.render_all_vaults_digest(vaults_base=tmp_path / "vaults")


def test_all_vaults_digest_concats_on_jns_mac(monkeypatch, tmp_path):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={
            "V1": {"subscribed": ["a"], "ssh_writes": []},
            "V2": {"subscribed": ["b"], "ssh_writes": []},
        },
        projects=[("V1", "a", "jns-mac"), ("V2", "b", "jns-mac")],
        local_host="jns-mac",
    )
    out = cli.render_all_vaults_digest(vaults_base=vaults_base)
    assert "# V1 —" in out
    assert "# V2 —" in out


# ---------- main() report + digest ----------

def test_main_report_renders(monkeypatch, tmp_path, capsys):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["x"], "ssh_writes": []}},
        projects=[("V", "x", "jns-mac")],
    )
    rc = cli.main(["report", "--project", "x", "--vault", "V",
                   "--vaults-base", str(vaults_base)])
    assert rc == 0
    assert "# x" in capsys.readouterr().out


def test_main_report_auto_resolves_vault(monkeypatch, tmp_path, capsys):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["x"], "ssh_writes": []}},
        projects=[("V", "x", "jns-mac")],
    )
    rc = cli.main(["report", "--project", "x", "--vaults-base", str(vaults_base)])
    assert rc == 0


def test_main_digest_vault(monkeypatch, tmp_path, capsys):
    vaults_base = _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": ["x"], "ssh_writes": []}},
        projects=[("V", "x", "jns-mac")],
    )
    rc = cli.main(["digest", "--vault", "V", "--vaults-base", str(vaults_base)])
    assert rc == 0
    assert "# V —" in capsys.readouterr().out


def test_main_digest_all_vaults_refused_on_non_jns_mac(monkeypatch, tmp_path, capsys):
    _setup(
        monkeypatch, tmp_path,
        vaults={"V": {"subscribed": [], "ssh_writes": []}},
        projects=[],
        local_host="vitalai-laptop",
    )
    rc = cli.main(["digest", "--all-vaults",
                   "--vaults-base", str(tmp_path / "vaults")])
    assert rc == 1
    assert "jns-mac-only" in capsys.readouterr().err
