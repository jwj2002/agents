"""D1 non-throwing usage collector (cost-telemetry-v0 §D1).

Unifies Claude + Codex transcript mining into a single incremental pipeline:
  - Calls the existing extract_records(strict=False) per transcript (reuses all
    attribution logic verbatim — no fork of the state machine).
  - Post-classifies each returned record via token_collector.is_known_model:
      known model  → normalize + write to usage.jsonl
      unknown model → quarantine row (cost_usd=None) → usage-quarantine.jsonl
  - PID-aware stale lock, incremental state, --reprocess-quarantine, --check.

Exit codes (stable, launchd+tests depend on these):
  0  ok / no new rows
  1  partial (>=1 quarantined this run)
  2  source tree unreadable
  3  stale-lock recovery FAILED
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import files_changed_enrich as FCE  # noqa: E402
import otel_sink as O  # noqa: E402
import token_collector as C  # noqa: E402
import usage_collector_claude as UC  # noqa: E402
import usage_collector_codex as CC  # noqa: E402
import usage_schema as S  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOCK_STALE_MIN = 30  # minutes before a lock is considered stale
LOCK_FILENAME = "cost-telemetry.lock"
STATE_FILENAME = "cost-telemetry.state"
REQUEST_FILENAME = ".collect-requested"
LOG_FILENAME = "cost-telemetry.log"
MALFORMED_ALARM_THRESHOLD = 0.02  # >2% malformed rows → alarm

# ---------------------------------------------------------------------------
# Logging setup — structured single logger; tests can capture via propagation
# ---------------------------------------------------------------------------
logger = logging.getLogger("usage_collect")


def _setup_logging(log_path: Path) -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    # File handler
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # Stderr handler for interactive use
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)


# ---------------------------------------------------------------------------
# Host helper (mirrors usage_collector_claude fallback)
# ---------------------------------------------------------------------------
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
    from project_resolver import get_host_name  # type: ignore[import]
except Exception:

    def get_host_name() -> str:  # type: ignore[misc]
        return socket.gethostname().split(".")[0]


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _telemetry_dir(base_dir: Path | None = None) -> Path:
    if base_dir:
        return Path(base_dir)
    return Path.home() / ".claude" / "telemetry" / get_host_name()


def _log_path(base_dir: Path | None = None) -> Path:
    if base_dir:
        return Path(base_dir) / LOG_FILENAME
    return Path.home() / ".claude" / "logs" / LOG_FILENAME


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------
def _lock_path(tdir: Path) -> Path:
    return tdir.parent / LOCK_FILENAME  # sibling of the host shard dir


def _read_lock(lock: Path) -> dict | None:
    """Return {pid, start_ts} from the lock file, or None if missing/corrupt."""
    if not lock.exists():
        return None
    try:
        return json.loads(lock.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_lock(lock: Path) -> None:
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({"pid": os.getpid(), "start_ts": time.time()}), encoding="utf-8"
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_lock(lock: Path, tdir: Path) -> str:
    """Try to acquire the PID lock.

    Returns:
      "acquired"        — lock written, caller may proceed
      "running"         — a live process holds the lock; caller should exit 0
      "recovered"       — dead/stale lock replaced; caller may proceed (warn in log)
      "recovery_failed" — could not write new lock; caller should exit 3
    """
    info = _read_lock(lock)
    if info is not None:
        pid = info.get("pid", 0)
        start_ts = info.get("start_ts", 0)
        age_min = (time.time() - start_ts) / 60
        alive = _pid_alive(int(pid)) if pid else False
        if alive and age_min < LOCK_STALE_MIN:
            logger.info(
                "Lock held by live PID %s (age %.1f min) — skipping run", pid, age_min
            )
            return "running"
        # Dead PID or stale lock
        reason = (
            "dead PID"
            if not alive
            else f"stale ({age_min:.1f} min > {LOCK_STALE_MIN} min)"
        )
        logger.warning(
            "Stale lock found (PID %s, %s) — recovering; previous holder may have crashed",
            pid,
            reason,
        )
        # Record recovery in state
        _update_state(
            tdir,
            {
                "last_lock_recovery": datetime.now(timezone.utc).isoformat(),
                "lock_recovery_reason": reason,
            },
        )
    try:
        _write_lock(lock)
        return "recovered" if info is not None else "acquired"
    except OSError as exc:
        logger.error("Failed to write lock file %s: %s", lock, exc)
        return "recovery_failed"


def _release_lock(lock: Path) -> None:
    try:
        lock.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------
def _state_path(tdir: Path) -> Path:
    return tdir.parent / STATE_FILENAME


def _read_state(tdir: Path) -> dict:
    p = _state_path(tdir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _update_state(tdir: Path, updates: dict) -> None:
    p = _state_path(tdir)
    p.parent.mkdir(parents=True, exist_ok=True)
    state = _read_state(tdir)
    state.update(updates)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# JSONL shard helpers
# ---------------------------------------------------------------------------
def _read_dedup_keys(path: Path) -> set:
    if not path.exists():
        return set()
    keys: set = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            keys.add(json.loads(line).get("dedup_key"))
        except json.JSONDecodeError:
            continue
    return keys


def _append_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------------------
# Quarantine row builder
# ---------------------------------------------------------------------------
def _quarantine_row(
    rec: dict, *, source_path: str, source_mtime: float, reason: str
) -> dict:
    """Build a quarantine row from a post-classified record."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "provider": rec.get("provider"),
        "source_path": source_path,
        "source_mtime": source_mtime,
        "dedup_key": rec.get("dedup_key"),
        "model": rec.get("model"),
        "input": rec.get("input", 0),
        "output": rec.get("output", 0),
        "cache_read": rec.get("cache_read", 0),
        "cache_creation": rec.get("cache_creation", 0),
        "project": rec.get("project"),
        "task": rec.get("task"),
        "work_host": rec.get("work_host"),
        "session_id": rec.get("session_id"),
        "ts": rec.get("ts"),
        "cost_usd": None,  # NEVER price an unknown model
        "reason": reason,
        "first_seen": now,
        "last_seen": now,
        "attempt_count": 1,
        "price_table_version_seen": O.PRICE_TABLE_VERSION,
        "resolved": False,
    }


# ---------------------------------------------------------------------------
# Collect one Claude transcript
# ---------------------------------------------------------------------------
def _collect_claude_transcript(
    tpath: str,
    *,
    inference_host: str,
    usage_keys: set,
    quarantine_keys: set,
    account_map: dict,
    fallback_account: dict | None,
) -> dict:
    """Extract records from one Claude transcript and post-classify by model.

    Returns a stats dict + lists of records ready for append.
    """
    try:
        entries = UC.read_transcript(tpath)
    except Exception as exc:
        logger.warning("Unreadable Claude transcript %s: %s", tpath, exc)
        return {
            "sources_unreadable": 1,
            "usage_rows": [],
            "quarantine_rows": [],
            "rows_malformed": 0,
        }

    try:
        source_mtime = Path(tpath).stat().st_mtime
    except OSError:
        source_mtime = 0.0

    try:
        records = UC.extract_records(
            entries,
            inference_host=inference_host,
            strict=False,
            account_map=account_map,
            fallback_account=fallback_account,
        )
    except Exception as exc:
        logger.warning("Error extracting records from %s: %s", tpath, exc)
        return {
            "sources_unreadable": 1,
            "usage_rows": [],
            "quarantine_rows": [],
            "rows_malformed": 0,
        }

    usage_rows: list = []
    quarantine_rows: list = []
    rows_malformed = 0
    dup_keys_skipped = 0

    for rec in records:
        dk = rec.get("dedup_key")
        model = rec.get("model")

        # Basic sanity — a record without a dedup_key is malformed
        if not dk:
            rows_malformed += 1
            continue

        if C.is_known_model(model):
            if dk in usage_keys:
                dup_keys_skipped += 1
                continue
            usage_keys.add(dk)
            usage_rows.append(S.normalize(rec))
        else:
            if dk in quarantine_keys:
                dup_keys_skipped += 1
                continue
            quarantine_keys.add(dk)
            quarantine_rows.append(
                _quarantine_row(
                    rec,
                    source_path=tpath,
                    source_mtime=source_mtime,
                    reason="unknown_model",
                )
            )

    return {
        "sources_unreadable": 0,
        "usage_rows": usage_rows,
        "quarantine_rows": quarantine_rows,
        "rows_malformed": rows_malformed,
        "dup_keys_skipped": dup_keys_skipped,
    }


# ---------------------------------------------------------------------------
# Collect one Codex session
# ---------------------------------------------------------------------------
def _collect_codex_session(
    spath: str,
    *,
    inference_host: str,
    account_info: dict,
    usage_keys: set,
    quarantine_keys: set,
) -> dict:
    """Extract records from one Codex session and post-classify by model."""
    try:
        entries = CC.read_session(spath)
    except Exception as exc:
        logger.warning("Unreadable Codex session %s: %s", spath, exc)
        return {
            "sources_unreadable": 1,
            "usage_rows": [],
            "quarantine_rows": [],
            "rows_malformed": 0,
        }

    try:
        source_mtime = Path(spath).stat().st_mtime
    except OSError:
        source_mtime = 0.0

    try:
        records = CC.extract_records(
            entries,
            inference_host=inference_host,
            account_info=account_info,
            strict=False,
        )
    except Exception as exc:
        logger.warning("Error extracting records from %s: %s", spath, exc)
        return {
            "sources_unreadable": 1,
            "usage_rows": [],
            "quarantine_rows": [],
            "rows_malformed": 0,
        }

    usage_rows: list = []
    quarantine_rows: list = []
    rows_malformed = 0
    dup_keys_skipped = 0

    for rec in records:
        dk = rec.get("dedup_key")
        model = rec.get("model")

        if not dk:
            rows_malformed += 1
            continue

        if C.is_known_model(model):
            if dk in usage_keys:
                dup_keys_skipped += 1
                continue
            usage_keys.add(dk)
            usage_rows.append(S.normalize(rec))
        else:
            if dk in quarantine_keys:
                dup_keys_skipped += 1
                continue
            quarantine_keys.add(dk)
            quarantine_rows.append(
                _quarantine_row(
                    rec,
                    source_path=spath,
                    source_mtime=source_mtime,
                    reason="unknown_model",
                )
            )

    return {
        "sources_unreadable": 0,
        "usage_rows": usage_rows,
        "quarantine_rows": quarantine_rows,
        "rows_malformed": rows_malformed,
        "dup_keys_skipped": dup_keys_skipped,
    }


# ---------------------------------------------------------------------------
# Main collection run
# ---------------------------------------------------------------------------
def run_collect(
    *,
    base_dir: Path | None = None,
    full: bool = False,
    enrich: bool = True,
    repo_root: Path | None = None,
    metrics_path: Path | None = None,
    claude_projects_dir: Path | None = None,
    codex_sessions_dir: Path | None = None,
    sidecar_path: Path | None = None,
    claude_json_path: Path | None = None,
    codex_auth_path: Path | None = None,
) -> tuple[int, dict]:
    """Run the collection pipeline.

    Returns (exit_code, stats).
    """
    tdir = _telemetry_dir(base_dir)
    tdir.mkdir(parents=True, exist_ok=True)
    log_path = _log_path(base_dir)
    _setup_logging(log_path)

    # --- consume .collect-requested marker ---
    req_path = tdir.parent / REQUEST_FILENAME
    if req_path.exists():
        try:
            age = time.time() - req_path.stat().st_mtime
            logger.info("Consuming .collect-requested (age %.0f s)", age)
            req_path.unlink()
        except OSError:
            pass

    # --- acquire lock ---
    lock = _lock_path(tdir)
    lock_result = _acquire_lock(lock, tdir)
    if lock_result == "running":
        return 0, {"note": "already_running"}
    if lock_result == "recovery_failed":
        logger.error("Stale lock recovery failed — aborting")
        return 3, {"note": "lock_recovery_failed"}
    # lock_result in ("acquired", "recovered") — proceed

    home = Path.home()
    projects_dir = claude_projects_dir or (home / ".claude" / "projects")
    codex_dir = codex_sessions_dir or (home / ".codex" / "sessions")
    auth_path = codex_auth_path or (home / ".codex" / "auth.json")
    sidecar = sidecar_path or (home / ".claude" / "telemetry" / "account-map.jsonl")
    cj_path = claude_json_path or (home / ".claude.json")

    # Check source tree is accessible
    if not projects_dir.exists() and not codex_dir.exists():
        logger.error(
            "Source tree unreadable: neither %s nor %s exists", projects_dir, codex_dir
        )
        _release_lock(lock)
        return 2, {"note": "source_tree_unreadable"}

    # --- read state + determine watermark ---
    state = _read_state(tdir)
    source_watermark = state.get("source_watermark", 0.0) if not full else 0.0
    run_start = time.time()

    # --- paths ---
    usage_path = tdir / "usage.jsonl"
    quarantine_path = tdir / "usage-quarantine.jsonl"

    # --- preload dedup sets ---
    usage_keys = _read_dedup_keys(usage_path)
    quarantine_keys: set = set()
    for qrow in _read_jsonl(quarantine_path):
        dk = qrow.get("dedup_key")
        if dk:
            quarantine_keys.add(dk)

    # --- account info ---
    account_map = UC.load_account_map(sidecar)
    fallback_account = UC.current_account(cj_path)
    codex_account_info = CC.read_codex_account(auth_path)
    inference_host = get_host_name()

    # --- run stats ---
    stats: dict = {
        "sources_seen": 0,
        "sources_processed": 0,
        "sources_unreadable": 0,
        "rows_malformed": 0,
        "rows_known_written": 0,
        "rows_quarantined": 0,
        "dup_keys_skipped": 0,
    }

    all_usage_rows: list = []
    all_quarantine_rows: list = []

    # --- Claude transcripts ---
    if projects_dir.exists():
        for tpath in sorted(glob.glob(str(projects_dir / "*" / "*.jsonl"))):
            try:
                mtime = Path(tpath).stat().st_mtime
            except OSError:
                continue
            stats["sources_seen"] += 1
            # incremental: process files with mtime in (source_watermark, run_start)
            if not full and not (source_watermark < mtime < run_start):
                continue
            stats["sources_processed"] += 1
            result = _collect_claude_transcript(
                tpath,
                inference_host=inference_host,
                usage_keys=usage_keys,
                quarantine_keys=quarantine_keys,
                account_map=account_map,
                fallback_account=fallback_account,
            )
            stats["sources_unreadable"] += result["sources_unreadable"]
            stats["rows_malformed"] += result["rows_malformed"]
            stats["dup_keys_skipped"] += result.get("dup_keys_skipped", 0)
            all_usage_rows.extend(result["usage_rows"])
            all_quarantine_rows.extend(result["quarantine_rows"])

    # --- Codex sessions ---
    if codex_dir.exists():
        for spath in sorted(
            glob.glob(str(codex_dir / "**" / "*.jsonl"), recursive=True)
        ):
            try:
                mtime = Path(spath).stat().st_mtime
            except OSError:
                continue
            stats["sources_seen"] += 1
            if not full and not (source_watermark < mtime < run_start):
                continue
            stats["sources_processed"] += 1
            result = _collect_codex_session(
                spath,
                inference_host=inference_host,
                account_info=codex_account_info,
                usage_keys=usage_keys,
                quarantine_keys=quarantine_keys,
            )
            stats["sources_unreadable"] += result["sources_unreadable"]
            stats["rows_malformed"] += result["rows_malformed"]
            stats["dup_keys_skipped"] += result.get("dup_keys_skipped", 0)
            all_usage_rows.extend(result["usage_rows"])
            all_quarantine_rows.extend(result["quarantine_rows"])

    # --- enrich files_changed / files_changed_source ---
    # Resolve enrichment inputs to their LIVE defaults (the bug behind "100% files_changed_source=none":
    # run_collect was never handed these, so all tiers were inert). metrics.jsonl is the orchestrate
    # outcome log; the sessions shard is the per-host capture stream (best-effort, None if absent).
    if enrich and all_usage_rows:
        _sessions_shard = tdir / "sessions.jsonl"
        _resolved_metrics = metrics_path or (
            Path.home() / ".claude" / "memory" / "metrics.jsonl"
        )
        _resolved_repo = repo_root
        _enrich_cache: dict = {}  # task -> (files_changed, source)
        for row in all_usage_rows:
            task = row.get("task")
            if task not in _enrich_cache:
                _enrich_cache[task] = FCE.enrich_task(
                    task,
                    repo_root=_resolved_repo,
                    metrics_path=_resolved_metrics,
                    sessions_shard=_sessions_shard
                    if _sessions_shard.exists()
                    else None,
                )
            fc, fcs = _enrich_cache[task]
            row["files_changed"] = fc
            row["files_changed_source"] = fcs

    # --- write rows ---
    if all_usage_rows:
        _append_jsonl(usage_path, all_usage_rows)
    if all_quarantine_rows:
        _append_jsonl(quarantine_path, all_quarantine_rows)

    stats["rows_known_written"] = len(all_usage_rows)
    stats["rows_quarantined"] = len(all_quarantine_rows)

    # --- malformed alarm ---
    records_emitted = stats["rows_known_written"] + stats["rows_quarantined"]
    if records_emitted > 0:
        malformed_rate = stats["rows_malformed"] / records_emitted
        if malformed_rate > MALFORMED_ALARM_THRESHOLD:
            logger.warning(
                "ALARM: malformed row rate %.1f%% > %.0f%% threshold (rows_malformed=%d, records_emitted=%d)",
                malformed_rate * 100,
                MALFORMED_ALARM_THRESHOLD * 100,
                stats["rows_malformed"],
                records_emitted,
            )

    # --- advance watermark: once all eligible transcripts parsed into EITHER file ---
    # Quarantine does NOT hold the watermark back; --reprocess-quarantine owns retries.
    _update_state(
        tdir,
        {
            "source_watermark": run_start,
            "last_success": datetime.now(timezone.utc).isoformat(),
            "last_run_stats": stats,
        },
    )

    _release_lock(lock)

    logger.info(
        "Run complete: seen=%d processed=%d known_written=%d quarantined=%d dup_skipped=%d unreadable=%d",
        stats["sources_seen"],
        stats["sources_processed"],
        stats["rows_known_written"],
        stats["rows_quarantined"],
        stats["dup_keys_skipped"],
        stats["sources_unreadable"],
    )

    exit_code = 1 if stats["rows_quarantined"] > 0 else 0
    return exit_code, stats


# ---------------------------------------------------------------------------
# --reprocess-quarantine
# ---------------------------------------------------------------------------
def run_reprocess_quarantine(
    *,
    base_dir: Path | None = None,
) -> tuple[int, dict]:
    """Re-check quarantine rows; move now-known rows to usage.jsonl."""
    tdir = _telemetry_dir(base_dir)
    log_path = _log_path(base_dir)
    _setup_logging(log_path)

    usage_path = tdir / "usage.jsonl"
    quarantine_path = tdir / "usage-quarantine.jsonl"

    qrows = _read_jsonl(quarantine_path)
    usage_keys = _read_dedup_keys(usage_path)

    resolved_keys: set = set()
    new_usage_rows: list = []

    for qrow in qrows:
        if qrow.get("resolved"):
            continue
        model = qrow.get("model")
        dk = qrow.get("dedup_key")
        if not C.is_known_model(model):
            continue
        # Model is now known — price it
        cost_rec = {
            "model": model,
            "input": qrow.get("input", 0),
            "output": qrow.get("output", 0),
            "cache_read": qrow.get("cache_read", 0),
            "cache_creation": qrow.get("cache_creation", 0),
        }
        cost = C.session_cost(cost_rec, strict=True)
        usage_rec = {
            "provider": qrow.get("provider"),
            "account": None,
            "billing_type": None,
            "inference_host": get_host_name(),
            "work_host": qrow.get("work_host"),
            "project": qrow.get("project"),
            "task": qrow.get("task"),
            "model": model,
            "input": qrow.get("input", 0),
            "output": qrow.get("output", 0),
            "cache_read": qrow.get("cache_read", 0),
            "cache_creation": qrow.get("cache_creation", 0),
            "cost_usd": cost,
            "ts": qrow.get("ts"),
            "session_id": qrow.get("session_id"),
            "dedup_key": dk,
        }
        normalized = S.normalize(usage_rec)

        if dk not in usage_keys:
            usage_keys.add(dk)
            new_usage_rows.append(normalized)
        # Mark resolved regardless of dedup (no row in both files)
        if dk:
            resolved_keys.add(dk)

    # Write newly priced rows
    if new_usage_rows:
        _append_jsonl(usage_path, new_usage_rows)

    # Rewrite quarantine file marking resolved rows
    if resolved_keys:
        new_qrows = []
        for qrow in qrows:
            dk = qrow.get("dedup_key")
            if dk in resolved_keys:
                qrow = dict(qrow)
                qrow["resolved"] = True
            new_qrows.append(qrow)
        quarantine_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in new_qrows) + "\n",
            encoding="utf-8",
        )

    stats = {
        "resolved": len(resolved_keys),
        "written_to_usage": len(new_usage_rows),
        "still_unknown": sum(
            1
            for r in qrows
            if not r.get("resolved") and not C.is_known_model(r.get("model"))
        ),
    }
    logger.info("Reprocess quarantine: %s", stats)
    return 0, stats


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------
def run_check(*, base_dir: Path | None = None) -> None:
    """Print collector status to stdout."""
    tdir = _telemetry_dir(base_dir)
    state = _read_state(tdir)
    usage_path = tdir / "usage.jsonl"
    quarantine_path = tdir / "usage-quarantine.jsonl"
    lock = _lock_path(tdir)
    req_path = tdir.parent / REQUEST_FILENAME

    lines = ["=== usage_collect --check ==="]

    # Last run info
    last_success = state.get("last_success", "never")
    last_stats = state.get("last_run_stats", {})
    lines.append(f"last_success: {last_success}")
    if last_stats:
        lines.append(f"last_run_stats: {json.dumps(last_stats)}")

    # Shard freshness
    if usage_path.exists():
        age = time.time() - usage_path.stat().st_mtime
        row_count = sum(
            1
            for ln in usage_path.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines()
            if ln.strip()
        )
        lines.append(f"usage.jsonl: {row_count} rows, last modified {age:.0f}s ago")
    else:
        lines.append("usage.jsonl: MISSING")

    # Quarantine summary
    if quarantine_path.exists():
        qrows = _read_jsonl(quarantine_path)
        unresolved = [r for r in qrows if not r.get("resolved")]
        models = sorted({r.get("model") for r in unresolved if r.get("model")})
        lines.append(
            f"usage-quarantine.jsonl: {len(unresolved)} unresolved rows, models: {models}"
        )
    else:
        lines.append("usage-quarantine.jsonl: empty/missing")

    # Lock state
    lock_info = _read_lock(lock)
    if lock_info:
        pid = lock_info.get("pid")
        age_min = (time.time() - lock_info.get("start_ts", 0)) / 60
        alive = _pid_alive(int(pid)) if pid else False
        lines.append(f"lock: PID {pid} alive={alive} age={age_min:.1f}min")
    else:
        lines.append("lock: not held")

    # Pending request
    if req_path.exists():
        age = time.time() - req_path.stat().st_mtime
        lines.append(f"pending .collect-requested: age {age:.0f}s")
    else:
        lines.append("pending .collect-requested: none")

    # Lock recovery info
    if state.get("last_lock_recovery"):
        lines.append(
            f"last_lock_recovery: {state['last_lock_recovery']} ({state.get('lock_recovery_reason', '?')})"
        )

    print("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="D1 non-throwing usage collector (cost-telemetry-v0 §D1)"
    )
    parser.add_argument(
        "--full", action="store_true", help="Ignore watermark; rescan all transcripts"
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip files_changed enrichment (rows get files_changed=null/source=none)",
    )
    parser.add_argument(
        "--reprocess-quarantine",
        action="store_true",
        help="Re-price quarantined rows after PRICES update",
    )
    parser.add_argument("--check", action="store_true", help="Print status and exit")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Override telemetry base dir (for tests)",
    )
    parser.add_argument("--claude-projects-dir", type=Path, default=None)
    parser.add_argument("--codex-sessions-dir", type=Path, default=None)
    parser.add_argument("--sidecar-path", type=Path, default=None)
    parser.add_argument("--claude-json-path", type=Path, default=None)
    parser.add_argument("--codex-auth-path", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.check:
        run_check(base_dir=args.base_dir)
        return 0

    if args.reprocess_quarantine:
        code, _stats = run_reprocess_quarantine(base_dir=args.base_dir)
        return code

    code, _stats = run_collect(
        base_dir=args.base_dir,
        full=args.full,
        enrich=not args.no_enrich,
        claude_projects_dir=args.claude_projects_dir,
        codex_sessions_dir=args.codex_sessions_dir,
        sidecar_path=args.sidecar_path,
        claude_json_path=args.claude_json_path,
        codex_auth_path=args.codex_auth_path,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
