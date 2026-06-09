"""Tests for bin/memory core logic (issue #369): recall ranking, TTL expiry,
stale-perishable heuristic, archive selection helpers.

bin/memory has no .py extension; load it via SourceFileLoader.
"""

import datetime
import importlib.util
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent.parent / "bin" / "memory"
_loader = SourceFileLoader("bin_memory", str(_BIN))
_spec = importlib.util.spec_from_loader("bin_memory", _loader)
M = importlib.util.module_from_spec(_spec)
_loader.exec_module(M)

TODAY = datetime.date(2026, 6, 9)


def _fact(memdir, name, *, ftype="project", expires="", desc="", body="body text"):
    memdir.mkdir(parents=True, exist_ok=True)
    fm = f"---\nname: {name}\ndescription: {desc}\ntype: {ftype}\n"
    if expires:
        fm += f"expires: {expires}\n"
    fm += "---\n\n"
    p = memdir / f"{name}.md"
    p.write_text(fm + body, encoding="utf-8")
    return p


def _store(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    monkeypatch.setattr(M, "PROJECTS_ROOT", root)
    return root


# ---------- frontmatter parsing ----------

def test_split_frontmatter_flat_and_nested():
    flat, body = M._split_frontmatter("---\nname: a\ntype: feedback\n---\nB")
    assert flat["type"] == "feedback" and body == "B"
    nested, _ = M._split_frontmatter(
        "---\nname: a\nmetadata:\n  type: user\n---\nB")
    assert nested["type"] == "user"


def test_split_frontmatter_absent():
    meta, body = M._split_frontmatter("no frontmatter")
    assert meta["name"] == "" and body == "no frontmatter"


# ---------- TTL ----------

def test_is_expired():
    assert M._is_expired({"expires": "2026-01-01"}, TODAY)
    assert not M._is_expired({"expires": "2027-01-01"}, TODAY)
    assert not M._is_expired({"expires": ""}, TODAY)
    assert not M._is_expired({"expires": "not-a-date"}, TODAY)


def test_stale_perishable_heuristic(tmp_path):
    now = time.time()
    old = now - 100 * 86400
    p = tmp_path / "resume_session_plan.md"
    p.write_text("x")
    # type=project + perishable name + old → candidate
    assert M._is_stale_perishable(p, {"type": "project"}, old, now, 90)
    # durable types never stale
    assert not M._is_stale_perishable(p, {"type": "feedback"}, old, now, 90)
    # non-perishable name → not a candidate
    q = tmp_path / "architecture_decision.md"
    q.write_text("x")
    assert not M._is_stale_perishable(q, {"type": "project"}, old, now, 90)
    # recent → not a candidate
    assert not M._is_stale_perishable(p, {"type": "project"}, now - 86400, now, 90)


def test_ttl_reason_strings(tmp_path):
    p = tmp_path / "resume_notes.md"
    p.write_text("x")
    now = time.time()
    assert "expired" in M._ttl_reason(p, {"expires": "2026-01-01", "type": ""}, now, TODAY, now, 90)
    assert "stale perishable" in M._ttl_reason(
        p, {"expires": "", "type": "project"}, now - 100 * 86400, TODAY, now, 90)
    assert M._ttl_reason(p, {"expires": "", "type": "feedback"}, now, TODAY, now, 90) is None


# ---------- recall ranking ----------

class _Args:
    def __init__(self, query, project=None, limit=5, compact=True, all=False):
        self.query = query
        self.project = project
        self.limit = limit
        self.compact = compact
        self.all = all


def test_recall_title_match_outranks_body_match(tmp_path, monkeypatch, capsys):
    root = _store(tmp_path, monkeypatch)
    _fact(root / "-p-alpha" / "memory", "telemetry-design",
          desc="telemetry hub design", body="unrelated")
    _fact(root / "-p-beta" / "memory", "other-fact",
          desc="", body="telemetry mentioned once")
    rc = M.cmd_recall(_Args("telemetry"))
    assert rc == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("- ")]
    assert "telemetry-design" in lines[0]
    assert "other-fact" in lines[1]


def test_recall_hides_expired_by_default(tmp_path, monkeypatch, capsys):
    root = _store(tmp_path, monkeypatch)
    _fact(root / "-p-a" / "memory", "dead-fact", expires="2026-01-01",
          body="needle content")
    rc = M.cmd_recall(_Args("needle"))
    assert rc == 0
    assert "No facts match" in capsys.readouterr().out

    rc = M.cmd_recall(_Args("needle", all=True))
    assert "dead-fact" in capsys.readouterr().out and rc == 0


def test_recall_project_filter(tmp_path, monkeypatch, capsys):
    root = _store(tmp_path, monkeypatch)
    _fact(root / "-Users-jasonjob-projects-alpha" / "memory", "fact-a", body="needle")
    _fact(root / "-Users-jasonjob-projects-beta" / "memory", "fact-b", body="needle")
    M.cmd_recall(_Args("needle", project="alpha"))
    out = capsys.readouterr().out
    assert "fact-a" in out and "fact-b" not in out


def test_recall_skips_archive_subdir(tmp_path, monkeypatch, capsys):
    root = _store(tmp_path, monkeypatch)
    mem = root / "-p-a" / "memory"
    _fact(mem, "live-fact", body="needle")
    _fact(mem / "archive", "buried-fact", body="needle")
    M.cmd_recall(_Args("needle"))
    out = capsys.readouterr().out
    assert "live-fact" in out and "buried-fact" not in out


def test_recall_limit(tmp_path, monkeypatch, capsys):
    root = _store(tmp_path, monkeypatch)
    for i in range(8):
        _fact(root / f"-p-{i}" / "memory", f"fact-{i}", body="needle")
    M.cmd_recall(_Args("needle", limit=3))
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("- ")]
    assert len(lines) == 3


def test_recall_empty_query_errors():
    assert M.cmd_recall(_Args("   ")) == 2


# ---------- index hygiene ----------

def test_deindex_removes_pointer(tmp_path):
    idx = tmp_path / "MEMORY.md"
    idx.write_text("# Memory\n- [A](a.md) — hook\n- [B](b.md) — hook\n")
    M._deindex(idx, "a.md")
    text = idx.read_text()
    assert "a.md" not in text and "b.md" in text
