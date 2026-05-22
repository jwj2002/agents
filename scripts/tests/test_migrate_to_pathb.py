"""Tests for scripts/migrate-to-pathb.py (#168).

Covers:
- Field mapping (1:1, renamed, dropped, destination-only)
- Frontmatter field order
- Body sections present (Dataview operational half + minimal overview)
- Kind heuristic (agents → engineering-tool, else → personal)
- repo_path detection
- repo_remote: empty when repo dir absent
- Subscription cutover (legacy → vault-keyed, idempotent, backup)
- Dry-run writes nothing
- --force overwrites existing destinations; default refuses
- Idempotency across full second run
- Atomic write (no .tmp leftovers)
- Errors clearly on malformed source YAML
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Load the hyphen-named script as a module.
_SCRIPT = Path(__file__).resolve().parent.parent / "migrate-to-pathb.py"
_spec = importlib.util.spec_from_file_location("migrate_to_pathb", _SCRIPT)
mp = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mp)

# Also load obsidian_md for fixture verification.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import obsidian_md  # noqa: E402


# ---------- fixtures ----------

_FULL_YAML = """\
schema_version: 1
project: testproj
host: jns-mac
status: active
focus: A real focus
next_steps:
  - first
  - second
blockers: []
open_questions:
  - what about edge cases?
specs: []
dependencies: []
updated_at: 2026-05-08
updated_by: jason
"""

_MINIMAL_YAML = """\
project: tiny
status: active
focus: minimal
"""


@pytest.fixture
def tmp_projects(tmp_path: Path) -> Path:
    d = tmp_path / "knowledge" / "projects"
    d.mkdir(parents=True)
    (d / "testproj.yaml").write_text(_FULL_YAML)
    (d / "tiny.yaml").write_text(_MINIMAL_YAML)
    return d


@pytest.fixture
def tmp_home(tmp_path: Path) -> Path:
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _run(
    *args: str,
    home: Path | None = None,
) -> subprocess.CompletedProcess:
    cmd = ["python3", str(_SCRIPT), *args]
    if home is not None:
        cmd = [*cmd, "--home", str(home)]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


# ---------- field mapping ----------

def test_build_frontmatter_1to1_fields(tmp_path):
    source = yaml.safe_load(_FULL_YAML)
    fm = mp.build_frontmatter(source, name="testproj", client="personal", home=tmp_path)
    assert fm["project"] == "testproj"
    assert fm["host"] == "jns-mac"
    assert fm["status"] == "active"
    assert fm["focus"] == "A real focus"
    assert fm["next_steps"] == ["first", "second"]
    assert fm["blockers"] == []
    assert fm["open_questions"] == ["what about edge cases?"]


def test_build_frontmatter_renames_updated_at(tmp_path):
    source = yaml.safe_load(_FULL_YAML)
    fm = mp.build_frontmatter(source, name="testproj", client="personal", home=tmp_path)
    assert fm["status_updated"] == "2026-05-08"
    assert "updated_at" not in fm


def test_build_frontmatter_drops_legacy_fields(tmp_path):
    source = yaml.safe_load(_FULL_YAML)
    fm = mp.build_frontmatter(source, name="testproj", client="personal", home=tmp_path)
    for dropped in ("schema_version", "specs", "dependencies", "updated_by"):
        assert dropped not in fm


def test_build_frontmatter_destination_only_fields(tmp_path):
    source = yaml.safe_load(_MINIMAL_YAML)
    fm = mp.build_frontmatter(source, name="tiny", client="vital", home=tmp_path)
    assert fm["client"] == "vital"
    assert fm["kind"] == "personal"  # default
    assert fm["stack"] == []
    assert fm["repo_path"].endswith("projects/tiny")
    assert fm["repo_remote"] == ""  # no repo dir


def test_kind_heuristic_for_agents(tmp_path):
    fm = mp.build_frontmatter({"project": "agents"}, name="agents", client="personal", home=tmp_path)
    assert fm["kind"] == "engineering-tool"
    assert fm["repo_path"].endswith("/agents")


def test_repo_remote_detected_from_real_git_dir(tmp_path):
    # Simulate $HOME/agents being a git repo with a remote
    repo = tmp_path / "agents"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "git@example.com:test.git"],
                   check=True)
    fm = mp.build_frontmatter({"project": "agents"}, name="agents", client="personal", home=tmp_path)
    assert fm["repo_remote"] == "git@example.com:test.git"


def test_list_fields_default_to_empty_when_source_is_null(tmp_path):
    source = {"project": "x", "next_steps": None, "blockers": None}
    fm = mp.build_frontmatter(source, name="x", client="personal", home=tmp_path)
    assert fm["next_steps"] == []
    assert fm["blockers"] == []
    assert fm["open_questions"] == []  # not in source — default
    assert fm["stack"] == []


# ---------- body rendering ----------

def test_render_body_contains_required_sections():
    body = mp.render_body("agents", Path("/x/agents"), "git@example.com:foo.git")
    assert "## Purpose" in body
    assert "## Stack" in body
    assert "## Repository" in body
    assert "## Status (live)" in body
    assert "## Activity" in body
    assert "## Decisions linked" in body
    assert "## Git on this device" in body
    assert "## Notes / journal" in body
    # Dataview blocks well-formed (count fence pairs)
    assert body.count("```dataview") >= 4
    assert body.count("```") % 2 == 0


def test_render_body_includes_repo_remote():
    body = mp.render_body("p", Path("/x/projects/p"), "git@example.com:repo.git")
    assert "git@example.com:repo.git" in body


def test_render_body_dataview_uses_this_host_substitution():
    """Git block should query for host = this.host (frontmatter), not a hardcoded value."""
    body = mp.render_body("agents", Path("/x/agents"), "")
    assert "host = this.host" in body


# ---------- migrate_project ----------

def test_migrate_project_writes_md_file(tmp_projects, tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    action, dest = mp.migrate_project(
        tmp_projects / "testproj.yaml", vault,
        client="personal", dry_run=False, force=False, home=tmp_path,
    )
    assert action == "wrote"
    assert dest.exists()
    assert dest.name == "testproj.md"


def test_migrate_project_frontmatter_field_order(tmp_projects, tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    _, dest = mp.migrate_project(
        tmp_projects / "testproj.yaml", vault,
        client="personal", dry_run=False, force=False, home=tmp_path,
    )
    text = dest.read_text()
    idx_project = text.index("project:")
    idx_host = text.index("host:")
    idx_client = text.index("client:")
    idx_kind = text.index("kind:")
    idx_status = text.index("status:")
    idx_focus = text.index("focus:")
    assert idx_project < idx_host < idx_client < idx_kind < idx_status < idx_focus


def test_migrate_project_roundtrip(tmp_projects, tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    _, dest = mp.migrate_project(
        tmp_projects / "testproj.yaml", vault,
        client="personal", dry_run=False, force=False, home=tmp_path,
    )
    fm, body = obsidian_md.load(dest)
    # Renamed field
    assert fm["status_updated"] == "2026-05-08"
    # 1:1
    assert fm["host"] == "jns-mac"
    assert fm["next_steps"] == ["first", "second"]
    # Destination-only
    assert fm["client"] == "personal"
    assert "kind" in fm
    # Dropped
    assert "schema_version" not in fm
    assert "specs" not in fm
    # Body well-formed
    assert "# testproj" in body
    assert "## Purpose" in body


def test_migrate_project_dry_run_writes_nothing(tmp_projects, tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    action, dest = mp.migrate_project(
        tmp_projects / "testproj.yaml", vault,
        client="personal", dry_run=True, force=False, home=tmp_path,
    )
    assert action == "dry-run-would-write"
    assert not dest.exists()


def test_migrate_project_refuses_existing_without_force(tmp_projects, tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    dest = vault / "Projects" / "testproj.md"
    dest.write_text("existing content")
    action, _ = mp.migrate_project(
        tmp_projects / "testproj.yaml", vault,
        client="personal", dry_run=False, force=False, home=tmp_path,
    )
    assert action == "skipped-exists"
    assert dest.read_text() == "existing content"


def test_migrate_project_force_overwrites(tmp_projects, tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    dest = vault / "Projects" / "testproj.md"
    dest.write_text("existing")
    action, _ = mp.migrate_project(
        tmp_projects / "testproj.yaml", vault,
        client="personal", dry_run=False, force=True, home=tmp_path,
    )
    assert action == "wrote"
    assert "project: testproj" in dest.read_text()


def test_migrate_project_malformed_yaml_errors(tmp_path):
    src = tmp_path / "bad.yaml"
    src.write_text("project: x\n  bad: indent: : :\n")
    with pytest.raises(mp.MigrationError, match="bad.yaml"):
        mp.migrate_project(
            src, tmp_path / "vault",
            client="personal", dry_run=False, force=False, home=tmp_path,
        )


def test_migrate_project_atomic_no_tmp_leftovers(tmp_projects, tmp_path):
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    mp.migrate_project(
        tmp_projects / "testproj.yaml", vault,
        client="personal", dry_run=False, force=False, home=tmp_path,
    )
    assert not list((vault / "Projects").glob("*.tmp*"))


# ---------- subscription cutover ----------

def test_subscription_legacy_migrated(tmp_path):
    subs = tmp_path / "subs.json"
    subs.write_text(json.dumps({"subscribed": ["agents", "buddy"]}))
    status, _ = mp.migrate_subscription_file(subs, "JNS-Personal-Vault", dry_run=False)
    assert status == "migrated"
    new = json.loads(subs.read_text())
    assert new == {
        "JNS-Personal-Vault": {
            "subscribed": ["agents", "buddy"],
            "ssh_writes": [],
        }
    }


def test_subscription_already_vault_keyed_no_op(tmp_path):
    subs = tmp_path / "subs.json"
    initial = {"V1": {"subscribed": ["a"], "ssh_writes": ["h"]}}
    subs.write_text(json.dumps(initial))
    status, _ = mp.migrate_subscription_file(subs, "JNS-Personal-Vault", dry_run=False)
    assert status == "ok"
    assert json.loads(subs.read_text()) == initial


def test_subscription_missing_no_op(tmp_path):
    subs = tmp_path / "missing.json"
    status, _ = mp.migrate_subscription_file(subs, "JNS-Personal-Vault", dry_run=False)
    assert status == "no-op"
    assert not subs.exists()


def test_subscription_creates_backup(tmp_path):
    subs = tmp_path / "subs.json"
    original = json.dumps({"subscribed": ["agents"]})
    subs.write_text(original)
    mp.migrate_subscription_file(subs, "JNS-Personal-Vault", dry_run=False)
    backup = tmp_path / "dashboard-subscriptions-pre-pathb.json"
    assert backup.exists()
    assert backup.read_text() == original


def test_subscription_backup_not_overwritten_on_second_run(tmp_path):
    subs = tmp_path / "subs.json"
    subs.write_text(json.dumps({"subscribed": ["agents"]}))
    mp.migrate_subscription_file(subs, "JNS-Personal-Vault", dry_run=False)
    backup = tmp_path / "dashboard-subscriptions-pre-pathb.json"
    backup_content_first = backup.read_text()
    # Simulate user re-running; subs is already vault-keyed now so it's a no-op
    mp.migrate_subscription_file(subs, "JNS-Personal-Vault", dry_run=False)
    assert backup.read_text() == backup_content_first


def test_subscription_dry_run_writes_nothing(tmp_path):
    subs = tmp_path / "subs.json"
    original = json.dumps({"subscribed": ["agents"]})
    subs.write_text(original)
    status, _ = mp.migrate_subscription_file(subs, "JNS-Personal-Vault", dry_run=True)
    assert status == "dry-run-would-migrate"
    assert subs.read_text() == original


def test_subscription_malformed_json_errors(tmp_path):
    subs = tmp_path / "subs.json"
    subs.write_text("not json {")
    with pytest.raises(mp.MigrationError, match="malformed JSON"):
        mp.migrate_subscription_file(subs, "V", dry_run=False)


# ---------- end-to-end via main() ----------

def test_main_dry_run_against_real_fixtures(tmp_projects, tmp_path, tmp_home):
    r = _run(
        "--vault", "JNS-Personal-Vault",
        "--projects-dir", str(tmp_projects),
        "--vaults-base", str(tmp_path / "vaults"),
        "--subscriptions", str(tmp_home / ".claude" / "missing.json"),
        "--noninteractive",
        "--dry-run",
        home=tmp_home,
    )
    assert r.returncode == 0, r.stderr
    assert "dry-run-would-write" in r.stdout
    # Nothing written
    assert not (tmp_path / "vaults" / "JNS-Personal-Vault" / "Projects" / "testproj.md").exists()


def test_main_full_run_writes_both_files_and_migrates_subs(tmp_projects, tmp_path, tmp_home):
    subs = tmp_home / ".claude" / "dashboard-subscriptions.json"
    subs.write_text(json.dumps({"subscribed": ["testproj"]}))

    r = _run(
        "--vault", "JNS-Personal-Vault",
        "--projects-dir", str(tmp_projects),
        "--vaults-base", str(tmp_path / "vaults"),
        "--subscriptions", str(subs),
        "--noninteractive",
        home=tmp_home,
    )
    assert r.returncode == 0, r.stderr
    # Both MDs written
    vault = tmp_path / "vaults" / "JNS-Personal-Vault" / "Projects"
    assert (vault / "testproj.md").exists()
    assert (vault / "tiny.md").exists()
    # Subscriptions migrated
    after = json.loads(subs.read_text())
    assert "JNS-Personal-Vault" in after
    assert after["JNS-Personal-Vault"]["subscribed"] == ["testproj"]


def test_main_idempotent_second_run_makes_no_changes(tmp_projects, tmp_path, tmp_home):
    args = [
        "--vault", "JNS-Personal-Vault",
        "--projects-dir", str(tmp_projects),
        "--vaults-base", str(tmp_path / "vaults"),
        "--subscriptions", str(tmp_home / ".claude" / "subs.json"),
        "--noninteractive",
    ]
    first = _run(*args, home=tmp_home)
    assert first.returncode == 0
    vault_dir = tmp_path / "vaults" / "JNS-Personal-Vault" / "Projects"
    md_path = vault_dir / "testproj.md"
    first_content = md_path.read_text()
    first_mtime = md_path.stat().st_mtime

    second = _run(*args, home=tmp_home)
    assert second.returncode == 0
    # Second run skipped (existing files preserved)
    assert "skipped-exists" in second.stdout
    assert md_path.read_text() == first_content
    assert md_path.stat().st_mtime == first_mtime


def test_main_errors_on_missing_projects_dir(tmp_path, tmp_home):
    r = _run(
        "--vault", "V",
        "--projects-dir", str(tmp_path / "does-not-exist"),
        "--vaults-base", str(tmp_path / "vaults"),
        "--subscriptions", str(tmp_home / ".claude" / "subs.json"),
        "--noninteractive",
        home=tmp_home,
    )
    assert r.returncode == 2
    assert "source projects dir not found" in r.stderr


def test_main_requires_vault_flag(tmp_path):
    r = _run("--noninteractive", home=tmp_path)
    assert r.returncode != 0
    assert "vault" in (r.stderr + r.stdout).lower()
