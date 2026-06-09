"""Tests for the executable behavioral evals (issue #361)."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evals import (  # noqa: E402
    e01_enum_value,
    e04_model_migration,
    e13_fk_index,
    e14_docker_user,
    e15_secrets,
    run_evals,
)
from evals.common import ChangeSet, changeset_from_git  # noqa: E402


def _cs(tmp_path, added):
    return ChangeSet(repo=tmp_path, added=added)


# ---------- E01 ENUM_VALUE ----------

def _backend_enum(tmp_path):
    mod = tmp_path / "backend" / "app" / "enums.py"
    mod.parent.mkdir(parents=True)
    mod.write_text(
        "from enum import Enum\n\n"
        "class Role(str, Enum):\n"
        '    CO_OWNER = "CO-OWNER"\n'
        '    OWNER = "OWNER"\n',
        encoding="utf-8",
    )


def test_e01_flags_enum_name_literal(tmp_path):
    _backend_enum(tmp_path)
    cs = _cs(tmp_path, {"frontend/src/Form.jsx": [(10, 'if (role === "CO_OWNER") {')]})
    findings = e01_enum_value.run(cs)
    assert len(findings) == 1
    assert "CO-OWNER" in findings[0].message


def test_e01_value_literal_is_clean(tmp_path):
    _backend_enum(tmp_path)
    cs = _cs(tmp_path, {"frontend/src/Form.jsx": [(10, 'if (role === "CO-OWNER") {')]})
    assert e01_enum_value.run(cs) == []


def test_e01_name_equals_value_not_flagged(tmp_path):
    _backend_enum(tmp_path)  # OWNER == "OWNER" — never a mismatch risk
    cs = _cs(tmp_path, {"frontend/src/Form.jsx": [(10, 'if (role === "OWNER") {')]})
    assert e01_enum_value.run(cs) == []


def test_e01_identifier_use_not_flagged(tmp_path):
    _backend_enum(tmp_path)
    cs = _cs(tmp_path, {"frontend/src/Form.jsx": [(10, "const CO_OWNER = roles.coOwner;")]})
    assert e01_enum_value.run(cs) == []


def test_e01_backend_only_diff_skips(tmp_path):
    _backend_enum(tmp_path)
    cs = _cs(tmp_path, {"backend/app/service.py": [(5, 'x = "CO_OWNER"')]})
    assert e01_enum_value.run(cs) == []


def test_e01_allowlist(tmp_path):
    _backend_enum(tmp_path)
    cs = _cs(tmp_path, {"frontend/src/Form.jsx": [
        (10, 'const key = "CO_OWNER";  // eval-ok: E01 — i18n key, not the enum')]})
    assert e01_enum_value.run(cs) == []


# ---------- E04 MODEL_WITHOUT_MIGRATION ----------

def test_e04_schema_change_without_migration(tmp_path):
    cs = _cs(tmp_path, {"backend/app/models/job.py": [
        (12, "    category = Column(String, nullable=True)")]})
    findings = e04_model_migration.run(cs)
    assert len(findings) == 1
    assert "no alembic/migrations file" in findings[0].message


def test_e04_with_migration_is_clean(tmp_path):
    cs = _cs(tmp_path, {
        "backend/app/models/job.py": [(12, "    category = Column(String)")],
        "backend/alembic/versions/abc123_add_category.py": [(1, "def upgrade():")],
    })
    assert e04_model_migration.run(cs) == []


def test_e04_non_schema_edit_in_models_file_is_clean(tmp_path):
    cs = _cs(tmp_path, {"backend/app/models/job.py": [
        (40, "    def display_name(self) -> str:")]})
    assert e04_model_migration.run(cs) == []


def test_e04_non_model_file_is_clean(tmp_path):
    cs = _cs(tmp_path, {"backend/app/services/job.py": [
        (12, "    q = Column(String)  # query builder helper")]})
    assert e04_model_migration.run(cs) == []


# ---------- E13 MISSING_FK_INDEX ----------

def test_e13_fk_without_index(tmp_path):
    cs = _cs(tmp_path, {"backend/app/models/job.py": [
        (8, '    account_id = Column(Integer, ForeignKey("accounts.id"))')]})
    findings = e13_fk_index.run(cs)
    assert len(findings) == 1


def test_e13_fk_with_index_clean(tmp_path):
    cs = _cs(tmp_path, {"backend/app/models/job.py": [
        (8, '    account_id = Column(Integer, ForeignKey("accounts.id"), index=True)')]})
    assert e13_fk_index.run(cs) == []


def test_e13_multiline_definition(tmp_path):
    cs = _cs(tmp_path, {"backend/app/models/job.py": [
        (8, "    account_id = Column("),
        (9, "        Integer,"),
        (10, '        ForeignKey("accounts.id"),'),
        (11, "    )"),
    ]})
    assert len(e13_fk_index.run(cs)) == 1


def test_e13_multiline_with_index_clean(tmp_path):
    cs = _cs(tmp_path, {"backend/app/models/job.py": [
        (8, "    account_id = Column("),
        (9, '        Integer, ForeignKey("accounts.id"),'),
        (10, "        index=True,"),
        (11, "    )"),
    ]})
    assert e13_fk_index.run(cs) == []


def test_e13_primary_key_fk_clean(tmp_path):
    cs = _cs(tmp_path, {"backend/app/models/job.py": [
        (8, '    id = Column(Integer, ForeignKey("base.id"), primary_key=True)')]})
    assert e13_fk_index.run(cs) == []


# ---------- E14 DOCKER_ROOT_USER ----------

def test_e14_no_user_directive(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\nCOPY . /app\n")
    cs = _cs(tmp_path, {"Dockerfile": [(2, "COPY . /app")]})
    findings = e14_docker_user.run(cs)
    assert len(findings) == 1
    assert "root" in findings[0].message


def test_e14_with_user_clean(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\nUSER app\nCOPY . /app\n")
    cs = _cs(tmp_path, {"Dockerfile": [(3, "COPY . /app")]})
    assert e14_docker_user.run(cs) == []


def test_e14_final_user_root_flagged(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM x\nUSER app\nUSER root\n")
    cs = _cs(tmp_path, {"Dockerfile": [(3, "USER root")]})
    assert len(e14_docker_user.run(cs)) == 1


def test_e14_non_docker_file_ignored(tmp_path):
    cs = _cs(tmp_path, {"src/main.py": [(1, "print('hi')")]})
    assert e14_docker_user.run(cs) == []


# ---------- E15 SECRETS ----------

def test_e15_aws_key(tmp_path):
    cs = _cs(tmp_path, {"config.py": [(3, 'KEY = "AKIAIOSFODNN7EXAMPLE"')]})
    assert len(e15_secrets.run(cs)) == 1


def test_e15_password_literal(tmp_path):
    cs = _cs(tmp_path, {"db.py": [(3, 'password = "hunter2hunter2"')]})
    assert len(e15_secrets.run(cs)) == 1


def test_e15_env_lookup_clean(tmp_path):
    cs = _cs(tmp_path, {"db.py": [(3, 'password = os.environ["DB_PASSWORD"]')]})
    assert e15_secrets.run(cs) == []


def test_e15_placeholder_clean(tmp_path):
    cs = _cs(tmp_path, {"db.py": [(3, 'password = "your-password-here"')]})
    assert e15_secrets.run(cs) == []


def test_e15_allowlist(tmp_path):
    cs = _cs(tmp_path, {"tests/fixtures.py": [
        (3, 'password = "fixturepass1234"  # eval-ok: E15 — inert fixture')]})
    assert e15_secrets.run(cs) == []


def test_e15_markdown_skipped(tmp_path):
    cs = _cs(tmp_path, {"docs/setup.md": [(3, 'password = "realLooking12345"')]})
    assert e15_secrets.run(cs) == []


# ---------- runner + git integration ----------

def test_applicable_mapping(tmp_path):
    cs = _cs(tmp_path, {
        "frontend/src/App.tsx": [(1, "x")],
        "backend/app/models/job.py": [(1, "x")],
        "Dockerfile": [(1, "x")],
    })
    assert run_evals.applicable(cs) == ["E01", "E04", "E13", "E14", "E15"]


def test_applicable_defaults_to_e15(tmp_path):
    cs = _cs(tmp_path, {"README.txt": [(1, "x")]})
    assert run_evals.applicable(cs) == ["E15"]


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_changeset_from_git_integration(tmp_path):
    _git(["init", "-q", "--initial-branch=main"], tmp_path)
    _git(["config", "user.email", "t@e.st"], tmp_path)
    _git(["config", "user.name", "T"], tmp_path)
    f = tmp_path / "a.py"
    f.write_text("line1\nline2\n")
    _git(["add", "."], tmp_path)
    _git(["commit", "-qm", "base"], tmp_path)
    f.write_text("line1\nNEW = 1\nline2\nTAIL = 2\n")
    _git(["add", "."], tmp_path)
    _git(["commit", "-qm", "change"], tmp_path)

    cs = changeset_from_git(tmp_path, "HEAD~1...HEAD")
    assert cs.paths == ["a.py"]
    assert (2, "NEW = 1") in cs.added_lines("a.py")
    assert (4, "TAIL = 2") in cs.added_lines("a.py")


def test_runner_end_to_end_finding(tmp_path):
    _git(["init", "-q", "--initial-branch=main"], tmp_path)
    _git(["config", "user.email", "t@e.st"], tmp_path)
    _git(["config", "user.name", "T"], tmp_path)
    (tmp_path / "ok.py").write_text("x = 1\n")
    _git(["add", "."], tmp_path)
    _git(["commit", "-qm", "base"], tmp_path)
    (tmp_path / "cfg.py").write_text('api_key = "abcd1234efgh5678"\n')
    _git(["add", "."], tmp_path)
    _git(["commit", "-qm", "leak"], tmp_path)

    rc = run_evals.main(["--repo", str(tmp_path), "--diff-range", "HEAD~1...HEAD"])
    assert rc == 1

    rc_clean = run_evals.main(["--repo", str(tmp_path), "--diff-range", "HEAD...HEAD"])
    assert rc_clean == 0
