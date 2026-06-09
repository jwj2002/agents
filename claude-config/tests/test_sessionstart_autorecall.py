"""Tests for SessionStart project-memory auto-recall (issue #365)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import sessionstart_restore_state as H  # noqa: E402

TODAY = "2026-06-09"


def _fact(d, name, *, ftype="project", expires=None, body="the why lives here",
          mtime=None):
    fm = f"---\nname: {name}\ntype: {ftype}\n"
    if expires:
        fm += f"expires: {expires}\n"
    fm += "---\n\n"
    p = d / f"{name}.md"
    p.write_text(fm + body, encoding="utf-8")
    if mtime:
        import os
        os.utime(p, (mtime, mtime))
    return p


def _memdir(tmp_path):
    d = tmp_path / ".claude" / "projects" / "-Users-x-proj" / "memory"
    d.mkdir(parents=True)
    return d


def test_injects_fact_bodies(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    _fact(d, "lesson-one", ftype="feedback", body="Always do X because Y.")
    out = H.render_project_memory(d, today=TODAY)
    assert "auto-recalled" in out
    assert "Always do X because Y." in out
    assert "lesson-one" in out


def test_empty_dir_renders_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    assert H.render_project_memory(d, today=TODAY) == ""


def test_expired_facts_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    _fact(d, "dead-handoff", expires="2026-01-01", body="stale resume doc")
    assert H.render_project_memory(d, today=TODAY) == ""


def test_unexpired_expires_included(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    _fact(d, "live-plan", expires="2027-01-01", body="still relevant plan")
    assert "still relevant plan" in H.render_project_memory(d, today=TODAY)


def test_memory_index_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    (d / "MEMORY.md").write_text("# index\n- [a](a.md)\n")
    assert H.render_project_memory(d, today=TODAY) == ""


def test_feedback_outranks_project(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    _fact(d, "zz-feedback", ftype="feedback", body="F" * 100, mtime=1000)
    _fact(d, "aa-project", ftype="project", body="P" * 100, mtime=2000)
    out = H.render_project_memory(d, today=TODAY)
    assert out.index("zz-feedback") < out.index("aa-project")


def test_budget_caps_injection_and_lists_leftovers(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    for i in range(12):
        _fact(d, f"fact-{i:02d}", ftype="feedback", body="B" * 1100, mtime=1000 + i)
    out = H.render_project_memory(d, today=TODAY)
    assert "Not injected" in out
    assert "memory recall" in out
    # budget 6000 chars with ~1140-char facts → at most 5 injected
    assert out.count("(feedback):") <= 5


def test_long_body_truncated_with_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    _fact(d, "big-fact", ftype="feedback", body="X" * 5000)
    out = H.render_project_memory(d, today=TODAY)
    assert "truncated" in out
    assert "big-fact.md" in out


def test_autoinject_metrics_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    _fact(d, "lesson", ftype="user", body="who jason is")
    H.render_project_memory(d, today=TODAY)
    log = tmp_path / ".claude" / "memory-autoinject.jsonl"
    assert log.exists()
    import json
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["facts_injected"] == 1
    assert rec["project"] == "-Users-x-proj"


def test_corrupt_fact_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = _memdir(tmp_path)
    (d / "bad.md").write_bytes(b"\xff\xfe broken")
    _fact(d, "good", ftype="feedback", body="fine")
    out = H.render_project_memory(d, today=TODAY)
    assert "fine" in out
