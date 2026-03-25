#!/usr/bin/env python3
"""
Claude Code PreCompact hook (Optimized v2):
- Extracts structured state from transcript
- Updates PERSISTENT_STATE.yaml with extracted info
- Keeps transcript checkpoint for recovery
- Identifies issue numbers, phases, and key decisions
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# File-based error logging
_log_file = Path.home() / ".claude" / "hooks.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_log_file),
    level=logging.WARNING,
    format="%(asctime)s [precompact] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

MAX_TAIL_LINES = 300  # Reduced from 600 - we extract structured state instead
CHECKPOINT_RETENTION_DAYS = 7  # Auto-delete checkpoints older than this


def tail_lines(path: Path, max_lines: int) -> list[str]:
    """Get last N lines from file."""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = 8192
        data = b""
        while size > 0 and data.count(b"\n") <= max_lines:
            step = min(block, size)
            size -= step
            f.seek(size)
            data = f.read(step) + data
        lines = data.splitlines()[-max_lines:]
        return [ln.decode("utf-8", errors="replace") for ln in lines]


def extract_state_from_transcript(transcript_lines: list[str]) -> dict:
    """Extract structured state from conversation transcript."""
    state = {
        "last_issue": None,
        "last_phase": None,
        "last_action": None,
        "pending_tasks": [],
        "key_decisions": [],
        "files_modified": [],
        "artifacts_created": [],
    }

    for line in transcript_lines:
        try:
            msg = json.loads(line)
            content = str(msg.get("content", ""))

            # Extract issue numbers (most recent wins)
            if matches := re.findall(r"[Ii]ssue[#\s]*(\d+)", content):
                state["last_issue"] = int(matches[-1])

            # Extract phase (most recent wins)
            for phase in ["MAP-PLAN", "TEST-PLAN", "CONTRACT", "PATCH", "PROVE"]:
                if phase in content:
                    state["last_phase"] = phase

            # Extract artifacts created
            if match := re.search(r"AGENT_RETURN:\s*(\S+\.md)", content):
                artifact = match.group(1)
                if artifact not in state["artifacts_created"]:
                    state["artifacts_created"].append(artifact)

            # Extract file modifications
            if match := re.search(r"(?:created|modified|updated).*?([a-zA-Z0-9_/]+\.(?:py|jsx?|tsx?|md))", content, re.I):
                filepath = match.group(1)
                if filepath not in state["files_modified"]:
                    state["files_modified"].append(filepath)

            # Extract TODO items (last 5)
            if "- [ ]" in content:
                todos = re.findall(r"- \[ \] (.+?)(?:\n|$)", content)
                for todo in todos[-5:]:
                    if todo not in state["pending_tasks"]:
                        state["pending_tasks"].append(todo)
                state["pending_tasks"] = state["pending_tasks"][-5:]

            # Extract key decisions (look for decision keywords)
            if any(kw in content.lower() for kw in ["decided", "decision:", "chose", "approach:"]):
                # Extract sentence containing decision
                sentences = re.split(r'[.!?]', content)
                for sent in sentences:
                    if any(kw in sent.lower() for kw in ["decided", "decision", "chose", "approach"]):
                        clean = sent.strip()[:100]
                        if clean and clean not in state["key_decisions"]:
                            state["key_decisions"].append(clean)
                state["key_decisions"] = state["key_decisions"][-5:]

        except (json.JSONDecodeError, TypeError):
            continue

    return state


def update_persistent_state(project_dir: Path, extracted: dict) -> None:
    """Update PERSISTENT_STATE.yaml with extracted info via state_manager."""
    try:
        from state_manager import update_from_extracted
        update_from_extracted(project_dir, extracted)
    except ImportError:
        # state_manager not on path, skip
        print("[precompact] Warning: state_manager not found, skipping state update", file=sys.stderr)
    except Exception as e:
        print(f"[precompact] Warning: Could not update PERSISTENT_STATE.yaml: {e}", file=sys.stderr)


def cleanup_old_checkpoints(out_dir: Path, retention_days: int) -> int:
    """Delete checkpoint files older than retention_days. Returns count of deleted files."""
    if not out_dir.exists():
        return 0

    cutoff = datetime.now().timestamp() - (retention_days * 86400)
    deleted = 0

    for f in out_dir.iterdir():
        # Skip PERSISTENT_STATE.yaml and other non-checkpoint files
        if f.name == "PERSISTENT_STATE.yaml":
            continue
        if not (f.suffix in [".jsonl", ".md"] and "__" in f.name):
            continue

        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        except OSError:
            continue

    return deleted


def main() -> int:
    hook_in = json.load(sys.stdin)
    transcript_path = Path(hook_in["transcript_path"]).expanduser()

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    out_dir = project_dir / ".agents" / "outputs" / "claude_checkpoints"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_id = hook_in.get("session_id", "unknown-session")
    trigger = hook_in.get("trigger", "unknown")

    # 1) Copy the transcript as a raw checkpoint (for recovery)
    raw_dst = out_dir / f"{ts}__{session_id}__{trigger}.transcript.jsonl"
    shutil.copyfile(transcript_path, raw_dst)

    # 2) Extract structured state from transcript
    tail = tail_lines(transcript_path, MAX_TAIL_LINES)
    extracted = extract_state_from_transcript(tail)

    # 3) Create a compact summary (not full tail dump)
    md_dst = out_dir / f"{ts}__{session_id}__{trigger}.md"
    summary = f"""# Claude Code Checkpoint

- **Time**: {ts}
- **Session**: {session_id}
- **Trigger**: {trigger}
- **Transcript**: {raw_dst.name}

## Extracted State

- **Last Issue**: #{extracted['last_issue'] or 'None'}
- **Last Phase**: {extracted['last_phase'] or 'None'}
- **Artifacts Created**: {', '.join(extracted['artifacts_created']) or 'None'}

## Pending Tasks
{chr(10).join(f'- [ ] {t}' for t in extracted['pending_tasks']) or '- None'}

## Files Modified
{chr(10).join(f'- {f}' for f in extracted['files_modified'][-10:]) or '- None'}

## Key Decisions
{chr(10).join(f'- {d}' for d in extracted['key_decisions']) or '- None'}
"""
    md_dst.write_text(summary, encoding="utf-8")

    # 4) Update PERSISTENT_STATE.yaml with extracted info
    try:
        update_persistent_state(project_dir, extracted)
        print("[precompact] Updated PERSISTENT_STATE.yaml")
    except Exception as e:
        print(f"[precompact] Skipped PERSISTENT_STATE.yaml update: {e}")

    # 5) Cleanup old checkpoints
    try:
        deleted = cleanup_old_checkpoints(out_dir, CHECKPOINT_RETENTION_DAYS)
        if deleted > 0:
            print(f"[precompact] Cleaned up {deleted} checkpoints older than {CHECKPOINT_RETENTION_DAYS} days")
    except Exception as e:
        logging.error(f"Failed to cleanup old checkpoints: {e}", exc_info=True)
        print(f"[precompact] Warning: Checkpoint cleanup failed: {e}", file=sys.stderr)

    # PreCompact stdout is not injected into context; it's mostly for verbose logs.
    print(f"[precompact] Checkpointed transcript -> {raw_dst}")
    print(f"[precompact] Wrote summary -> {md_dst}")
    print(f"[precompact] Extracted: issue={extracted['last_issue']}, phase={extracted['last_phase']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
