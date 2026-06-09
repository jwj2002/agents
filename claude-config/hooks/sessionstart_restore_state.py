#!/usr/bin/env python3
"""
Claude Code SessionStart hook (Optimized v2):
- Loads compact YAML state (~300 tokens vs ~650)
- Loads critical patterns only (~200 tokens vs ~2600)
- Detects active orchestrate workflow and provides continue instructions
- Total: ~500 tokens vs ~3250 (85% reduction)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# File-based error logging
_log_file = Path.home() / ".claude" / "hooks.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)


def _rotate_log_if_oversize(max_bytes: int = 10 * 1024 * 1024) -> None:
    """Rotate hooks.log if it exceeds max_bytes (default 10 MB).

    Keeps one rotated copy at hooks.log.1; older copies are discarded.
    Runs once per session via SessionStart so the cost is negligible.
    """
    try:
        if not _log_file.exists() or _log_file.stat().st_size <= max_bytes:
            return
        rotated = _log_file.with_suffix(_log_file.suffix + ".1")
        if rotated.exists():
            rotated.unlink()
        _log_file.rename(rotated)
    except Exception:
        # Never let log rotation break session startup.
        pass


_rotate_log_if_oversize()

logging.basicConfig(
    filename=str(_log_file),
    level=logging.WARNING,
    format="%(asctime)s [sessionstart] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Try to import centralized state manager
try:
    from state_manager import get_active_work as _sm_get_active_work
    HAS_STATE_MANAGER = True
except ImportError:
    HAS_STATE_MANAGER = False


def get_active_work(yaml_content: str) -> dict:
    """Extract active_work from YAML content (fallback when state_manager unavailable)."""
    if not HAS_YAML:
        return {}
    try:
        data = yaml.safe_load(yaml_content)
        return data.get("active_work", {}) if data else {}
    except Exception as e:
        logging.warning(f"Failed to parse YAML state: {e}", exc_info=True)
        return {}


# ---------------------------------------------------------------- auto-recall

# Injection budget (#365): keep the whole section ~1–1.5k tokens so sessions
# don't bloat. Chars ≈ 4 × tokens.
AUTORECALL_TOTAL_CHARS = 6000
AUTORECALL_PER_FACT_CHARS = 1200
_TYPE_PRIORITY = {"feedback": 0, "user": 1, "reference": 2, "project": 3}


def _fact_meta(path: Path) -> dict | None:
    """Parse name/type/expires/body from a fact file. None on unreadable.

    Minimal line-based frontmatter parse — works without PyYAML and tolerates
    the nested `metadata:`/flat variants in the wild.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta = {"name": path.stem, "type": "project", "expires": None, "body": text}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                stripped = line.strip()
                for key in ("type", "expires", "name"):
                    if stripped.startswith(f"{key}:"):
                        meta[key] = stripped.split(":", 1)[1].strip().strip("'\"") or meta[key]
            meta["body"] = text[end + 4:].lstrip("-").lstrip("\n")
    return meta


def _expired(expires: str | None, today: str) -> bool:
    return bool(expires) and str(expires)[:10] < today


def render_project_memory(fact_dir: Path, *, today: str | None = None) -> str:
    """Build the auto-recalled Project Memory section (empty string if none).

    Selection: non-expired facts ranked by type priority (feedback > user >
    reference > project) then mtime (newest first), injected until the char
    budget runs out. Remaining facts are listed as topics with the recall CTA.
    """
    from datetime import date
    today = today or date.today().isoformat()

    paths = [p for p in sorted(fact_dir.glob("*.md")) if p.name != "MEMORY.md"]
    facts = []
    for p in paths:
        meta = _fact_meta(p)
        if meta is None or _expired(meta["expires"], today):
            continue
        meta["path"] = p
        facts.append(meta)
    if not facts:
        return ""

    facts.sort(key=lambda f: (_TYPE_PRIORITY.get(f["type"], 9),
                              -f["path"].stat().st_mtime))
    injected, leftover, used = [], [], 0
    for f in facts:
        body = f["body"].strip()
        if len(body) > AUTORECALL_PER_FACT_CHARS:
            body = (body[:AUTORECALL_PER_FACT_CHARS]
                    + f"\n… *(truncated — full fact: `{f['path']}`)*")
        cost = len(body) + len(f["name"]) + 40
        if used + cost > AUTORECALL_TOTAL_CHARS:
            leftover.append(f)
            continue
        injected.append((f, body))
        used += cost

    lines = ["### Project Memory (auto-recalled)\n"]
    lines.append(
        f"{len(injected)} of {len(facts)} fact bodies injected "
        "(highest-value first, budget-capped). Verify against current code "
        "before acting — facts reflect what was true when written.\n"
    )
    for f, body in injected:
        lines.append(f"**{f['name']}** ({f['type']}):\n{body}\n")
    if leftover:
        topics = ", ".join(f["name"].replace("_", " ").replace("-", " ")
                           for f in leftover[:8])
        lines.append(
            f"Not injected ({len(leftover)}): {topics}. "
            "→ `~/agents/bin/memory recall <topic>` to pull these.\n"
        )

    _log_autorecall(fact_dir, len(injected), len(facts), used)
    return "\n".join(lines)


def _log_autorecall(fact_dir: Path, injected: int, total: int, chars: int) -> None:
    """Append an auto-injection record so memory_audit_metrics can report
    auto-recall separately from manual recall. Best-effort."""
    try:
        from datetime import datetime, timezone
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "project": fact_dir.parent.name,
            "facts_injected": injected,
            "facts_total": total,
            "chars": chars,
        }
        log = Path.home() / ".claude" / "memory-autoinject.jsonl"
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        logging.warning("autorecall metrics append failed", exc_info=True)


def main() -> int:
    _hook_in = json.load(sys.stdin)

    # 0. Pull latest agent shards (fail-open — divergence warns but does not abort session).
    _agents_root = Path.home() / "agents"
    if _agents_root.is_dir():
        try:
            _pull = subprocess.run(
                ["git", "-C", str(_agents_root), "pull", "--ff-only", "--quiet"],
                capture_output=True,
                timeout=10,
            )
            if _pull.returncode != 0:
                logging.warning(
                    "git pull --ff-only failed on agents repo — shards may be stale. "
                    "Resolve with: git -C ~/agents pull --ff-only"
                )
                print(
                    "**Advisory**: agents repo diverged from origin — "
                    "run `git -C ~/agents pull --ff-only` to sync latest shards.\n"
                )
            else:
                # Pull succeeded — check whether the telemetry gate is tripped.
                _gate_script = _agents_root / "claude-config" / "scripts" / "telemetry_gate.py"
                if _gate_script.exists():
                    try:
                        _gate = subprocess.run(
                            ["python3", str(_gate_script), "--verbose"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if _gate.returncode == 0:  # gate tripped
                            _gate_msg = _gate.stdout.strip() or "gate tripped"
                            print(f"**Advisory**: /learn gate tripped — {_gate_msg}\n")
                    except Exception as _gate_exc:
                        logging.warning(f"telemetry_gate check failed (non-fatal): {_gate_exc}")
        except (subprocess.TimeoutExpired, OSError, Exception) as _pull_exc:
            logging.warning(f"git pull --ff-only failed (non-fatal): {_pull_exc}")

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    global_claude_dir = Path.home() / ".claude"
    checkpoints_dir = project_dir / ".agents" / "outputs" / "claude_checkpoints"
    project_memory_dir = project_dir / ".claude" / "memory"
    global_memory_dir = global_claude_dir / "memory"

    print("## Restored Context\n")

    # 1. Load compact YAML state (preferred) or fallback to markdown
    yaml_state = checkpoints_dir / "PERSISTENT_STATE.yaml"
    md_state = checkpoints_dir / "PERSISTENT_STATE.md"

    active_work = {}
    if yaml_state.exists():
        yaml_content = yaml_state.read_text(encoding="utf-8")
        if HAS_STATE_MANAGER:
            active_work = _sm_get_active_work(project_dir)
        else:
            active_work = get_active_work(yaml_content)
        print("### Project State\n")
        print("```yaml")
        print(yaml_content)
        print("```\n")
    elif md_state.exists():
        print("### Project State\n")
        print(md_state.read_text(encoding="utf-8"))
        print()

    # 2. Load critical patterns (project-specific first, then global fallback)
    patterns_critical = project_memory_dir / "patterns-critical.md"
    if not patterns_critical.exists():
        patterns_critical = global_memory_dir / "patterns-critical.md"

    if patterns_critical.exists():
        print("### Critical Patterns (Always Apply)\n")
        print(patterns_critical.read_text(encoding="utf-8"))
        print()
    else:
        # Fallback: try reading rules/core-patterns.md (canonical source)
        core_patterns = global_claude_dir / "rules" / "core-patterns.md"
        if core_patterns.exists():
            print("### Critical Patterns (Always Apply)\n")
            print(core_patterns.read_text(encoding="utf-8"))
            print()
        else:
            # Last resort: minimal inline reminder
            print("### Critical Patterns\n")
            print("1. **VERIFICATION_GAP**: Read spec/code before assuming")
            print("2. **ENUM_VALUE**: Use VALUES not Python names (CO-OWNER not CO_OWNER)")
            print("3. **COMPONENT_API**: Read PropTypes before using components")
            print()
            print("Full patterns: `~/.claude/rules/core-patterns.md`\n")

    # 3. Check for active orchestrate workflow and provide continue instructions
    issue = active_work.get("issue")
    phase = active_work.get("phase")
    branch = active_work.get("branch")

    if issue and phase:
        print("### ACTIVE ORCHESTRATE WORKFLOW\n")
        print(f"**Issue**: #{issue}")
        print(f"**Phase**: {phase}")
        print(f"**Branch**: {branch}")
        print()
        print("**CRITICAL**: You were in the middle of an orchestrate workflow.")
        print("Continue with the current phase using the Task tool:")
        print()
        print("1. Read `.claude/commands/orchestrate.md` for phase instructions")
        print("2. Check for existing artifacts in `.agents/outputs/`")
        print(f"3. Continue the `{phase}` phase for issue #{issue}")
        print()
        print("If the phase was completed, proceed to the next phase in the workflow.")
        print()

    # 3.5 Project-memory auto-recall (#365). The CTA-only approach measured
    #     0.9% adoption (13 recalls / 328 sessions) — facts were written and
    #     never read. Inject the high-value fact BODIES directly, within a
    #     hard budget, instead of asking the session to go fetch them. Facts
    #     live under ~/.claude/projects/<encoded-cwd>/memory/.
    encoded = str(project_dir).replace("/", "-")
    fact_dir = Path.home() / ".claude" / "projects" / encoded / "memory"
    if fact_dir.is_dir():
        section = render_project_memory(fact_dir)
        if section:
            print(section)

    # 4. Hint about full patterns location — only if the file actually exists.
    #    patterns-full.md is produced by `/learn`; advertising it before that
    #    first run sends readers to a missing file (the audit's "dangling ref").
    if (project_memory_dir / "patterns-full.md").exists() or (
        global_memory_dir / "patterns-full.md"
    ).exists():
        print("---")
        print("*Full patterns available at `.claude/memory/patterns-full.md` if needed.*\n")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
