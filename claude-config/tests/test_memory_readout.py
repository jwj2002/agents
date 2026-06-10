"""Tests for `memory readout` subcommand and `memory doctor` injection metrics (#431).

Covers:
  - readout: empty log, autorecall-only, mixed skip events, missing-key tolerance
  - doctor: metrics block appended after summary line, empty log handling
"""

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

# `bin/memory` is extensionless; load it as a module via its file path.
_MEMORY_PATH = Path(__file__).resolve().parents[2] / "bin" / "memory"
_spec = importlib.util.spec_from_loader(
    "memory_cli",
    importlib.machinery.SourceFileLoader("memory_cli", str(_MEMORY_PATH)),
)
memory_cli = importlib.util.module_from_spec(_spec)
sys.modules["memory_cli"] = memory_cli
_spec.loader.exec_module(memory_cli)


# ---------------------------------------------------------------- helpers


def _write_log(path: Path, records: list[dict]) -> None:
    """Write JSONL records to a log file."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _make_minimal_store(tmp_path: Path):
    """Create a minimal memory store with one fact file and a MEMORY.md index."""
    proj_dir = tmp_path / "-test-proj" / "memory"
    proj_dir.mkdir(parents=True)
    # Fact file
    fact = proj_dir / "some-fact.md"
    fact.write_text(
        "---\nname: some-fact\ntype: reference\ndurability: durable\n---\n\nsome body",
        encoding="utf-8",
    )
    # MEMORY.md index
    index = proj_dir / "MEMORY.md"
    index.write_text(
        "# Memory Index\n\n- [some-fact](some-fact.md)\n", encoding="utf-8"
    )
    return proj_dir


# ---------------------------------------------------------------- readout tests


def test_readout_empty_log(tmp_path, capsys):
    """Missing log file → exits 0 and stdout contains 'no data yet'."""
    missing = tmp_path / "nonexistent.jsonl"
    args = type("A", (), {"log": str(missing)})()
    rc = memory_cli.cmd_readout(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "no data yet" in out


def test_readout_autorecall_only(tmp_path, capsys):
    """Three autorecall records with known values → correct aggregation."""
    log = tmp_path / "autoinject.jsonl"
    records = [
        {
            "ts": "t1",
            "project": "p1",
            "facts_injected": 2,
            "facts_total": 5,
            "chars": 100,
        },
        {
            "ts": "t2",
            "project": "p1",
            "facts_injected": 0,
            "facts_total": 5,
            "chars": 80,
        },
        {
            "ts": "t3",
            "project": "p2",
            "facts_injected": 3,
            "facts_total": 3,
            "chars": 200,
        },
    ]
    _write_log(log, records)
    args = type("A", (), {"log": str(log)})()
    rc = memory_cli.cmd_readout(args)
    assert rc == 0
    out = capsys.readouterr().out
    # sessions = 3
    assert "Injection sessions:     3" in out
    # total injected = 2 + 0 + 3 = 5
    assert "5 total" in out
    # total chars = 100 + 80 + 200 = 380
    assert "380 total" in out
    # active recall: 2 of 3 sessions had facts_injected > 0
    assert "2 of 3 sessions" in out
    # write:read deferred
    assert "deferred" in out


def test_readout_with_skip_events(tmp_path, capsys):
    """Mix of autorecall + injection_skip → skip count and top-skipped-facts printed."""
    log = tmp_path / "autoinject.jsonl"
    records = [
        {
            "ts": "t1",
            "project": "p1",
            "facts_injected": 1,
            "facts_total": 2,
            "chars": 50,
        },
        {
            "ts": "t2",
            "event": "injection_skip",
            "project": "p1",
            "fact": "big-fact.md",
            "reason": "too_large",
            "excerpt": "...",
        },
        {
            "ts": "t3",
            "event": "injection_skip",
            "project": "p1",
            "fact": "big-fact.md",
            "reason": "too_large",
            "excerpt": "...",
        },
        {
            "ts": "t4",
            "event": "injection_skip",
            "project": "p1",
            "fact": "other-fact.md",
            "reason": "low_rank",
            "excerpt": "...",
        },
    ]
    _write_log(log, records)
    args = type("A", (), {"log": str(log)})()
    rc = memory_cli.cmd_readout(args)
    assert rc == 0
    out = capsys.readouterr().out
    # 3 injection_skip events
    assert "3  (injection_skip events)" in out
    # top skipped: big-fact.md appears twice
    assert "big-fact.md" in out
    assert "2x" in out


def test_readout_tolerates_missing_keys(tmp_path, capsys):
    """Old-format autorecall records missing optional keys → no KeyError, no crash."""
    log = tmp_path / "autoinject.jsonl"
    records = [
        # Minimal record: just ts and project, no facts_injected / chars
        {"ts": "t1", "project": "p1"},
        # Normal record
        {
            "ts": "t2",
            "project": "p1",
            "facts_injected": 2,
            "facts_total": 2,
            "chars": 100,
        },
    ]
    _write_log(log, records)
    args = type("A", (), {"log": str(log)})()
    rc = memory_cli.cmd_readout(args)
    assert rc == 0
    out = capsys.readouterr().out
    # Should have 2 sessions, facts_injected = 0 + 2 = 2
    assert "Injection sessions:     2" in out
    assert "2 total" in out


def test_readout_malformed_line_tolerance(tmp_path, capsys):
    """Malformed JSON lines in the log are skipped silently; valid lines still process."""
    log = tmp_path / "autoinject.jsonl"
    log.write_text(
        '{"ts":"t1","project":"p1","facts_injected":3,"facts_total":5,"chars":200}\n'
        "NOT VALID JSON\n"
        '{"ts":"t2","project":"p1","facts_injected":1,"facts_total":5,"chars":100}\n',
        encoding="utf-8",
    )
    args = type("A", (), {"log": str(log)})()
    rc = memory_cli.cmd_readout(args)
    assert rc == 0
    out = capsys.readouterr().out
    # 2 valid records processed
    assert "Injection sessions:     2" in out
    # total injected = 3 + 1 = 4
    assert "4 total" in out


# ---------------------------------------------------------------- doctor metrics tests


def test_doctor_metrics_block_appended(tmp_path, capsys, monkeypatch):
    """cmd_doctor prints the metrics block after the 'checked N project(s)' line."""
    _make_minimal_store(tmp_path)
    log = tmp_path / "autoinject.jsonl"
    records = [
        {
            "ts": "t1",
            "project": "p1",
            "facts_injected": 1,
            "facts_total": 1,
            "chars": 100,
        },
    ]
    _write_log(log, records)

    # Redirect PROJECTS_ROOT and AUTOINJECT_LOG to tmp paths
    monkeypatch.setattr(memory_cli, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(memory_cli, "AUTOINJECT_LOG", log)

    args = type(
        "A",
        (),
        {
            "project": None,
            "strict": False,
            "stale_days": memory_cli.STALE_DAYS,
            "log": None,
        },
    )()
    rc = memory_cli.cmd_doctor(args)
    assert rc == 0
    out = capsys.readouterr().out
    # Existing summary line
    assert "checked 1 project(s)" in out
    # Metrics block appended
    assert "--- Injection metrics" in out
    assert "cold%" in out
    assert "active-recall%" in out
    assert "write:read" in out
    assert "deferred" in out


def test_doctor_metrics_empty_log(tmp_path, capsys, monkeypatch):
    """doctor with missing log → 'no data yet' for active-recall, exit 0, --strict unaffected."""
    _make_minimal_store(tmp_path)
    missing_log = tmp_path / "nonexistent.jsonl"

    monkeypatch.setattr(memory_cli, "PROJECTS_ROOT", tmp_path)
    monkeypatch.setattr(memory_cli, "AUTOINJECT_LOG", missing_log)

    args = type(
        "A",
        (),
        {
            "project": None,
            "strict": False,
            "stale_days": memory_cli.STALE_DAYS,
            "log": None,
        },
    )()
    rc = memory_cli.cmd_doctor(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "no data yet" in out
    # Metrics block still present
    assert "--- Injection metrics" in out
