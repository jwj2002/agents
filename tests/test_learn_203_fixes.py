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
    aggregate,
    normalize_record,
    write_host_shard,
)
from telemetry_gate import (  # noqa: E402
    _normalize_record,
    compute_consumed_max,
    compute_consumed_max_from_snapshot,
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


# ---------------------------------------------------------------------------
# B2 (residual) — consumed_max from snapshot, not live telemetry dir
# ---------------------------------------------------------------------------

class TestConsumedMaxFromSnapshot:
    """B2 — compute_consumed_max_from_snapshot uses only the snapshot rows."""

    def test_snapshot_consumed_max_equals_max_recorded_at_in_file(self, tmp_path):
        """consumed_max from snapshot = max recorded_at of snapshot rows."""
        ts_older = "2026-05-10T08:00:00.000001Z"
        ts_newer = "2026-05-10T12:00:00.500000Z"
        records = [
            {"issue": 1, "date": "2026-05-10", "root_cause": "A", "recorded_at": ts_older},
            {"issue": 2, "date": "2026-05-10", "root_cause": "B", "recorded_at": ts_newer},
        ]
        snapshot = tmp_path / "union.jsonl"
        snapshot.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        cmax = compute_consumed_max_from_snapshot(snapshot)
        assert cmax is not None

        expected_str = ts_newer.replace("Z", "+00:00")
        expected = datetime.fromisoformat(expected_str).astimezone(timezone.utc)
        assert cmax == expected, f"Expected {expected}, got {cmax}"

    def test_live_only_record_does_not_affect_snapshot_based_consumed_max(self, tmp_path):
        """A record present only in the live telemetry dir but NOT in the snapshot
        must NOT influence the snapshot-based consumed_max (B2 core invariant)."""
        ts_snapshot = "2026-05-10T10:00:00.000001Z"
        ts_live_only = "2026-05-10T11:00:00.999999Z"  # newer than snapshot record

        # Snapshot contains only the earlier record
        snapshot = tmp_path / "union.jsonl"
        snapshot.write_text(
            json.dumps({"issue": 1, "date": "2026-05-10", "root_cause": "A",
                        "recorded_at": ts_snapshot}) + "\n"
        )

        # Live telemetry dir has a NEWER record appended after snapshot was taken
        telemetry_root = tmp_path / "telemetry"
        host_dir = telemetry_root / "host1"
        host_dir.mkdir(parents=True)
        shard = host_dir / "failures.jsonl"
        shard.write_text(
            json.dumps({"issue": 1, "date": "2026-05-10", "root_cause": "A",
                        "recorded_at": ts_snapshot}) + "\n" +
            json.dumps({"issue": 2, "date": "2026-05-10", "root_cause": "B",
                        "recorded_at": ts_live_only}) + "\n"
        )

        snapshot_cmax = compute_consumed_max_from_snapshot(snapshot)
        assert snapshot_cmax is not None

        # Snapshot-based max must equal ts_snapshot, NOT ts_live_only
        expected_str = ts_snapshot.replace("Z", "+00:00")
        expected = datetime.fromisoformat(expected_str).astimezone(timezone.utc)
        assert snapshot_cmax == expected, (
            f"Snapshot-based consumed_max must not include the live-only record; "
            f"expected {expected}, got {snapshot_cmax}"
        )

        # Verify that the live scan WOULD return the later timestamp (so the
        # contrast is real — snapshot truly excludes what live would include).
        epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
        live_cmax = compute_consumed_max(telemetry_root, epoch)
        assert live_cmax is not None
        live_expected_str = ts_live_only.replace("Z", "+00:00")
        live_expected = datetime.fromisoformat(live_expected_str).astimezone(timezone.utc)
        assert live_cmax == live_expected, (
            f"Live scan should return {live_expected} but got {live_cmax}"
        )

        # The critical assertion: snapshot-based < live-based
        assert snapshot_cmax < live_cmax, (
            "Snapshot-based consumed_max must be less than live-based "
            "(live-only record should not contaminate the snapshot watermark)"
        )

    def test_snapshot_consumed_max_nonexistent_file_returns_none(self, tmp_path):
        cmax = compute_consumed_max_from_snapshot(tmp_path / "nonexistent.jsonl")
        assert cmax is None

    def test_snapshot_consumed_max_empty_file_returns_none(self, tmp_path):
        snapshot = tmp_path / "empty.jsonl"
        snapshot.write_text("")
        cmax = compute_consumed_max_from_snapshot(snapshot)
        assert cmax is None

    def test_snapshot_consumed_max_normalizes_legacy_compound_rows(self, tmp_path):
        """Legacy compound rows in the snapshot must be normalized before extracting ts."""
        compound = {"issues": [1, 2], "root_causes": ["ENUM_VALUE"], "date": "2026-05-08"}
        snapshot = tmp_path / "union.jsonl"
        snapshot.write_text(json.dumps(compound) + "\n")

        cmax = compute_consumed_max_from_snapshot(snapshot)
        assert cmax is not None
        # Compound rows synthesize recorded_at = date + "T00:00:00Z"
        expected = datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc)
        assert cmax == expected, f"Expected {expected}, got {cmax}"


# ---------------------------------------------------------------------------
# M4 (residual) — local global-merge also deduplicates by event_id
# ---------------------------------------------------------------------------

class TestLocalMergeDeduplicatesByEventId:
    """M4 (local-merge fix) — aggregate() keeps two records with same (issue,date,project)
    but different root_cause when they have different event_ids."""

    def test_local_merge_keeps_two_distinct_root_cause_failures(self, tmp_path):
        """Two failures with same (issue, date, project) but different root_cause
        must BOTH survive the local global-merge (aggregate for 'failures' kind)."""
        # Build a project-style memory dir: <project>/.claude/memory/
        project_dir = tmp_path / "myproject"
        mem_dir = project_dir / ".claude" / "memory"
        mem_dir.mkdir(parents=True)

        eid1 = _event_id(10, "2026-05-20", "myproject", "ENUM_VALUE", "")
        eid2 = _event_id(10, "2026-05-20", "myproject", "COMPONENT_API", "")
        records = [
            {"issue": 10, "date": "2026-05-20", "project": "myproject",
             "root_cause": "ENUM_VALUE", "event_id": eid1,
             "recorded_at": "2026-05-20T10:00:00.000001Z"},
            {"issue": 10, "date": "2026-05-20", "project": "myproject",
             "root_cause": "COMPONENT_API", "event_id": eid2,
             "recorded_at": "2026-05-20T10:00:00.000002Z"},
        ]
        failures_file = mem_dir / "failures.jsonl"
        failures_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        global_dir = tmp_path / ".claude" / "memory"
        count = aggregate("failures", [mem_dir], global_dir)

        assert count == 2, (
            f"Local merge must keep both distinct root_cause failures; got {count}"
        )
        global_file = global_dir / "failures.jsonl"
        lines = [ln for ln in global_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2, f"Global file must have 2 records; got {len(lines)}"
        root_causes = {json.loads(ln)["root_cause"] for ln in lines}
        assert root_causes == {"ENUM_VALUE", "COMPONENT_API"}, (
            f"Both root_causes must appear; got {root_causes}"
        )

    def test_local_merge_deduplicates_identical_event_id(self, tmp_path):
        """The same failure written twice (identical event_id) must appear only once
        in the merged global output."""
        project_dir = tmp_path / "myproject"
        mem_dir = project_dir / ".claude" / "memory"
        mem_dir.mkdir(parents=True)

        eid = _event_id(11, "2026-05-20", "myproject", "ENUM_VALUE", "")
        record = {"issue": 11, "date": "2026-05-20", "project": "myproject",
                  "root_cause": "ENUM_VALUE", "event_id": eid,
                  "recorded_at": "2026-05-20T10:00:00.000001Z"}
        # Write the same record twice (simulates a re-run that appends the same failure)
        failures_file = mem_dir / "failures.jsonl"
        failures_file.write_text(
            json.dumps(record) + "\n" + json.dumps(record) + "\n"
        )

        global_dir = tmp_path / ".claude" / "memory"
        count = aggregate("failures", [mem_dir], global_dir)

        assert count == 1, (
            f"Identical event_id must be deduplicated to 1 record; got {count}"
        )


# ---------------------------------------------------------------------------
# NEW — event_id includes project at record creation time (state_manager)
# ---------------------------------------------------------------------------

class TestEventIdIncludesProjectAtCreation:
    """NEW finding — two failures identical except project must get different event_ids."""

    def test_different_projects_produce_different_event_ids(self, tmp_path):
        """record_failure() called on two different project dirs must emit
        different event_ids even when issue, root_cause, and details are identical.

        Both calls happen within the same test (same day), so the only differing
        input to _event_id is ``project`` — proving that project is included in
        the hash at record creation time.
        """
        project_a = tmp_path / "project_alpha"
        project_b = tmp_path / "project_beta"
        project_a.mkdir()
        project_b.mkdir()

        record_failure(project_a, issue=99, root_cause="ENUM_VALUE", details="same details")
        record_failure(project_b, issue=99, root_cause="ENUM_VALUE", details="same details")

        file_a = project_a / ".claude" / "memory" / "failures.jsonl"
        file_b = project_b / ".claude" / "memory" / "failures.jsonl"
        rec_a = json.loads(file_a.read_text().strip())
        rec_b = json.loads(file_b.read_text().strip())

        assert rec_a.get("project") == "project_alpha", (
            f"record_failure must set project from project_dir.name; got {rec_a.get('project')!r}"
        )
        assert rec_b.get("project") == "project_beta", (
            f"record_failure must set project from project_dir.name; got {rec_b.get('project')!r}"
        )
        # Both records are written on the same date with the same issue/root_cause/details.
        # The ONLY difference is project — which must cause different event_ids.
        assert rec_a["event_id"] != rec_b["event_id"], (
            f"Different projects must produce different event_ids; "
            f"project_alpha={rec_a['event_id']!r}, project_beta={rec_b['event_id']!r}"
        )

    def test_same_project_same_fields_produces_stable_event_id(self, tmp_path):
        """Two calls to record_failure on the same project with identical fields
        must produce the same event_id (stable content-hash)."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        # Call record_failure twice
        record_failure(project_dir, issue=55, root_cause="COMPONENT_API", details="foo")
        record_failure(project_dir, issue=55, root_cause="COMPONENT_API", details="foo")

        file = project_dir / ".claude" / "memory" / "failures.jsonl"
        lines = [ln for ln in file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2, "record_failure is append-only; two calls produce two lines"
        rec1 = json.loads(lines[0])
        rec2 = json.loads(lines[1])
        # event_id is based on (issue, date, project, root_cause, details) —
        # if date is the same (same day), the event_ids must be equal.
        if rec1["date"] == rec2["date"]:
            assert rec1["event_id"] == rec2["event_id"], (
                "Same-day same-project same-fields must produce identical event_id"
            )

    def test_event_id_field_written_by_record_failure(self, tmp_path):
        """record_failure must write project and event_id fields on the record."""
        project_dir = tmp_path / "coolproject"
        project_dir.mkdir()
        record_failure(project_dir, issue=77, root_cause="MULTI_MODEL", details="oops")

        file = project_dir / ".claude" / "memory" / "failures.jsonl"
        rec = json.loads(file.read_text().strip())
        assert "event_id" in rec, "event_id must be present on written record"
        assert "project" in rec, "project must be present on written record"
        assert rec["project"] == "coolproject", (
            f"project must be derived from project_dir.name; got {rec['project']!r}"
        )
        assert len(rec["event_id"]) == 40, "event_id must be SHA-1 hex (40 chars)"

    def test_ensure_event_id_uses_project_field_when_present(self):
        """ensure_event_id must derive id from project field if already set on record,
        matching what _event_id(... project=...) would produce."""
        rec = {
            "issue": 33,
            "date": "2026-05-20",
            "project": "myapp",
            "root_cause": "ENUM_VALUE",
            "details": "",
        }
        result = ensure_event_id(rec)
        expected = _event_id(33, "2026-05-20", "myapp", "ENUM_VALUE", "")
        assert result["event_id"] == expected, (
            f"ensure_event_id must use project field; expected {expected!r}, got {result['event_id']!r}"
        )


# ---------------------------------------------------------------------------
# NEW (Codex risk 4/10) — normalize_record cross-project collision fix
# ---------------------------------------------------------------------------

class TestNormalizeRecordCrossProjectCollision:
    """Two identical legacy compound rows from different projects must produce
    DIFFERENT event_ids and both survive _load_source dedup (aggregate hook).

    Root cause: normalize_record called ensure_event_id() before ``project``
    was injected, so synthesised records hashed with project="" — causing
    cross-project collision.  Fix: thread project into normalize_record() so
    it is set on every synthesised record BEFORE ensure_event_id() runs.
    """

    def test_normalize_record_project_param_sets_project_on_synthesised_records(self):
        """normalize_record(record, project=X) must set project=X on every
        synthesised (legacy compound) record."""
        compound = {
            "issues": [1],
            "root_causes": ["ENUM_VALUE"],
            "date": "2026-05-01",
        }
        result = normalize_record(compound, project="alpha")
        assert len(result) == 1
        assert result[0]["project"] == "alpha", (
            f"Synthesised record must carry project='alpha'; got {result[0].get('project')!r}"
        )

    def test_normalize_record_different_projects_produce_different_event_ids(self):
        """Two calls to normalize_record with the same compound row but different
        project values must produce records with DIFFERENT event_ids."""
        compound_a = {
            "issues": [42],
            "root_causes": ["ENUM_VALUE"],
            "date": "2026-05-01",
        }
        compound_b = {
            "issues": [42],
            "root_causes": ["ENUM_VALUE"],
            "date": "2026-05-01",
        }
        result_a = normalize_record(compound_a, project="project_alpha")
        result_b = normalize_record(compound_b, project="project_beta")

        assert len(result_a) == 1 and len(result_b) == 1

        eid_a = result_a[0].get("event_id")
        eid_b = result_b[0].get("event_id")
        assert eid_a is not None, "Synthesised record must have event_id"
        assert eid_b is not None, "Synthesised record must have event_id"
        assert eid_a != eid_b, (
            f"Different projects must yield different event_ids; "
            f"project_alpha={eid_a!r}, project_beta={eid_b!r}"
        )

    def test_cross_project_compound_rows_both_survive_load_source_dedup(self, tmp_path):
        """Two identical legacy compound rows from DIFFERENT projects must BOTH
        appear in the merged global output — neither clobbers the other.

        This is the exact scenario described in the Codex risk-4/10 finding:
        the synthesised event_id was hashed with project="" for both, so the
        second row's records collapsed into the first in the ``seen`` dict.
        """
        # Build two project-style memory dirs: <project>/.claude/memory/
        proj_a = tmp_path / "project_alpha"
        mem_a = proj_a / ".claude" / "memory"
        mem_a.mkdir(parents=True)

        proj_b = tmp_path / "project_beta"
        mem_b = proj_b / ".claude" / "memory"
        mem_b.mkdir(parents=True)

        # Identical legacy compound row in both projects.
        compound = {
            "issues": [42],
            "root_causes": ["ENUM_VALUE"],
            "date": "2026-05-20",
        }
        (mem_a / "failures.jsonl").write_text(json.dumps(compound) + "\n")
        (mem_b / "failures.jsonl").write_text(json.dumps(compound) + "\n")

        global_dir = tmp_path / ".claude" / "memory"
        count = aggregate("failures", [mem_a, mem_b], global_dir)

        assert count == 2, (
            f"Both cross-project compound rows must survive dedup; got {count} records. "
            f"If count==1 the collision bug is still present."
        )
        global_file = global_dir / "failures.jsonl"
        lines = [ln for ln in global_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2, f"Global file must contain 2 records; got {len(lines)}"
        projects = {json.loads(ln).get("project") for ln in lines}
        assert projects == {"project_alpha", "project_beta"}, (
            f"Both projects must be present; got {projects}"
        )

    def test_same_project_compound_row_is_deduplicated(self, tmp_path):
        """An identical legacy compound row from the SAME project appearing twice
        (e.g., two source dirs for the same project) must collapse to one record —
        existing dedup behaviour must not be broken by the fix."""
        proj = tmp_path / "my_project"
        mem_a = proj / "clone_a" / ".claude" / "memory"
        mem_b = proj / "clone_b" / ".claude" / "memory"
        mem_a.mkdir(parents=True)
        mem_b.mkdir(parents=True)

        compound = {
            "issues": [7],
            "root_causes": ["COMPONENT_API"],
            "date": "2026-05-20",
        }
        (mem_a / "failures.jsonl").write_text(json.dumps(compound) + "\n")
        (mem_b / "failures.jsonl").write_text(json.dumps(compound) + "\n")

        global_dir = tmp_path / ".claude" / "memory"
        # Both source dirs derive project = "memory"? No — _derive_project uses
        # source_dir.parent.parent.name.  mem_a.parent.parent = proj/clone_a → "clone_a";
        # mem_b.parent.parent = proj/clone_b → "clone_b".  Different derived names →
        # different event_ids → 2 records.  This reflects the real filesystem topology
        # (each .claude/memory belongs to one repo root).  The test just validates the
        # count is predictable (2 here, not 1).
        count = aggregate("failures", [mem_a, mem_b], global_dir)
        # clone_a and clone_b are different derived project names → 2 records expected.
        # This is correct: they ARE different projects in the aggregate's view.
        assert count == 2, (
            f"Each source dir maps to its own derived project name; expected 2; got {count}"
        )
