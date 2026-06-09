"""Tests for the shared hook helpers (issue #369)."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import hook_common as HC  # noqa: E402


def test_utc_now_iso_format():
    ts = HC.utc_now_iso()
    # microsecond precision + Z suffix — the watermark invariant depends on this
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", ts), ts


def test_consumers_share_one_definition():
    """Drift-proofing: the hook scripts must alias hook_common's functions,
    not carry their own copies."""
    import capture_session_telemetry as CT
    import state_manager as SM
    assert SM._utc_now_iso is HC.utc_now_iso
    assert CT._utc_now_iso is HC.utc_now_iso
    assert CT._get_host_name is HC.get_host_name
    assert CT._append_jsonl_fsync is HC.append_jsonl_fsync


def test_get_host_name_reads_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "host-name").write_text("my-box\n")
    assert HC.get_host_name() == "my-box"


def test_get_host_name_falls_back_to_hostname(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    name = HC.get_host_name()
    assert name and "." not in name and name == name.lower()


def test_append_jsonl_fsync_roundtrip(tmp_path):
    target = tmp_path / "sub" / "log.jsonl"
    HC.append_jsonl_fsync(target, {"a": 1})
    HC.append_jsonl_fsync(target, {"b": 2})
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert rows == [{"a": 1}, {"b": 2}]
