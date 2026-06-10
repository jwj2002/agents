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
import re
import subprocess
import sys
from datetime import date, datetime, timezone
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


# ---------------------------------------------------------------- safety-filter


class BodyClassificationError(Exception):
    """Internal: classification logic failed (caught immediately, never propagates)."""


class InjectionSkipLogError(Exception):
    """Internal: skip-log write failed (caught immediately, never propagates)."""


_SUPPRESSED_BODY = "[body suppressed — safety filter]"

# Secret-shaped patterns — any match suppresses the body.
# The key=value branch (last alternative) captures the value portion in group 1
# so the whitelist guard can inspect it without re-running the full pattern.
# Note: re.IGNORECASE applied globally to cover the key=value branch.
#
# The sk- alternative allows up to 3 short hyphenated prefix segments
# (sk-ant-api03-…, sk-proj-…) before a HIGH-ENTROPY run of 12+ alnum chars.
# Two guards stop ordinary hyphenated words (entertask-project-pointer,
# task-project, EnterTask-Code-Review-2026-05-12) from matching: (1) the \b
# anchor — in those words "sk" sits mid-token with no word boundary before it;
# (2) the 12-char entropy floor on the final run — those words have no 12+ char
# alnum segment. The floor is 12 (not 16) to keep real-shaped short keys like
# sk-ant-abc1234567890 (13-char run) suppressed; 16 would let them slip through.
_SECRET_RE = re.compile(
    r"""
    \bsk-(?:[A-Za-z0-9]+-){0,3}[A-Za-z0-9_]{12,}\b  # OpenAI/Anthropic sk- keys (hyphenated prefixes; _ allowed in base64url tails)
    | \bgithub_pat_[A-Za-z0-9_]{20,}   # GitHub fine-grained PATs
    | \bgh[pousr]_[A-Za-z0-9]{10,}     # GitHub tokens (ghp_/gho_/ghu_/ghs_/ghr_)
    | \bglpat-[A-Za-z0-9]{5,}          # GitLab PATs
    | \bxox[bpoas]-[A-Za-z0-9\-]{10,}  # Slack tokens
    | \bAKIA[A-Z0-9]{16}\b             # AWS access key IDs ([A-Z0-9]{16} per AWS spec)
    | \beyJ[A-Za-z0-9_\-]{10,}         # JWT header prefix
    | -----BEGIN\ (?:RSA\ |EC\ |OPENSSH\ )?PRIVATE\ KEY-----  # PEM private keys
    | (?:password|secret|api_key)\s*[:=]\s*([^\s\$\{`][^\s]{4,})  # key=value credentials
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Pointer-style value guard. A value portion (captured group 1 of the key=value
# pattern) is exempt ONLY when it is unambiguously a pointer/placeholder, not a
# smuggled literal credential (FIX C). The simple prefix list below covers the
# shapes that carry no inline value:
#   $FOO / ${FOO}   -- shell/template expansion
#   `...`           -- code-span literal (markdown)
#   from ...        -- prose pointer ("from $ENV", "from the vault")
_WHITELIST_PREFIX_RE = re.compile(r"^\s*(?:\$|\$\{|`|from )")

# An env: pointer is only a pointer when it names an env var in UPPER_SNAKE
# convention (env:DB_PASSWORD). env:hunter2supersecret is a smuggled literal.
_ENV_POINTER_RE = re.compile(r"^\s*env:[A-Z_][A-Z0-9_]*\s*$")

# A <...> placeholder is only exempt when the inner content looks like a real
# placeholder: no whitespace, no embedded secret shape, and no long unbroken
# alphanumeric run (which would look like a credential rather than a label).
_ANGLE_PLACEHOLDER_RE = re.compile(r"^\s*<([^>]*)>\s*$")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9]{16,}")


def _is_whitelisted_value(value: str) -> bool:
    """True when a captured key=value value portion is a pointer/placeholder.

    Tightened (FIX C): `env:` and `<...>` no longer blanket-exempt. `env:` must
    name an UPPER_SNAKE env var; `<...>` must be a placeholder with no embedded
    secret, no whitespace, and no long unbroken token. Anything else falls
    through to the literal-credential branch and is suppressed.
    """
    if _WHITELIST_PREFIX_RE.match(value):
        return True
    if _ENV_POINTER_RE.match(value):
        return True
    m = _ANGLE_PLACEHOLDER_RE.match(value)
    if m:
        inner = m.group(1)
        if (
            inner
            and not _SECRET_RE.search(inner)
            and not re.search(r"\s", inner)
            and not _LONG_TOKEN_RE.search(inner)
        ):
            return True
    return False


# Instruction-injection patterns (case-insensitive applied globally).
_INJECTION_RE = re.compile(
    r"""
    ignore\s+(?:all\s+)?(?:prior|previous|above|earlier)\s+(?:instructions?|context)
    | you\s+are\s+now\s+(?:a\s+)?\w+(?:\s+\w+){2,}(?:$|\.)
    | disregard\s+(?:all\s+)?(?:prior|previous|above|earlier)\s+(?:instructions?|context)
    | system\s*prompt\s*:
    | \[INST\]|\[\/INST\]|<\|im_start\|>
    """,
    re.VERBOSE | re.MULTILINE | re.IGNORECASE,
)


def _scrub_secrets(text: str) -> str:
    """Replace every secret-shaped match in `text` with a redacted token.

    FIX A: redaction is UNCONDITIONAL — it does not depend on how the body was
    classified. Any excerpt that leaves this module (log records AND rendered
    output) must pass through here so a secret embedded inside an
    injection-classified or error excerpt can never be written verbatim. Each
    match is replaced by its first 3 chars + "***" (token prefix preserved for
    triage, credential body removed). Whitelisted pointer values are left intact
    so harmless pointers in an excerpt are not mangled.
    """
    if not text:
        return text

    def _repl(m: "re.Match[str]") -> str:
        value_capture = m.group(1) if m.lastindex else None
        if value_capture is not None and _is_whitelisted_value(value_capture):
            return m.group(0)
        matched = m.group(0)
        return matched[:3] + "***"

    try:
        return _SECRET_RE.sub(_repl, text)
    except Exception:  # noqa: BLE001 — fail-closed on redaction: never emit raw
        # If substitution somehow fails, drop the excerpt entirely rather than
        # risk leaking it.
        return "[redacted — safety filter]"


def _scan_secret_line(line: str) -> str | None:
    """Return a redactable excerpt if a single line contains a literal secret.

    The whitelist guard exempts ONLY a pointer-style key=value match on THIS
    line. Because every key=value match is re-checked here per line, scanning
    continues past a whitelisted match in the body (see _classify_body): a
    whitelisted pointer on one line never grants the rest of the body a pass.
    """
    for m in _SECRET_RE.finditer(line):
        value_capture = m.group(1) if m.lastindex else None
        if value_capture is not None and _is_whitelisted_value(value_capture):
            # Pointer-style reference on this match — not a literal credential.
            # Keep scanning later matches on the same line.
            continue
        return m.group(0)[:60]
    return None


def _classify_body(body: str) -> tuple[str, str | None]:
    """Classify a fact body (or fact name) for injection safety.

    Returns:
        ("ok", None)              -- safe to inject verbatim
        ("secret", excerpt)       -- secret-shaped pattern found
        ("injection", excerpt)    -- instruction-injection phrase found

    Never raises. On internal error returns ("ok", None) (fail-open) and the
    caller is expected to emit a `classify_error` diagnostic via the boolean
    returned by _classify_body_raised — kept simple here by logging directly.
    """
    try:  # noqa: BLE001 — fail-open surface: classification errors must never crash SessionStart
        # Check injection patterns first (no whitelist needed).
        m = _INJECTION_RE.search(body)
        if m:
            return ("injection", m.group(0)[:60])

        # Scan for secrets line-by-line so a whitelisted pointer on one line
        # never short-circuits scanning of the remaining lines (BLOCKING 2).
        for line in body.splitlines() or [body]:
            excerpt = _scan_secret_line(line)
            if excerpt is not None:
                return ("secret", excerpt)

        return ("ok", None)
    except Exception:  # noqa: BLE001 — fail-open: swallow all errors, log nothing sensitive
        # Signal the failure with a sentinel verdict so the caller can emit a
        # classify_error diagnostic. "error" is treated as fail-open (inject).
        return ("error", None)


def _log_injection_skip(
    fact_name: str,
    reason: str,
    excerpt: str,
    project: str,
) -> None:
    """Append a skip record to memory-autoinject.jsonl. Best-effort.

    NEVER writes a raw secret. FIX A: the excerpt is scrubbed UNCONDITIONALLY
    (regardless of `reason`) so a secret embedded inside an injection or error
    excerpt is also redacted before it is written.
    """
    try:  # noqa: BLE001 — fail-open: logging errors must never crash SessionStart
        # Scrub every secret-shaped match out of the excerpt, no matter the
        # classification reason — an injection-classified excerpt can still
        # contain a credential.
        safe_excerpt = _scrub_secrets(excerpt) if excerpt else excerpt

        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "injection_skip",
            "project": project,
            "fact": fact_name,
            "reason": reason,
            "excerpt": safe_excerpt,
        }
        log = Path.home() / ".claude" / "memory-autoinject.jsonl"
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 — fail-open: do not let log write crash the hook
        logging.warning("injection_skip log append failed", exc_info=True)


def _log_classify_error(fact_name: str, project: str) -> None:
    """Append a `classify_error` diagnostic to memory-autoinject.jsonl.

    Emitted when the classifier hit its exception path (fail-open). NEVER
    includes the body or any secret — only the (possibly redacted) fact name.
    """
    try:  # noqa: BLE001 — fail-open: logging errors must never crash SessionStart
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "classify_error",
            "project": project,
            "fact": fact_name,
        }
        log = Path.home() / ".claude" / "memory-autoinject.jsonl"
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 — fail-open: do not let log write crash the hook
        logging.warning("classify_error log append failed", exc_info=True)


def _redact_secret_name(name: str) -> str:
    """Redact a fact name that itself classifies as secret/injection (BLOCKING 3).

    Returns a safe placeholder that never echoes the raw name. Pure function;
    never raises (fail-open via _classify_body's internal try/except).
    """
    verdict, _ = _classify_body(name)
    if verdict in ("secret", "injection"):
        return "[name redacted — safety filter]"
    return name


# ---------------------------------------------------------------- active-work


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
AUTORECALL_SUMMARY_CHARS = 200
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
    meta = {
        "name": path.stem,
        "type": "project",
        "expires": None,
        "summary": "",
        "durability": "",
        "body": text,
    }
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                stripped = line.strip()
                for key in ("type", "expires", "name", "summary", "durability"):
                    if stripped.startswith(f"{key}:"):
                        meta[key] = (
                            stripped.split(":", 1)[1].strip().strip("'\"") or meta[key]
                        )
            meta["body"] = text[end + 4 :].lstrip("-").lstrip("\n")
    return meta


def _extract_summary(
    meta: dict, body: str, *, max_chars: int = AUTORECALL_SUMMARY_CHARS
) -> str:
    """Derive a ≤max_chars summary for a fact.

    Uses ``meta["summary"]`` if set; otherwise falls back to the first
    non-header, non-list, non-empty sentence in the body. Always passes the
    candidate through ``_classify_body`` — a suppressed body never leaks via
    its summary. Fail-open: any exception returns a short safe default.
    """
    try:
        candidate = meta.get("summary", "").strip()
        if not candidate:
            # Fallback: first non-header, non-list, non-empty sentence.
            for raw_line in body.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith(("#", "-", "*", ">")):
                    continue
                # Split on ". " to get first sentence.
                candidate = line.split(". ")[0].rstrip(".")
                break
        candidate = candidate[:max_chars]
        # Safety: a suppressed body must not leak via its summary.
        # "error" is fail-open (classifier failed internally) — treat as safe.
        verdict, _ = _classify_body(candidate)
        if verdict in ("secret", "injection"):
            return _SUPPRESSED_BODY
        return candidate
    except Exception:  # noqa: BLE001 — fail-open: summary error must not crash hook
        return ""


def _rank_score(f: dict, today_str: str) -> float:
    """Compute a sort key for fact ``f``; lower score = injected first.

    Formula (all components non-negative except durability bonus):
        base_priority     = _TYPE_PRIORITY.get(type, 9)          # 0..9
        freshness_penalty = clamp((days - 30) / 30, 0, 2)        # 0 at <30d, +2 at >90d
        size_penalty      = clamp((body_size - 1200) / 1200, 0, 1.5)  # project type only
        durability_bonus  = -1.0 if durable else 0.0
    """
    try:
        ftype = f.get("type", "project")
        base = float(_TYPE_PRIORITY.get(ftype, 9))

        # Freshness penalty: 0 for facts touched ≤30d ago, up to +2 at 90d+.
        try:
            mtime = f["path"].stat().st_mtime
        except OSError:
            mtime = 0.0
        try:
            today_date = date.fromisoformat(today_str)
        except ValueError:
            today_date = date.today()
        days = (today_date - date.fromtimestamp(mtime)).days
        freshness = max(0.0, min(2.0, (days - 30) / 30.0))

        # session/temporary facts get an extra staleness multiplier.
        durability = f.get("durability", "")
        if durability in ("session", "temporary"):
            freshness *= 1.5

        # Size penalty: only for project-type facts (they are the over-represented class).
        if ftype == "project":
            body_size = len(f.get("body", "").strip())
            size_penalty = max(
                0.0,
                min(
                    1.5,
                    (body_size - AUTORECALL_PER_FACT_CHARS)
                    / float(AUTORECALL_PER_FACT_CHARS),
                ),
            )
        else:
            size_penalty = 0.0

        # Durability bonus: durable facts resist size/freshness penalties.
        dur_bonus = -1.0 if durability == "durable" else 0.0

        return base + freshness + size_penalty + dur_bonus
    except Exception:  # noqa: BLE001 — fail-open: ranking error must not crash hook
        return float(_TYPE_PRIORITY.get(f.get("type", "project"), 9))


def _expired(expires: str | None, today: str) -> bool:
    return bool(expires) and str(expires)[:10] < today


def render_project_memory(fact_dir: Path, *, today: str | None = None) -> str:
    """Build the auto-recalled Project Memory section (empty string if none).

    Two-pass injection (#430):
      Pass 1 — inject a summary line for every selected fact (budget: first half).
      Pass 2 — inject full bodies for top-N eligible facts (remaining budget).
    Total budget: AUTORECALL_TOTAL_CHARS (6000 chars, unchanged from #365).
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

    # Rank by _rank_score (lower = better); use path.name as deterministic tiebreaker.
    facts.sort(key=lambda f: (_rank_score(f, today), f["path"].name))

    project = fact_dir.parent.name

    # ---- Pass 1: summary injection ----
    # Budget slice for summaries: up to half the total budget so full bodies
    # can always fill the second half.
    summary_budget = AUTORECALL_TOTAL_CHARS // 2
    summary_used = 0
    summary_entries = []  # (safe_name, ftype, summary_text, fact_dict, verdict)
    leftover = []

    for f in facts:
        try:
            safe_name = _redact_secret_name(f["name"])
        except Exception:  # noqa: BLE001 — fail-open: redaction must not crash hook
            safe_name = f["name"]

        # Derive summary — safety-filtered inside _extract_summary.
        summary = _extract_summary(f, f["body"].strip())

        # Summary line cost.
        cost = len(summary) + len(safe_name) + 30
        if summary_used + cost > summary_budget:
            leftover.append(f)
            continue

        # Also classify the raw body for the body-pass safety check.
        try:
            verdict, excerpt = _classify_body(f["body"].strip())
        except Exception:  # noqa: BLE001 — fail-open: filter errors must not crash hook
            verdict, excerpt = "error", None

        if verdict == "error":
            _log_classify_error(safe_name, project)
        elif verdict != "ok":
            _log_injection_skip(safe_name, verdict, excerpt or "", project)
            # Suppressed body must not leak via its summary (PLAN: fail-safe).
            summary = _SUPPRESSED_BODY

        summary_entries.append((safe_name, f["type"], summary, f, verdict))
        summary_used += cost

    # ---- Pass 2: full-body injection ----
    body_budget = AUTORECALL_TOTAL_CHARS - summary_used
    body_used = 0
    body_entries = []  # (safe_name, ftype, body_text)

    for safe_name, ftype, _summary, f, verdict in summary_entries:
        # session/temporary facts are summary-only by declaration.
        if f.get("durability", "") in ("session", "temporary"):
            continue
        # Suppressed bodies are not injected.
        if verdict not in ("ok", "error"):
            continue

        body = f["body"].strip()
        if len(body) > AUTORECALL_PER_FACT_CHARS:
            body = (
                body[:AUTORECALL_PER_FACT_CHARS]
                + f"\n… *(truncated — full fact: `{f['path']}`)*"
            )

        cost = len(body) + len(safe_name) + 20
        if body_used + cost > body_budget:
            continue
        body_entries.append((safe_name, ftype, body))
        body_used += cost

    # Count only body-pass (non-suppressed) facts for the metrics record.
    real_injected = len(body_entries)

    # ---- Render ----
    lines = ["### Project Memory (auto-recalled)\n"]
    n_summaries = len(summary_entries)
    n_bodies = len(body_entries)
    lines.append(
        f"{n_summaries} summaries injected ({n_bodies} of {n_summaries} with full body). "
        "Verify against current code before acting — facts reflect what was true when written.\n"
    )

    # Summary section.
    for safe_name, ftype, summary, _f, _verdict in summary_entries:
        lines.append(f"**{safe_name}** ({ftype}): {summary}")

    # Full-body section (omitted when empty).
    if body_entries:
        lines.append(f"\n#### Full bodies (top-{n_bodies})\n")
        for safe_name, ftype, body in body_entries:
            lines.append(f"**{safe_name}** ({ftype}):\n{body}\n")

    if leftover:
        topics = ", ".join(
            _redact_secret_name(f["name"]).replace("_", " ").replace("-", " ")
            for f in leftover[:8]
        )
        lines.append(
            f"\nNot injected ({len(leftover)}): {topics}. "
            "→ `~/agents/bin/memory recall <topic>` to pull these.\n"
        )

    total_used = summary_used + body_used
    _log_autorecall(fact_dir, real_injected, len(facts), total_used)
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


def _maybe_pull_agents(
    agents_root: Path,
    stamp_path: Path,
    today_str: str,
    git_fn=None,
) -> bool:
    """Pull the agents repo at most once per calendar day (UTC).

    Stamp file: stamp_path stores the last-pull date via mtime.
    Written only on successful pull so failures are retried next session.
    Returns True if a pull was attempted, False if skipped (already pulled today).
    Fail-open: any exception is logged but never propagates.
    """
    if git_fn is None:

        def git_fn():
            return subprocess.run(
                ["git", "-C", str(agents_root), "pull", "--ff-only", "--quiet"],
                capture_output=True,
                timeout=10,
            )

    # Skip if already pulled today.
    if stamp_path.exists():
        stamp_date = (
            datetime.fromtimestamp(stamp_path.stat().st_mtime, tz=timezone.utc)
            .date()
            .isoformat()
        )
        if stamp_date == today_str:
            return False  # already pulled today

    try:
        result = git_fn()
        if result.returncode != 0:
            logging.warning(
                "git pull --ff-only failed on agents repo — config may be behind origin. "
                "Resolve with: git -C ~/agents pull --ff-only"
            )
            print(
                "**Advisory**: agents repo diverged from origin — "
                "run `git -C ~/agents pull --ff-only` to sync latest config.\n"
            )
            # Do NOT write stamp: next session should retry.
        else:
            # Pull succeeded — write/touch stamp.
            stamp_path.parent.mkdir(parents=True, exist_ok=True)
            stamp_path.touch()

            # Check whether the telemetry gate is tripped.
            _gate_script = (
                agents_root / "claude-config" / "scripts" / "telemetry_gate.py"
            )
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
                    logging.warning(
                        f"telemetry_gate check failed (non-fatal): {_gate_exc}"
                    )
    except (subprocess.TimeoutExpired, OSError, Exception) as _pull_exc:
        logging.warning(f"git pull --ff-only failed (non-fatal): {_pull_exc}")

    return True


def main() -> int:
    _hook_in = json.load(sys.stdin)

    # 0. Pull latest agents config at most once per day (stamp-guarded, fail-open).
    _agents_root = Path.home() / "agents"
    _stamp_path = Path.home() / ".claude" / ".agents-pull-stamp"
    _today_str = date.today().isoformat()
    if _agents_root.is_dir():
        _maybe_pull_agents(_agents_root, _stamp_path, _today_str)

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
            print(
                "2. **ENUM_VALUE**: Use VALUES not Python names (CO-OWNER not CO_OWNER)"
            )
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
        print(
            "*Full patterns available at `.claude/memory/patterns-full.md` if needed.*\n"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
