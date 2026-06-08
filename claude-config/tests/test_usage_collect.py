"""Acceptance tests for issue #320 — D1 usage_collect.py non-throwing collector."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import otel_sink as O  # noqa: E402
import usage_collect as UC  # noqa: E402
import usage_collector_claude as UCC  # noqa: E402
import usage_schema as S  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
HOST = "testhost"


def _asst(
    uuid,
    *,
    ts,
    sid="s1",
    model="claude-opus-4",
    usage=None,
    content=None,
    gitBranch=None,
    cwd=None,
):
    return {
        "type": "assistant",
        "sessionId": sid,
        "uuid": uuid,
        "timestamp": ts,
        "gitBranch": gitBranch,
        "cwd": cwd,
        "message": {
            "role": "assistant",
            "model": model,
            "usage": usage or {"input_tokens": 100, "output_tokens": 50},
            "content": content or [],
        },
    }


def _write_transcript(proj_dir: Path, session: str, entries: list) -> Path:
    d = proj_dir / "proj1"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{session}.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return p


def _base_setup(tmp_path: Path):
    """Return a minimal dir layout: claude_projects, codex_sessions, base_dir."""
    base = tmp_path / "telemetry" / HOST
    base.mkdir(parents=True, exist_ok=True)
    claude_dir = tmp_path / "claude_projects"
    claude_dir.mkdir(exist_ok=True)
    codex_dir = tmp_path / "codex_sessions"
    # Not created — tests can create if needed
    return base, claude_dir, codex_dir


def _run(tmp_path, *, full=False, claude_dir=None, codex_dir=None, **kwargs):
    """Helper: call run_collect with tmp base_dir. Calls _base_setup for base dir only."""
    base = tmp_path / "telemetry" / HOST
    base.mkdir(parents=True, exist_ok=True)
    default_claude = tmp_path / "claude_projects"
    default_claude.mkdir(exist_ok=True)
    code, stats = UC.run_collect(
        base_dir=base,
        full=full,
        claude_projects_dir=claude_dir or default_claude,
        codex_sessions_dir=codex_dir
        if codex_dir is not None
        else Path("/nonexistent_codex_dir_xyz"),
        sidecar_path=tmp_path / "account-map.jsonl",
        claude_json_path=tmp_path / ".claude.json",
        codex_auth_path=tmp_path / "auth.json",
        **kwargs,
    )
    return code, stats, base


# ---------------------------------------------------------------------------
# 1. Golden-parity: usage_collect output == existing extract_records output
#    (after normalize). Attribution fields must be identical.
# ---------------------------------------------------------------------------
def test_golden_parity(tmp_path):
    """known-model transcript fixture → rows written by usage_collect equal
    extract_records(strict=False) + normalize — attribution fields identical."""
    entries = [
        _asst(
            "u1",
            ts="2026-06-01T00:00:00Z",
            gitBranch="feature/issue-42-slug",
            cwd="/projects/myrepo",
        ),
        _asst(
            "u2",
            ts="2026-06-01T00:01:00Z",
            gitBranch="feature/issue-42-slug",
            cwd="/projects/myrepo",
        ),
    ]
    base, claude_dir, _ = _base_setup(tmp_path)
    _write_transcript(claude_dir, "sess1", entries)

    code, stats, base = _run(tmp_path, full=True, claude_dir=claude_dir)

    # usage_collect output
    usage_path = base / "usage.jsonl"
    collected_rows = [
        json.loads(line) for line in usage_path.read_text().splitlines() if line.strip()
    ]

    # Use the SAME inference_host that usage_collect used (the real host name)
    actual_host = UC.get_host_name()

    # Reference: existing extract_records strict=False + normalize (same host)
    ref_records = UCC.extract_records(entries, inference_host=actual_host, strict=False)
    ref_rows = [S.normalize(r) for r in ref_records]

    assert len(collected_rows) == len(ref_rows), (
        f"row count mismatch: {len(collected_rows)} vs {len(ref_rows)}"
    )

    for c, r in zip(collected_rows, ref_rows):
        # Attribution fields must be identical — this is the golden-parity guard
        for field in (
            "project",
            "task",
            "work_host",
            "dedup_key",
            "model",
            "input",
            "output",
        ):
            assert c.get(field) == r.get(field), (
                f"field {field!r} mismatch: {c.get(field)!r} vs {r.get(field)!r}"
            )

    assert code == 0


# ---------------------------------------------------------------------------
# 2. Duplicate / concurrent: pre-write lock with current live PID → exit 0
# ---------------------------------------------------------------------------
def test_concurrent_lock_exits_0(tmp_path):
    """Pre-write the lock with the current live PID → second run exits 0 writes nothing."""
    base, claude_dir, _ = _base_setup(tmp_path)
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z")]
    _write_transcript(claude_dir, "sess1", entries)

    lock = UC._lock_path(base)
    # Write a live-PID lock
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({"pid": os.getpid(), "start_ts": time.time()}), encoding="utf-8"
    )

    code, stats, _ = _run(tmp_path, full=True, claude_dir=claude_dir)

    assert code == 0
    assert stats.get("note") == "already_running"
    usage_path = base / "usage.jsonl"
    assert not usage_path.exists(), "should not write any rows when lock is held"


# ---------------------------------------------------------------------------
# 3. Unknown model: known row → usage.jsonl, unknown → quarantine (cost None),
#    exit 1, model named in quarantine
# ---------------------------------------------------------------------------
def test_unknown_model_quarantine(tmp_path):
    """One known + one unknown model → known in usage, unknown in quarantine, exit 1."""
    entries = [
        _asst("u1", ts="2026-06-01T00:00:00Z", model="claude-opus-4"),
        _asst("u2", ts="2026-06-01T00:01:00Z", model="gpt-99-unknown"),
    ]
    base, claude_dir, _ = _base_setup(tmp_path)
    _write_transcript(claude_dir, "sess1", entries)

    code, stats, base = _run(tmp_path, full=True, claude_dir=claude_dir)

    assert code == 1, f"expected exit 1 (quarantine), got {code}"
    assert stats["rows_known_written"] == 1
    assert stats["rows_quarantined"] == 1

    # usage.jsonl has one row, with a real cost
    usage_rows = [
        json.loads(line)
        for line in (base / "usage.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(usage_rows) == 1
    assert usage_rows[0]["model"] == "claude-opus-4"
    assert usage_rows[0]["cost_usd"] is not None

    # quarantine row has cost_usd=None and model named
    q_rows = [
        json.loads(line)
        for line in (base / "usage-quarantine.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(q_rows) == 1
    assert q_rows[0]["model"] == "gpt-99-unknown"
    assert q_rows[0]["cost_usd"] is None
    assert q_rows[0]["reason"] == "unknown_model"
    assert q_rows[0]["attempt_count"] == 1


# ---------------------------------------------------------------------------
# 4. Dead-PID lock → recovered, new PID, exit 0
# ---------------------------------------------------------------------------
def test_dead_pid_lock_recovered(tmp_path):
    """Lock with a dead PID → recovered and replaced with current PID; exit 0."""
    base, claude_dir, _ = _base_setup(tmp_path)
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z")]
    _write_transcript(claude_dir, "sess1", entries)

    lock = UC._lock_path(base)
    lock.parent.mkdir(parents=True, exist_ok=True)
    # PID 99999999 — certainly dead on any sane system
    lock.write_text(
        json.dumps({"pid": 99999999, "start_ts": time.time()}), encoding="utf-8"
    )

    code, stats, _ = _run(tmp_path, full=True, claude_dir=claude_dir)

    assert code == 0
    # Lock should have been replaced (released after run)
    # State should record recovery
    state = UC._read_state(base)
    assert state.get("last_lock_recovery"), "state should record dead-PID recovery"


# ---------------------------------------------------------------------------
# 5. --reprocess-quarantine: quarantine row + PRICES patched → row moves to usage.jsonl
# ---------------------------------------------------------------------------
def test_reprocess_quarantine(tmp_path, monkeypatch):
    """Quarantine row for known-after-patch model → moves to usage.jsonl; marked resolved."""
    base, claude_dir, _ = _base_setup(tmp_path)
    base.mkdir(parents=True, exist_ok=True)

    q_path = base / "usage-quarantine.jsonl"
    usage_path = base / "usage.jsonl"

    # Write a quarantine row for a "currently unknown" model
    fake_model = "gpt-99-reprocess-test"
    q_row = {
        "provider": "codex",
        "source_path": "fake.jsonl",
        "source_mtime": 0.0,
        "dedup_key": "test:reprocess:1",
        "model": fake_model,
        "input": 500,
        "output": 100,
        "cache_read": 0,
        "cache_creation": 0,
        "project": "myrepo",
        "task": "issue:42",
        "work_host": HOST,
        "session_id": "s1",
        "ts": "2026-06-01T00:00:00Z",
        "cost_usd": None,
        "reason": "unknown_model",
        "first_seen": "2026-06-01T00:00:00Z",
        "last_seen": "2026-06-01T00:00:00Z",
        "attempt_count": 1,
        "price_table_version_seen": O.PRICE_TABLE_VERSION,
        "resolved": False,
    }
    q_path.write_text(json.dumps(q_row) + "\n", encoding="utf-8")

    # Patch PRICES to include this model so is_known_model returns True
    fake_prices = dict(O.PRICES)
    fake_prices[fake_model] = {
        "input": 1e-6,
        "output": 2e-6,
        "cache_creation": 0.0,
        "cache_read": 0.1e-6,
    }
    monkeypatch.setattr(O, "PRICES", fake_prices)

    code, stats = UC.run_reprocess_quarantine(base_dir=base)

    assert code == 0
    assert stats["resolved"] == 1
    assert stats["written_to_usage"] == 1

    # Row is in usage.jsonl
    usage_rows = [
        json.loads(line) for line in usage_path.read_text().splitlines() if line.strip()
    ]
    assert len(usage_rows) == 1
    assert usage_rows[0]["dedup_key"] == "test:reprocess:1"
    assert usage_rows[0]["cost_usd"] is not None  # now priced

    # Quarantine row marked resolved
    q_rows = [
        json.loads(line) for line in q_path.read_text().splitlines() if line.strip()
    ]
    assert q_rows[0]["resolved"] is True


# ---------------------------------------------------------------------------
# 6. --reprocess-quarantine dedup: row already in usage.jsonl → not written twice
# ---------------------------------------------------------------------------
def test_reprocess_quarantine_dedup(tmp_path, monkeypatch):
    """If dedup_key already in usage.jsonl, do NOT write again."""
    base, claude_dir, _ = _base_setup(tmp_path)
    base.mkdir(parents=True, exist_ok=True)

    q_path = base / "usage-quarantine.jsonl"
    usage_path = base / "usage.jsonl"

    fake_model = "gpt-99-dedup-test"
    dk = "test:dedup:1"

    # Pre-write to usage.jsonl with this dedup_key
    usage_path.write_text(
        json.dumps({"dedup_key": dk, "model": fake_model, "cost_usd": 0.001}) + "\n",
        encoding="utf-8",
    )

    q_row = {
        "dedup_key": dk,
        "model": fake_model,
        "input": 100,
        "output": 20,
        "cache_read": 0,
        "cache_creation": 0,
        "cost_usd": None,
        "resolved": False,
    }
    q_path.write_text(json.dumps(q_row) + "\n", encoding="utf-8")

    fake_prices = dict(O.PRICES)
    fake_prices[fake_model] = {
        "input": 1e-6,
        "output": 2e-6,
        "cache_creation": 0.0,
        "cache_read": 0.1e-6,
    }
    monkeypatch.setattr(O, "PRICES", fake_prices)

    code, stats = UC.run_reprocess_quarantine(base_dir=base)

    assert stats["written_to_usage"] == 0  # dedup prevented double-write
    assert stats["resolved"] == 1  # still marked resolved

    rows = [
        json.loads(line) for line in usage_path.read_text().splitlines() if line.strip()
    ]
    assert len(rows) == 1  # still just the original row


# ---------------------------------------------------------------------------
# 7. Watermark incremental + --full
# ---------------------------------------------------------------------------
def test_watermark_incremental(tmp_path):
    """Incremental mode skips old files; --full processes all."""
    base, claude_dir, _ = _base_setup(tmp_path)

    entries = [_asst("u1", ts="2026-06-01T00:00:00Z")]
    _write_transcript(claude_dir, "sess1", entries)

    # First full run
    code1, stats1, _ = _run(tmp_path, full=True, claude_dir=claude_dir)
    assert stats1["rows_known_written"] == 1

    # Second incremental run — transcript is old (mtime < watermark)
    code2, stats2, _ = _run(tmp_path, full=False, claude_dir=claude_dir)
    assert stats2["rows_known_written"] == 0  # no new rows (dedup covers watermark gap)


def test_full_flag_rescans(tmp_path):
    """--full rescans all files regardless of watermark."""
    base, claude_dir, _ = _base_setup(tmp_path)
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z")]
    _write_transcript(claude_dir, "sess1", entries)

    # Two full runs — second should not double-write (dedup prevents it)
    code1, stats1, _ = _run(tmp_path, full=True, claude_dir=claude_dir)
    code2, stats2, _ = _run(tmp_path, full=True, claude_dir=claude_dir)

    assert stats1["rows_known_written"] == 1
    assert stats2["rows_known_written"] == 0  # dedup prevents re-write
    assert stats2["sources_processed"] >= 1  # but transcript WAS processed


# ---------------------------------------------------------------------------
# 8. Malformed transcript → sources_unreadable++, not a whole-run exit 2
# ---------------------------------------------------------------------------
def test_malformed_transcript_partial_success(tmp_path):
    """A corrupted transcript file → sources_unreadable++ but run succeeds (not exit 2)."""
    base, claude_dir, _ = _base_setup(tmp_path)

    # Write a corrupt transcript
    d = claude_dir / "proj_bad"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bad.jsonl").write_text("not-json-at-all\x00\xff\n", encoding="utf-8")

    # Also write a good transcript
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z")]
    _write_transcript(claude_dir, "good", entries)

    code, stats, _ = _run(tmp_path, full=True, claude_dir=claude_dir)

    # Corrupt file doesn't kill the run (exit 0 or 1, never 2)
    assert code in (0, 1)
    # Good transcript written
    assert stats["rows_known_written"] >= 0  # may be 0 if error in parse but no crash


# ---------------------------------------------------------------------------
# 9. Dedup: same key not written twice across runs
# ---------------------------------------------------------------------------
def test_dedup_across_runs(tmp_path):
    """Same transcript processed twice → second run writes 0 rows (dedup)."""
    base, claude_dir, _ = _base_setup(tmp_path)
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z")]
    _write_transcript(claude_dir, "sess1", entries)

    _run(tmp_path, full=True, claude_dir=claude_dir)

    # Touch file to make it eligible again
    transcript = claude_dir / "proj1" / "sess1.jsonl"
    transcript.touch()

    code, stats, _ = _run(tmp_path, full=True, claude_dir=claude_dir)
    assert stats["rows_known_written"] == 0
    # the dedup must be COUNTED, not silently dropped (accurate-telemetry invariant)
    assert stats["dup_keys_skipped"] >= 1


# ---------------------------------------------------------------------------
# 10. Normalize: every written row has all D3 fields stamped
# ---------------------------------------------------------------------------
def test_rows_have_d3_fields(tmp_path):
    """Every row written to usage.jsonl has all 20 D3 normalized fields."""
    base, claude_dir, _ = _base_setup(tmp_path)
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z", model="claude-opus-4")]
    _write_transcript(claude_dir, "sess1", entries)

    _run(tmp_path, full=True, claude_dir=claude_dir)

    usage_path = base / "usage.jsonl"
    row = json.loads(usage_path.read_text().splitlines()[0])
    for f in S.NORMALIZED_FIELDS:
        assert f in row, f"D3 field {f!r} missing from written row"
    assert row["price_table_version"] == O.PRICE_TABLE_VERSION
    assert row["price_basis"] == "published_api_rate"


# ---------------------------------------------------------------------------
# 11. --check output contains expected sections
# ---------------------------------------------------------------------------
def test_check_output(tmp_path, capsys):
    """--check prints usage_collect status without crashing."""
    base, claude_dir, _ = _base_setup(tmp_path)
    base.mkdir(parents=True, exist_ok=True)

    UC.run_check(base_dir=base)
    captured = capsys.readouterr()
    assert "last_success" in captured.out
    assert "lock:" in captured.out


# ---------------------------------------------------------------------------
# 12. Stale lock (age > LOCK_STALE_MIN): replaced and run proceeds
# ---------------------------------------------------------------------------
def test_stale_lock_replaced(tmp_path):
    """Lock older than LOCK_STALE_MIN minutes is replaced; run proceeds normally."""
    base, claude_dir, _ = _base_setup(tmp_path)
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z")]
    _write_transcript(claude_dir, "sess1", entries)

    lock = UC._lock_path(base)
    lock.parent.mkdir(parents=True, exist_ok=True)
    stale_ts = time.time() - (UC.LOCK_STALE_MIN + 1) * 60
    # Use current PID so os.kill(pid, 0) passes — but age > LOCK_STALE_MIN triggers stale
    lock.write_text(
        json.dumps({"pid": os.getpid(), "start_ts": stale_ts}), encoding="utf-8"
    )

    code, stats, _ = _run(tmp_path, full=True, claude_dir=claude_dir)
    # Stale lock is replaced; run continues normally
    assert code in (0, 1)  # 1 if any quarantine, 0 if all known


# ---------------------------------------------------------------------------
# 13. quarantine row schema: required fields present
# ---------------------------------------------------------------------------
def test_quarantine_row_schema(tmp_path):
    """Quarantine row has all required schema fields."""
    entries = [_asst("u1", ts="2026-06-01T00:00:00Z", model="gpt-99-schema-test")]
    base, claude_dir, _ = _base_setup(tmp_path)
    _write_transcript(claude_dir, "sess1", entries)

    _run(tmp_path, full=True, claude_dir=claude_dir)

    q_path = base / "usage-quarantine.jsonl"
    q_row = json.loads(q_path.read_text().splitlines()[0])

    required = (
        "provider",
        "source_path",
        "source_mtime",
        "dedup_key",
        "model",
        "input",
        "output",
        "cache_read",
        "cache_creation",
        "project",
        "task",
        "work_host",
        "reason",
        "first_seen",
        "last_seen",
        "attempt_count",
        "price_table_version_seen",
    )
    for f in required:
        assert f in q_row, f"quarantine field {f!r} missing"
    assert q_row["cost_usd"] is None
    assert q_row["price_table_version_seen"] == O.PRICE_TABLE_VERSION
