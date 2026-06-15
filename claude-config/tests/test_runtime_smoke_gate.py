"""Tests for the runtime-smoke obligation helper (issue #463, AC5 of #458)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import runtime_smoke_gate as R  # noqa: E402
from evals.common import ChangeSet  # noqa: E402


def _cs(tmp_path, added):
    return ChangeSet(repo=tmp_path, added=added)


# ---------- obligation mapping matrix ----------

def test_backend_route_with_fastapi_content(tmp_path):
    cs = _cs(tmp_path, {"app/routers/jobs.py": [
        (1, "from fastapi import APIRouter"),
        (5, "@router.get('/x')"),
    ]})
    assert R.obligations(cs) == {"backend_http"}


def test_backend_path_without_fastapi_content_no_false_positive(tmp_path):
    # Load-bearing: backend-shaped paths with NO FastAPI content must NOT fire.
    cs = _cs(tmp_path, {
        "claude-config/scripts/some_tool.py": [(1, "import argparse")],
        "app/util.py": [(1, "x = 1")],
    })
    assert R.obligations(cs) == set()


def test_bin_path_is_cli(tmp_path):
    cs = _cs(tmp_path, {"bin/foo": [(1, "#!/usr/bin/env python")]})
    assert R.obligations(cs) == {"cli"}


def test_services_path_is_worker(tmp_path):
    cs = _cs(tmp_path, {"services/x.py": [(1, "def run(): ...")]})
    assert R.obligations(cs) == {"worker"}


def test_pages_tsx_is_frontend(tmp_path):
    cs = _cs(tmp_path, {"frontend/pages/Home.tsx": [(1, "export default Home")]})
    assert R.obligations(cs) == {"frontend"}


def test_docs_only_is_na(tmp_path):
    cs = _cs(tmp_path, {"README.md": [(1, "# hi")]})
    assert R.obligations(cs) == set()


def test_mixed_change_is_union(tmp_path):
    cs = _cs(tmp_path, {
        "app/routers/jobs.py": [(1, "from fastapi import APIRouter"),
                                (2, "@router.post('/y')")],
        "bin/cli.py": [(1, "import argparse")],
    })
    assert R.obligations(cs) == {"backend_http", "cli"}


def test_backend_http_via_file_text_fallback(tmp_path):
    # No content in added lines, but the working-tree file has FastAPI() —
    # exercise the file_text fallback path.
    mod = tmp_path / "app" / "main.py"
    mod.parent.mkdir(parents=True)
    mod.write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    cs = _cs(tmp_path, {"app/main.py": [(3, "# comment-only added line")]})
    assert "backend_http" in R.obligations(cs)


def test_worker_via_lifespan_content(tmp_path):
    cs = _cs(tmp_path, {"core/boot.py": [(1, "async def lifespan(app): ...")]})
    assert R.obligations(cs) == {"worker"}


def test_test_files_excluded(tmp_path):
    # A test file whose fixtures contain route/worker example strings is NOT a
    # runnable surface — it must contribute no obligations (the dogfood case).
    cs = _cs(tmp_path, {
        "tests/test_thing.py": [
            (1, "cs = {'app/routers/x.py': '@router.get()'}"),
            (2, "async def lifespan(app): ..."),
        ],
        "app/__main__.py": [(1, "# in a test tree? no — but bin pattern still excluded under tests/")],
    })
    # tests/ path excluded entirely; only the non-test app/__main__.py is a CLI.
    assert R.obligations(cs) == {"cli"}


def test_comment_only_worker_marker_ignored(tmp_path):
    # A comment mentioning the markers must not fire the worker content rule.
    cs = _cs(tmp_path, {"core/util.py": [
        (1, "# this module talks to the ServiceContainer( and def lifespan"),
        (2, "x = 1"),
    ]})
    assert R.obligations(cs) == set()


# ---------- broadened BACKEND_HTTP detection (codex review #463) ----------

def test_backend_apirouter_construction(tmp_path):
    cs = _cs(tmp_path, {"app/routers/x.py": [
        (1, "api_router = APIRouter()"),
        (2, "@api_router.get('/x')"),
    ]})
    assert R.obligations(cs) == {"backend_http"}


def test_backend_add_api_route(tmp_path):
    cs = _cs(tmp_path, {"app/main.py": [
        (1, "app.add_api_route('/x', handler)"),
    ]})
    assert R.obligations(cs) == {"backend_http"}


def test_backend_router_suffixed_identifier_decorator(tmp_path):
    # A non-app/router identifier ending in `router` must still fire.
    cs = _cs(tmp_path, {"app/routers/v1.py": [
        (1, "@v1_router.post('/y')"),
    ]})
    assert R.obligations(cs) == {"backend_http"}


def test_backend_path_no_fastapi_still_empty(tmp_path):
    # No-false-positive guard still holds with the broadened content regex.
    cs = _cs(tmp_path, {"app/util.py": [(1, "x = 1"), (2, "def helper(): ...")]})
    assert R.obligations(cs) == set()


# ---------- broadened CLI detection (codex review #463) ----------

def test_pyproject_console_scripts_is_cli(tmp_path):
    cs = _cs(tmp_path, {"pyproject.toml": [
        (10, "[project.scripts]"),
        (11, "mytool = 'pkg.cli:main'"),
    ]})
    assert R.obligations(cs) == {"cli"}


def test_click_command_is_cli(tmp_path):
    cs = _cs(tmp_path, {"tools/cmd.py": [
        (1, "@click.command()"),
        (2, "def run(): ..."),
    ]})
    assert R.obligations(cs) == {"cli"}


# ---------- broadened WORKER detection (codex review #463) ----------

def test_celery_task_decorator_is_worker(tmp_path):
    cs = _cs(tmp_path, {"app/tasks.py": [
        (1, "@celery_app.task"),
        (2, "def crunch(): ..."),
    ]})
    assert R.obligations(cs) == {"worker"}


def test_add_job_scheduler_is_worker(tmp_path):
    cs = _cs(tmp_path, {"jobs/scheduler.py": [
        (1, "scheduler.add_job(crunch, 'interval', seconds=30)"),
    ]})
    assert R.obligations(cs) == {"worker"}


# ---------- path-boundary lock (codex review #463) ----------

def test_test_path_boundary_does_not_swallow_lookalikes(tmp_path):
    # `contests/` and `latest/` must NOT be treated as test paths — they remain
    # eligible for obligations. A genuine `tests/test_*.py` IS excluded.
    cs = _cs(tmp_path, {
        "contests/foo.py": [(1, "@click.command()")],
        "latest/foo.py": [(1, "@click.group()")],
        "tests/test_x.py": [(1, "@click.command()")],
    })
    # Both lookalikes fire CLI; the real test path contributes nothing.
    assert R.obligations(cs) == {"cli"}


# ---------- self-source guard (codex review #463) ----------

def test_self_source_not_self_dogfood_false_positive(tmp_path):
    # The helper's own source contains marker string literals; it must not
    # self-fire on content rules.
    cs = _cs(tmp_path, {"claude-config/scripts/runtime_smoke_gate.py": [
        (1, "_CLI_CONTENT_RE = re.compile(r'@click.command')"),
        (2, "_CONSOLE_SCRIPTS_RE = re.compile(r'console_scripts')"),
        (3, "r'Celery\\\\('"),
    ]})
    assert R.obligations(cs) == set()


# ---------- timeout normalization (codex review #463) ----------

def test_run_smoke_timeout_no_crash(tmp_path):
    # A smoke.sh that sleeps past the timeout maps cleanly to a non-zero exit
    # (no TypeError from bytes stdout/stderr concatenation).
    sh = _write_smoke(tmp_path, "sleep 5")
    code, out = R.run_smoke(sh, tmp_path, timeout=1)
    assert code == 124
    assert "timed out" in out


def test_main_timeout_exit_3(tmp_path, monkeypatch):
    _write_smoke(tmp_path, "sleep 5")
    cs = _cs(tmp_path, {"services/x.py": [(1, "def run(): ...")]})
    monkeypatch.setattr(R, "changeset_from_git", lambda *a, **k: cs)
    assert R.main(["--repo", str(tmp_path), "--timeout", "1"]) == 3


def test_to_text_normalizes(tmp_path):
    assert R._to_text(None) == ""
    assert R._to_text(b"hi") == "hi"
    assert R._to_text("hi") == "hi"


# ---------- smoke.sh discovery ----------

def test_discover_none(tmp_path):
    assert R.discover_smoke_sh(tmp_path) is None


def test_discover_root_smoke(tmp_path):
    sh = tmp_path / "smoke.sh"
    sh.write_text("#!/bin/bash\nexit 0\n")
    assert R.discover_smoke_sh(tmp_path) == sh


def test_discover_scripts_fallback(tmp_path):
    (tmp_path / "scripts").mkdir()
    sh = tmp_path / "scripts" / "smoke.sh"
    sh.write_text("#!/bin/bash\nexit 0\n")
    assert R.discover_smoke_sh(tmp_path) == sh


def test_discover_override(tmp_path):
    custom = tmp_path / "custom_smoke.sh"
    custom.write_text("#!/bin/bash\nexit 0\n")
    assert R.discover_smoke_sh(tmp_path, custom) == custom


# ---------- runner + exit codes ----------

def _write_smoke(tmp_path, body):
    sh = tmp_path / "smoke.sh"
    sh.write_text(f"#!/bin/bash\n{body}\n")
    return sh


def test_run_smoke_pass(tmp_path):
    sh = _write_smoke(tmp_path, "echo ok; exit 0")
    code, out = R.run_smoke(sh, tmp_path, timeout=10)
    assert code == 0
    assert "ok" in out


def test_run_smoke_fail(tmp_path):
    sh = _write_smoke(tmp_path, "echo boom; exit 3")
    code, _ = R.run_smoke(sh, tmp_path, timeout=10)
    assert code != 0


def test_main_smoke_present_and_passes_exit_0(tmp_path, monkeypatch):
    _write_smoke(tmp_path, "exit 0")
    cs = _cs(tmp_path, {"services/x.py": [(1, "def run(): ...")]})
    monkeypatch.setattr(R, "changeset_from_git", lambda *a, **k: cs)
    assert R.main(["--repo", str(tmp_path)]) == 0


def test_main_obligation_no_smoke_exit_1(tmp_path, monkeypatch):
    cs = _cs(tmp_path, {"services/x.py": [(1, "def run(): ...")]})
    monkeypatch.setattr(R, "changeset_from_git", lambda *a, **k: cs)
    assert R.main(["--repo", str(tmp_path)]) == 1


def test_main_smoke_fails_exit_3(tmp_path, monkeypatch):
    _write_smoke(tmp_path, "exit 1")
    cs = _cs(tmp_path, {"services/x.py": [(1, "def run(): ...")]})
    monkeypatch.setattr(R, "changeset_from_git", lambda *a, **k: cs)
    assert R.main(["--repo", str(tmp_path)]) == 3


def test_main_no_obligation_exit_0(tmp_path, monkeypatch):
    cs = _cs(tmp_path, {"README.md": [(1, "# hi")]})
    monkeypatch.setattr(R, "changeset_from_git", lambda *a, **k: cs)
    assert R.main(["--repo", str(tmp_path)]) == 0
