"""Tests for bootstrap-laptop.sh (#164).

Run the script via subprocess against a tmp HOME with BOOTSTRAP_OS overrides.
Coverage: OS branching, host-name registration, idempotency, FileVault
warning path (mocked), WSL symlink, plugin seeding, git remote allowlist.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "bootstrap-laptop.sh"


def _run(
    *args: str,
    home: Path,
    os_override: str | None = None,
    extra_env: dict | None = None,
    path_override: str | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["BOOTSTRAP_HOME"] = str(home)
    if os_override is not None:
        env["BOOTSTRAP_OS"] = os_override
    if path_override is not None:
        env["PATH"] = path_override
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, env=env, check=False,
    )


# ---------- bash syntax ----------

def test_bootstrap_passes_bash_syntax_check():
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---------- OS branching ----------

def test_linux_branch_skips_platform_specific(tmp_path):
    r = _run("--noninteractive", "--host-name", "test", home=tmp_path, os_override="linux")
    assert r.returncode == 0, r.stderr
    assert "OS: linux" in r.stdout
    # Linux skips both FileVault and WSL symlink blocks
    assert "FileVault" not in r.stdout
    assert "WSL vault symlink" not in r.stdout


def test_macos_branch_runs_filevault_check(tmp_path):
    r = _run("--noninteractive", "--host-name", "test", home=tmp_path, os_override="macos")
    assert r.returncode == 0, r.stderr
    assert "OS: macos" in r.stdout
    assert "FileVault" in r.stdout


def test_wsl_branch_runs_symlink_setup(tmp_path):
    r = _run("--noninteractive", "--host-name", "test", home=tmp_path, os_override="wsl")
    # WSL branch may fail to create /mnt/c/... on a non-WSL host, but the
    # block must at least RUN (visible in stdout/stderr).
    assert "WSL vault symlink" in r.stdout


# ---------- host name ----------

def test_host_name_flag_writes_file(tmp_path):
    r = _run("--noninteractive", "--host-name", "jns-mac",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0, r.stderr
    host_file = tmp_path / ".claude" / "host-name"
    assert host_file.read_text().strip() == "jns-mac"


def test_host_name_preserved_on_rerun(tmp_path):
    _run("--noninteractive", "--host-name", "jns-mac",
         home=tmp_path, os_override="linux")
    # Re-run without explicit host name — should keep existing
    r = _run("--noninteractive", home=tmp_path, os_override="linux")
    assert r.returncode == 0
    assert (tmp_path / ".claude" / "host-name").read_text().strip() == "jns-mac"
    assert "already set: jns-mac" in r.stdout


def test_host_name_override_via_rerun(tmp_path):
    _run("--noninteractive", "--host-name", "first",
         home=tmp_path, os_override="linux")
    r = _run("--noninteractive", "--host-name", "second",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    assert (tmp_path / ".claude" / "host-name").read_text().strip() == "second"


def test_host_name_noninteractive_falls_back_to_uname(tmp_path):
    r = _run("--noninteractive", home=tmp_path, os_override="linux")
    assert r.returncode == 0
    host = (tmp_path / ".claude" / "host-name").read_text().strip()
    assert host  # non-empty


# ---------- idempotency ----------

def test_full_idempotency(tmp_path):
    args = ["--noninteractive", "--host-name", "test"]
    first = _run(*args, home=tmp_path, os_override="linux")
    assert first.returncode == 0
    second = _run(*args, home=tmp_path, os_override="linux")
    assert second.returncode == 0
    # Critical files are identical after two runs
    host_after = (tmp_path / ".claude" / "host-name").read_text()
    assert host_after.strip() == "test"


# ---------- required tools ----------

def test_missing_required_tool_errors_clearly(tmp_path):
    """Restrict PATH to a dir that has bash but not jq/git/python3 → clean error."""
    fake_path = tmp_path / "empty-path"
    fake_path.mkdir()
    # Link only bash into the fake path so the script can start but tool checks fail
    (fake_path / "bash").symlink_to(shutil.which("bash"))
    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux",
             path_override=str(fake_path))
    assert r.returncode == 2
    assert "missing required tools" in r.stderr


# ---------- plugin seeding ----------

def test_plugin_seeding_writes_to_subscribed_vaults(tmp_path):
    # Subscriptions + vaults present
    subs = {"V1": {"subscribed": [], "ssh_writes": []},
            "V2": {"subscribed": [], "ssh_writes": []}}
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "dashboard-subscriptions.json").write_text(json.dumps(subs))
    (tmp_path / "vaults" / "V1").mkdir(parents=True)
    (tmp_path / "vaults" / "V2").mkdir(parents=True)

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0, r.stderr

    for v in ("V1", "V2"):
        manifest = tmp_path / "vaults" / v / ".obsidian" / "community-plugins.json"
        assert manifest.exists()
        plugins = json.loads(manifest.read_text())
        assert "dataview" in plugins
        assert "templater-obsidian" in plugins
        assert "obsidian-tasks-plugin" in plugins


def test_plugin_seeding_idempotent(tmp_path):
    subs = {"V1": {"subscribed": [], "ssh_writes": []}}
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "dashboard-subscriptions.json").write_text(json.dumps(subs))
    (tmp_path / "vaults" / "V1").mkdir(parents=True)

    _run("--noninteractive", "--host-name", "test",
         home=tmp_path, os_override="linux")
    r = _run("--noninteractive", home=tmp_path, os_override="linux")
    assert r.returncode == 0
    assert "all subscribed vaults already have plugin manifests" in r.stdout


def test_plugin_seeding_skipped_without_subscriptions(tmp_path):
    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    assert "skip: no subscriptions file" in r.stdout


# ---------- git remote allowlist ----------

def _git_available() -> bool:
    return shutil.which("git") is not None


@pytest.mark.skipif(not _git_available(), reason="git not installed")
def test_allowlist_adds_remote_when_repo_has_none(tmp_path):
    """Vault is a git repo with no remote → bootstrap adds origin from config."""
    (tmp_path / ".claude").mkdir()
    cfg = "MyVault: git@example.com:repo.git\n"
    (tmp_path / ".claude" / "vault-remotes.yaml").write_text(cfg)
    subs = {"MyVault": {"subscribed": [], "ssh_writes": []}}
    (tmp_path / ".claude" / "dashboard-subscriptions.json").write_text(json.dumps(subs))
    vault = tmp_path / "vaults" / "MyVault"
    vault.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True)

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0, r.stderr
    origin = subprocess.check_output(
        ["git", "-C", str(vault), "remote", "get-url", "origin"],
        text=True,
    ).strip()
    assert origin == "git@example.com:repo.git"


@pytest.mark.skipif(not _git_available(), reason="git not installed")
def test_allowlist_warns_on_mismatch(tmp_path):
    """Vault has a different remote than the config → warning, no rewrite."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "vault-remotes.yaml").write_text(
        "MyVault: git@example.com:expected.git\n"
    )
    subs = {"MyVault": {"subscribed": [], "ssh_writes": []}}
    (tmp_path / ".claude" / "dashboard-subscriptions.json").write_text(json.dumps(subs))
    vault = tmp_path / "vaults" / "MyVault"
    vault.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
    subprocess.run(
        ["git", "-C", str(vault), "remote", "add", "origin", "git@example.com:wrong.git"],
        check=True,
    )

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    assert "origin mismatch" in r.stderr
    # Confirm: bootstrap did NOT auto-rewrite the remote
    origin = subprocess.check_output(
        ["git", "-C", str(vault), "remote", "get-url", "origin"],
        text=True,
    ).strip()
    assert origin == "git@example.com:wrong.git"


@pytest.mark.skipif(not _git_available(), reason="git not installed")
def test_allowlist_ok_when_remote_matches(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "vault-remotes.yaml").write_text(
        "MyVault: git@example.com:right.git\n"
    )
    subs = {"MyVault": {"subscribed": [], "ssh_writes": []}}
    (tmp_path / ".claude" / "dashboard-subscriptions.json").write_text(json.dumps(subs))
    vault = tmp_path / "vaults" / "MyVault"
    vault.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
    subprocess.run(
        ["git", "-C", str(vault), "remote", "add", "origin", "git@example.com:right.git"],
        check=True,
    )

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0, r.stderr
    assert "origin OK" in r.stdout


def test_allowlist_skipped_without_config(tmp_path):
    """No ~/.claude/vault-remotes.yaml → allowlist enforcement is a no-op."""
    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    assert "allowlist enforcement is opt-in" in r.stdout


# ---------- subscription recovery (Codex 2026-05-13 #2) ----------

def _write_project_note(path: Path, project: str) -> None:
    """Minimal Path B project note used by recovery tests."""
    path.write_text(
        "---\n"
        f"project: {project}\n"
        "host: jns-mac\n"
        "client: personal\n"
        "kind: personal\n"
        "status: active\n"
        "---\n\n"
        f"# {project}\n"
    )


def test_recovery_rebuilds_subscriptions_from_vaults(tmp_path):
    """Fresh device: vault has project notes, no subscription file → recovery writes it."""
    (tmp_path / "vaults" / "JNS-Personal-Vault" / "Projects").mkdir(parents=True)
    for project in ("agents", "buddy", "paul-jason"):
        _write_project_note(
            tmp_path / "vaults" / "JNS-Personal-Vault" / "Projects" / f"{project}.md",
            project,
        )

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0, r.stderr

    subs_file = tmp_path / ".claude" / "dashboard-subscriptions.json"
    assert subs_file.exists()
    data = json.loads(subs_file.read_text())
    assert "JNS-Personal-Vault" in data
    assert data["JNS-Personal-Vault"]["subscribed"] == ["agents", "buddy", "paul-jason"]
    assert data["JNS-Personal-Vault"]["ssh_writes"] == []
    assert "recovered: 1 vault(s), 3 project subscription(s)" in r.stdout


def test_recovery_preserves_populated_subscriptions(tmp_path):
    """If subscription file already has entries, recovery is a no-op."""
    (tmp_path / ".claude").mkdir()
    existing = {"User-Vault": {"subscribed": ["agents"], "ssh_writes": ["jbox06"]}}
    (tmp_path / ".claude" / "dashboard-subscriptions.json").write_text(json.dumps(existing))
    # Also create vaults that recovery WOULD discover if it ran
    (tmp_path / "vaults" / "DiscoverMe" / "Projects").mkdir(parents=True)
    _write_project_note(
        tmp_path / "vaults" / "DiscoverMe" / "Projects" / "new.md", "new"
    )

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    # File unchanged
    after = json.loads((tmp_path / ".claude" / "dashboard-subscriptions.json").read_text())
    assert after == existing
    assert "already populated" in r.stdout


def test_recovery_rebuilds_when_file_is_empty(tmp_path):
    """If subscription file exists but has no populated vaults, recovery rebuilds."""
    (tmp_path / ".claude").mkdir()
    # Empty / no-entries shape
    (tmp_path / ".claude" / "dashboard-subscriptions.json").write_text("{}\n")
    (tmp_path / "vaults" / "V" / "Projects").mkdir(parents=True)
    _write_project_note(tmp_path / "vaults" / "V" / "Projects" / "agents.md", "agents")

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    data = json.loads((tmp_path / ".claude" / "dashboard-subscriptions.json").read_text())
    assert data == {"V": {"subscribed": ["agents"], "ssh_writes": []}}


def test_recovery_skipped_when_no_vaults_base(tmp_path):
    """No ~/vaults/ dir → recovery gracefully skips."""
    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    assert "no" in r.stdout and "vaults" in r.stdout


def test_recovery_ignores_archived_and_dot_dirs(tmp_path):
    """Recovery must skip _archived/ and .hidden/ under ~/vaults/."""
    base = tmp_path / "vaults"
    # Real vault
    (base / "Real" / "Projects").mkdir(parents=True)
    _write_project_note(base / "Real" / "Projects" / "agents.md", "agents")
    # Archived — must be ignored
    (base / "_archived" / "OldVault" / "Projects").mkdir(parents=True)
    _write_project_note(base / "_archived" / "OldVault" / "Projects" / "ghost.md", "ghost")
    # Hidden — must be ignored
    (base / ".hidden" / "Projects").mkdir(parents=True)
    _write_project_note(base / ".hidden" / "Projects" / "x.md", "x")

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    data = json.loads((tmp_path / ".claude" / "dashboard-subscriptions.json").read_text())
    assert list(data.keys()) == ["Real"]


def test_recovery_handles_vault_with_no_projects_dir(tmp_path):
    """A vault dir that doesn't have Projects/ yet is skipped silently."""
    base = tmp_path / "vaults"
    (base / "Empty").mkdir(parents=True)  # no Projects/
    (base / "Real" / "Projects").mkdir(parents=True)
    _write_project_note(base / "Real" / "Projects" / "a.md", "a")

    r = _run("--noninteractive", "--host-name", "test",
             home=tmp_path, os_override="linux")
    assert r.returncode == 0
    data = json.loads((tmp_path / ".claude" / "dashboard-subscriptions.json").read_text())
    assert list(data.keys()) == ["Real"]


def test_recovery_idempotent_across_two_runs(tmp_path):
    """Run twice; second run sees populated subscriptions and no-ops."""
    (tmp_path / "vaults" / "V" / "Projects").mkdir(parents=True)
    _write_project_note(tmp_path / "vaults" / "V" / "Projects" / "agents.md", "agents")

    first = _run("--noninteractive", "--host-name", "test",
                  home=tmp_path, os_override="linux")
    assert first.returncode == 0
    first_data = json.loads((tmp_path / ".claude" / "dashboard-subscriptions.json").read_text())

    second = _run("--noninteractive", home=tmp_path, os_override="linux")
    assert second.returncode == 0
    assert "already populated" in second.stdout
    after = json.loads((tmp_path / ".claude" / "dashboard-subscriptions.json").read_text())
    assert after == first_data  # unchanged


# ---------- help ----------

def test_help_flag(tmp_path):
    r = _run("--help", home=tmp_path)
    assert r.returncode == 0
    assert "bootstrap-laptop.sh" in r.stdout
    assert "Idempotent" in r.stdout
