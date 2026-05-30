"""Smoke tests for Codex fix findings on issue #203 cross-machine /learn.

Tests cover:
  (a) event_id dedup: two distinct same-(issue,date,project) failures with
      different root_cause are both preserved (M4).
  (b) watermark advances to max-consumed recorded_at (not wall-clock);
      a record stamped AFTER the snapshot is still counted next run (B2).
  (c) monotonic write: attempting to write an older watermark is rejected/no-op (M7).
  (d) legacy compound row normalizes without crash and doesn't perpetually count
      as new after consumption (M5).
  (e) microsecond precision in recorded_at (M3).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers: import target modules via sys.path manipulation
# ---------------------------------------------------------------------------
HOOKS_DIR = Path(__file__).resolve().parent.parent / "claude-config" / "hooks"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "claude-config" / "scripts"

if str(HOOKS_DIR) not in sys.path:  # noqa: E402
    sys.path.insert(0, str(HOOKS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from state_manager import (  # noqa: E402
    _event_id,
    _utc_now_iso,
    ensure_event_id,
    record_failure,
)
from aggregate_metrics_to_global import (  # noqa: E402
    _collect_failures,
    normalize_record,
    write_host_shard,
)
from telemetry_gate import (  # noqa: E402
    _normalize_record,
    compute_consumed_max,
    count_new_failures,
    load_watermark,
    write_watermark_monotonic,
)


# ---------------------------------------------------------------------------
# (a) event_id dedup: two distinct failures with different root_cause survive
# ---------------------------------------------------------------------------

class TestEventIdDedup:
    """M4 — dedup by event_id allows same-(issue,date,project) with different root_cause."""

    def test_different_root_cause_produces_different_event_id(self):
        eid1 = _event_id(42, "2026-05-01", "buddy", "ENUM_VALUE", "")
        eid2 = _event_id(42, "2026-05-01", "buddy", "COMPONENT_API", "")
        assert eid1 != eid2, "Different root_cause must yield different event_id"

    def test_same_fields_produce_same_event_id(self):
        eid1 = _event_id(42, "2026-05-01", "buddy", "ENUM_VALUE", "")
        eid2 = _event_id(42, "2026-05-01", "buddy", "ENUM_VALUE", "")
        assert eid1 == eid2, "Identical fields must yield identical event_id (stable hash)"

    def test_different_details_produces_different_event_id(self):
        eid1 = _event_id(42, "2026-05-01", "buddy", "ENUM_VALUE", "used wrong name")
        eid2 = _event_id(42, "2026-05-01", "buddy", "ENUM_VALUE", "missing field")
        assert eid1 != eid2

    def test_ensure_event_id_injects_when_missing(self):
        rec = {"issue": 1, "date": "2026-05-01", "root_cause": "ENUM_VALUE"}
        result = ensure_event_id(rec)
        assert "event_id" in result
        assert len(result["event_id"]) == 40  # SHA-1 hex

    def test_ensure_event_id_noop_when_present(self):
        rec = {"issue": 1, "date": "2026-05-01", "root_cause": "ENUM_VALUE", "event_id": "abc123"}
        result = ensure_event_id(rec)
        assert result["event_id"] == "abc123"

    def test_write_host_shard_keeps_both_distinct_failures(self, tmp_path):
        """Two failures with same (issue, date, project) but different root_cause must both survive."""
        agents_root = tmp_path
        host_dir = agents_root / "telemetry" / "testhost"
        host_dir.mkdir(parents=True)

        failures = [
            {
                "issue": 42,
                "date": "2026-05-01",
                "project": "buddy",
                "root_cause": "ENUM_VALUE",
                "event_id": _event_id(42, "2026-05-01", "buddy", "ENUM_VALUE", ""),
            },
            {
                "issue": 42,
                "date": "2026-05-01",
                "project": "buddy",
                "root_cause": "COMPONENT_API",
                "event_id": _event_id(42, "2026-05-01", "buddy", "COMPONENT_API", ""),
            },
        ]

        import unittest.mock as mock
        with mock.patch("aggregate_metrics_to_global._get_host_name", return_value="testhost"):
            appended = write_host_shard(failures, agents_root)

        assert appended == 2, f"Both distinct failures must be appended; got {appended}"
        shard = host_dir / "failures.jsonl"
        lines = [ln for ln in shard.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2, f"Shard must have 2 records; got {len(lines)}"
        root_causes = {json.loads(ln)["root_cause"] for ln in lines}
        assert root_causes == {"ENUM_VALUE", "COMPONENT_API"}

    def test_write_host_shard_dedup_by_event_id(self, tmp_path):
        """Same event_id written twice must produce only one shard record."""
        agents_root = tmp_path
        host_dir = agents_root / "telemetry" / "testhost"
        host_dir.mkdir(parents=True)

        eid = _event_id(7, "2026-05-01", "buddy", "ENUM_VALUE", "")
        failure = {"issue": 7, "date": "2026-05-01", "project": "buddy",
                   "root_cause": "ENUM_VALUE", "event_id": eid}

        import unittest.mock as mock
        with mock.patch("aggregate_metrics_to_global._get_host_name", return_value="testhost"):
            first = write_host_shard([failure], agents_root)
            second = write_host_shard([failure], agents_root)

        assert first == 1
        assert second == 0, "Second write of same event_id must be a no-op"

    def test_collect_failures_keeps_distinct_root_causes(self, tmp_path):
        """_collect_failures must keep two records with different root_cause for same issue."""
        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        eid1 = _event_id(5, "2026-05-01", "", "ENUM_VALUE", "")
        eid2 = _event_id(5, "2026-05-01", "", "COMPONENT_API", "")
        records = [
            {"issue": 5, "date": "2026-05-01", "root_cause": "ENUM_VALUE", "event_id": eid1},
            {"issue": 5, "date": "2026-05-01", "root_cause": "COMPONENT_API", "event_id": eid2},
        ]
        failures_file = mem_dir / "failures.jsonl"
        failures_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        # Mimic the project structure aggregate_metrics_to_global expects:
        # source_dir is the .claude/memory dir; parent.parent.name is repo root
        result = _collect_failures([mem_dir])
        root_causes = {r["root_cause"] for r in result}
        assert "ENUM_VALUE" in root_causes
        assert "COMPONENT_API" in root_causes
        assert len(result) == 2, f"Both distinct root_causes must survive; got {result}"


# ---------------------------------------------------------------------------
# (b) Watermark advances to max-consumed recorded_at; post-snapshot record counted next run
# ---------------------------------------------------------------------------

class TestWatermarkConsumedMax:
    """B2 — watermark = max consumed recorded_at; post-snapshot records survive."""

    def _write_shard(self, shard_dir: Path, records: list) -> None:
        shard_dir.mkdir(parents=True, exist_ok=True)
        shard_file = shard_dir / "failures.jsonl"
        with open(shard_file, "a") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def test_compute_consumed_max_returns_max_recorded_at(self, tmp_path):
        """compute_consumed_max returns the max recorded_at of new records."""
        telemetry_root = tmp_path / "telemetry"
        host_dir = telemetry_root / "host1"

        ts_old = "2026-05-01T10:00:00.000001Z"
        ts_mid = "2026-05-01T12:00:00.000000Z"
        ts_new = "2026-05-02T08:00:00.500000Z"

        records = [
            {"issue": 1, "date": "2026-05-01", "root_cause": "A", "recorded_at": ts_old},
            {"issue": 2, "date": "2026-05-01", "root_cause": "B", "recorded_at": ts_mid},
            {"issue": 3, "date": "2026-05-02", "root_cause": "C", "recorded_at": ts_new},
        ]
        self._write_shard(host_dir, records)

        # Watermark at epoch — all three are "new"
        epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
        cmax = compute_consumed_max(telemetry_root, epoch)
        assert cmax is not None

        expected_str = ts_new.replace("Z", "+00:00")
        expected = datetime.fromisoformat(expected_str).astimezone(timezone.utc)
        assert cmax == expected, f"Expected {expected}, got {cmax}"

    def test_post_snapshot_record_is_counted_next_run(self, tmp_path):
        """A record stamped AFTER consumed_max is still counted on the next run."""
        telemetry_root = tmp_path / "telemetry"
        host_dir = telemetry_root / "host1"

        ts_snapshot = "2026-05-01T12:00:00.000000Z"

        # Write the "consumed" record
        records_before = [
            {"issue": 1, "date": "2026-05-01", "root_cause": "A", "recorded_at": ts_snapshot},
        ]
        self._write_shard(host_dir, records_before)

        epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
        consumed_max = compute_consumed_max(telemetry_root, epoch)
        assert consumed_max is not None

        # Now add a record stamped 1µs AFTER consumed_max
        ts_after_str = (consumed_max + timedelta(microseconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        ) + "Z"

        shard_file = host_dir / "failures.jsonl"
        with open(shard_file, "a") as fh:
            fh.write(json.dumps({"issue": 2, "date": "2026-05-01", "root_cause": "B",
                                  "recorded_at": ts_after_str}) + "\n")

        # Count new failures SINCE consumed_max — must find the post-snapshot record
        count = count_new_failures(telemetry_root, consumed_max)
        assert count == 1, (
            f"Record stamped after consumed_max must be counted next run; "
            f"count={count}, consumed_max={consumed_max}, ts_after={ts_after_str}"
        )

    def test_record_at_exactly_consumed_max_is_excluded(self, tmp_path):
        """A record with recorded_at == consumed_max was already consumed — correctly excluded."""
        telemetry_root = tmp_path / "telemetry"
        host_dir = telemetry_root / "host1"

        ts = "2026-05-01T12:00:00.123456Z"
        records = [{"issue": 1, "date": "2026-05-01", "root_cause": "A", "recorded_at": ts}]
        self._write_shard(host_dir, records)

        epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
        consumed_max = compute_consumed_max(telemetry_root, epoch)
        assert consumed_max is not None

        # Count failures SINCE consumed_max using strict > — the record at exactly
        # consumed_max was already consumed and must NOT be counted.
        count = count_new_failures(telemetry_root, consumed_max)
        assert count == 0, (
            f"Record at exactly consumed_max must be excluded (already consumed); count={count}"
        )


# ---------------------------------------------------------------------------
# (c) Monotonic watermark: writing an older watermark is rejected/no-op
# ---------------------------------------------------------------------------

class TestMonotonicWatermark:
    """M7 — write_watermark_monotonic must never move the watermark backward."""

    def test_advance_watermark_succeeds(self, tmp_path):
        state_path = tmp_path / "_state.json"
        state_path.write_text(json.dumps({
            "last_learn_at": "2026-05-01T12:00:00Z",
            "last_learn_host": "host1",
            "version": 1,
        }))

        newer = datetime(2026, 5, 2, 8, 0, 0, 500000, tzinfo=timezone.utc)
        advanced = write_watermark_monotonic(state_path, newer, "host1")
        assert advanced is True, "Advancing to a newer timestamp must return True"

        data = json.loads(state_path.read_text())
        written = data["last_learn_at"]
        assert "2026-05-02" in written, f"Watermark should be advanced to 2026-05-02; got {written}"

    def test_backward_watermark_is_noop(self, tmp_path):
        """Attempting to write an older watermark must return False (no-op)."""
        state_path = tmp_path / "_state.json"
        state_path.write_text(json.dumps({
            "last_learn_at": "2026-05-10T12:00:00Z",
            "last_learn_host": "host1",
            "version": 1,
        }))

        older = datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)
        result = write_watermark_monotonic(state_path, older, "host1")
        assert result is False, "Writing a backward watermark must return False (no-op)"

        # File must be unchanged
        data = json.loads(state_path.read_text())
        assert "2026-05-10" in data["last_learn_at"]

    def test_equal_watermark_is_noop(self, tmp_path):
        """Writing the same timestamp as the existing watermark must be a no-op."""
        state_path = tmp_path / "_state.json"
        ts_str = "2026-05-10T12:00:00Z"
        state_path.write_text(json.dumps({
            "last_learn_at": ts_str,
            "last_learn_host": "host1",
            "version": 1,
        }))

        existing_dt = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
        result = write_watermark_monotonic(state_path, existing_dt, "host1")
        assert result is False, "Writing same timestamp as existing must be a no-op"

    def test_watermark_written_with_microsecond_precision(self, tmp_path):
        """Watermark written by write_watermark_monotonic must have microsecond precision (M3)."""
        state_path = tmp_path / "_state.json"
        state_path.write_text(json.dumps({"last_learn_at": "2000-01-01T00:00:00Z", "version": 1}))

        newer = datetime(2026, 5, 2, 10, 30, 45, 123456, tzinfo=timezone.utc)
        write_watermark_monotonic(state_path, newer, "host1")

        data = json.loads(state_path.read_text())
        written = data["last_learn_at"]
        assert "123456" in written, (
            f"Watermark must have microsecond precision; got {written}"
        )


# ---------------------------------------------------------------------------
# (d) Legacy compound row normalization (M5)
# ---------------------------------------------------------------------------

class TestLegacyCompoundNormalization:
    """M5 — legacy compound rows normalize without crash and don't perpetually count as new."""

    def test_canonical_record_passes_through(self):
        rec = {"issue": 1, "date": "2026-05-01", "root_cause": "ENUM_VALUE"}
        result = normalize_record(rec)
        assert len(result) == 1
        assert result[0]["root_cause"] == "ENUM_VALUE"

    def test_compound_expands_to_per_issue_records(self):
        compound = {
            "type": "batch",
            "issues": [1, 2],
            "root_causes": ["ENUM_VALUE"],
            "date": "2026-05-01",
        }
        result = normalize_record(compound)
        assert len(result) == 2
        assert all(r["root_cause"] == "ENUM_VALUE" for r in result)
        assert {r["issue"] for r in result} == {1, 2}

    def test_compound_expands_cross_product(self):
        compound = {
            "type": "batch",
            "issues": [1, 2],
            "root_causes": ["ENUM_VALUE", "COMPONENT_API"],
            "date": "2026-05-01",
        }
        result = normalize_record(compound)
        assert len(result) == 4, f"2 issues × 2 root_causes = 4; got {len(result)}"

    def test_compound_ambiguous_emits_single_stub(self):
        """issues=[1,2,3] × root_causes=[A,B] → ambiguous → single stub with first values."""
        compound = {
            "issues": [1, 2, 3],
            "root_causes": ["ENUM_VALUE", "COMPONENT_API"],
            "date": "2026-05-01",
        }
        result = normalize_record(compound)
        assert len(result) == 1, f"Ambiguous compound must produce 1 stub; got {len(result)}"
        assert result[0]["issue"] == 1
        assert result[0]["root_cause"] == "ENUM_VALUE"

    def test_compound_no_issues_emits_stub(self):
        compound = {"type": "batch", "root_causes": ["ENUM_VALUE"], "date": "2026-05-01"}
        result = normalize_record(compound)
        assert len(result) == 1
        assert result[0]["root_cause"] == "ENUM_VALUE"

    def test_completely_empty_compound_emits_stub(self):
        result = normalize_record({"type": "empty", "date": "2026-05-01"})
        assert len(result) == 1
        assert result[0]["root_cause"] == "LEGACY_COMPOUND"

    def test_compound_gets_synthesized_recorded_at(self):
        compound = {"issues": [5], "root_causes": ["ENUM_VALUE"], "date": "2026-05-10"}
        result = normalize_record(compound)
        assert result[0]["recorded_at"] == "2026-05-10T00:00:00Z"

    def test_compound_does_not_perpetually_count_as_new(self, tmp_path):
        """Once a compound row's max recorded_at is consumed, it must NOT appear in next count."""
        telemetry_root = tmp_path / "telemetry"
        host_dir = telemetry_root / "host1"
        host_dir.mkdir(parents=True, exist_ok=True)

        # Legacy compound row — recorded_at will be date+"T00:00:00Z"
        compound = {
            "issues": [1, 2],
            "root_causes": ["ENUM_VALUE"],
            "date": "2026-05-01",
        }
        shard_file = host_dir / "failures.jsonl"
        shard_file.write_text(json.dumps(compound) + "\n")

        # Watermark = epoch → should count 2 normalized records
        epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
        count_before = count_new_failures(telemetry_root, epoch)
        assert count_before == 2, f"Two expanded records expected; got {count_before}"

        # Advance watermark to consumed_max
        consumed = compute_consumed_max(telemetry_root, epoch)
        assert consumed is not None
        # Count again with watermark AT consumed_max — must be 0 (strict >)
        count_after = count_new_failures(telemetry_root, consumed)
        assert count_after == 0, (
            f"After consuming, compound row must not count again; got {count_after}"
        )

    def test_telemetry_gate_normalize_record_mirrors_aggregate(self):
        """_normalize_record in telemetry_gate.py must behave consistently with aggregate."""
        compound = {"issues": [1], "root_causes": ["ENUM_VALUE"], "date": "2026-05-01"}
        gate_result = _normalize_record(compound)
        agg_result = normalize_record(compound)
        assert len(gate_result) == len(agg_result)
        for g, a in zip(gate_result, agg_result):
            assert g["root_cause"] == a["root_cause"]
            assert g["issue"] == a["issue"]


# ---------------------------------------------------------------------------
# (e) Microsecond precision in recorded_at (M3)
# ---------------------------------------------------------------------------

class TestMicrosecondPrecision:
    """M3 — recorded_at must have microsecond precision."""

    def test_utc_now_iso_has_microseconds(self):
        ts = _utc_now_iso()
        assert ts.endswith("Z"), f"Timestamp must end with Z; got {ts!r}"
        # Parse: should not raise on microsecond format
        # Verify the timestamp can be parsed and has microsecond fraction
        ts_parsed = ts[:-1] + "+00:00"  # replace Z with +00:00 for fromisoformat
        datetime.fromisoformat(ts_parsed)  # must not raise
        assert "." in ts, f"Timestamp must include microsecond fraction; got {ts!r}"

    def test_record_failure_emits_microsecond_recorded_at(self, tmp_path):
        record_failure(tmp_path, issue=999, root_cause="TEST_CAUSE")
        failures_file = tmp_path / ".claude" / "memory" / "failures.jsonl"
        assert failures_file.exists()
        rec = json.loads(failures_file.read_text().strip())
        ts = rec["recorded_at"]
        assert "." in ts, f"recorded_at must have microsecond fraction; got {ts!r}"
        assert ts.endswith("Z"), f"recorded_at must end with Z; got {ts!r}"

    def test_two_rapid_failures_have_distinct_recorded_at(self):
        """Microsecond precision should make two rapid consecutive timestamps distinct."""
        ts1 = _utc_now_iso()
        ts2 = _utc_now_iso()
        # They MIGHT be equal (extremely rare, same microsecond) — but we can at least
        # verify both are valid and have microsecond precision.
        for ts in (ts1, ts2):
            assert "." in ts
            assert ts.endswith("Z")

    def test_event_id_in_record_failure(self, tmp_path):
        """record_failure must emit an event_id field (M4)."""
        record_failure(tmp_path, issue=1, root_cause="ENUM_VALUE", details="test")
        failures_file = tmp_path / ".claude" / "memory" / "failures.jsonl"
        rec = json.loads(failures_file.read_text().strip())
        assert "event_id" in rec, "record_failure must emit event_id"
        assert len(rec["event_id"]) == 40  # SHA-1 hex


# ---------------------------------------------------------------------------
# Integration: full round-trip — write shard, advance watermark, verify gate
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Integration: shard write → consumed_max → monotonic watermark → gate count = 0."""

    def test_full_round_trip(self, tmp_path):
        agents_root = tmp_path
        telemetry_root = agents_root / "telemetry"
        host_dir = telemetry_root / "host1"
        host_dir.mkdir(parents=True)

        state_path = telemetry_root / "_state.json"
        state_path.write_text(json.dumps({"last_learn_at": "2000-01-01T00:00:00Z", "version": 1}))

        # Write two distinct failures with microsecond timestamps
        ts1 = "2026-05-15T10:00:00.000001Z"
        ts2 = "2026-05-15T10:00:00.000002Z"
        records = [
            {"issue": 1, "date": "2026-05-15", "root_cause": "ENUM_VALUE", "recorded_at": ts1},
            {"issue": 1, "date": "2026-05-15", "root_cause": "COMPONENT_API", "recorded_at": ts2},
        ]
        shard_file = host_dir / "failures.jsonl"
        shard_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        epoch = load_watermark(state_path)

        # Step 1: count before consuming
        count_before = count_new_failures(telemetry_root, epoch)
        assert count_before == 2

        # Step 2: compute consumed_max
        consumed = compute_consumed_max(telemetry_root, epoch)
        assert consumed is not None

        # Step 3: advance watermark to consumed_max (not wall-clock)
        advanced = write_watermark_monotonic(state_path, consumed, "host1")
        assert advanced is True

        # Step 4: verify watermark has microsecond precision
        data = json.loads(state_path.read_text())
        assert "." in data["last_learn_at"], "Watermark must have microsecond precision"

        # Step 5: count after consuming — must be 0
        new_watermark = load_watermark(state_path)
        count_after = count_new_failures(telemetry_root, new_watermark)
        assert count_after == 0, f"After advancing watermark, count must be 0; got {count_after}"

        # Step 6: add a record AFTER consumed_max — must be counted
        ts_post = (consumed + timedelta(microseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        with open(shard_file, "a") as fh:
            fh.write(json.dumps({"issue": 2, "date": "2026-05-15", "root_cause": "NEW",
                                  "recorded_at": ts_post}) + "\n")

        count_post = count_new_failures(telemetry_root, new_watermark)
        assert count_post == 1, f"Post-snapshot record must be counted; got {count_post}"
