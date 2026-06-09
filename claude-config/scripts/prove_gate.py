"""PROVE verdict merge gate (issue #360).

PROVE emits rich verdict artifacts (status + ac_audit frontmatter) but until
this gate nothing ENFORCED them at ship time — a FAIL verdict was purely
diagnostic and `/ship` merged anyway. This script is the mechanical check
`/ship` runs before the merge step:

  python3 ~/.claude/scripts/prove_gate.py --issue 320 [--outputs-dir .agents/outputs]

Exit codes (stable contract for ship.md):
  0  GATE_PASS         PASS verdict + ac_audit clean — merge may proceed.
                       Also: issue was never orchestrate-tracked (no PROVE
                       expected — /quick and ad-hoc work is not falsely gated).
  2  GATE_FAIL         latest PROVE artifact says FAIL or BLOCKED.
  3  GATE_AC_VIOLATION status says PASS but ac_audit has missing/partial
                       entries (AC-FORBIDS-APPROVE, #1609/#1612) — the PASS
                       is downgraded, merge is blocked.
  4  GATE_NO_ARTIFACT  issue has orchestrate artifacts (map/plan/patch) but
                       no PROVE artifact — verification was skipped.
  5  GATE_PARSE_ERROR  artifact exists but frontmatter is unreadable.
                       Fail-CLOSED: an unverifiable verdict blocks the merge.

Override: `--override "<reason>"` records the bypass to
`<outputs-dir>/prove-overrides.jsonl` (who/when/why/what-the-gate-said) and
exits 0. The override is allowed but never silent — same philosophy as the
buddy chokepoint's bypassed=true telemetry (#1613).

AC-audit semantics are NOT reimplemented here: the gate imports
state_manager.validate_ac_audit so ship-time and record-time enforcement can
never drift.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# state_manager lives in the deployed hooks dir; fall back to the repo copy
# so the gate also works from a fresh checkout.
for _hooks in (Path.home() / ".claude" / "hooks",
               Path(__file__).resolve().parent.parent / "hooks"):
    if (_hooks / "state_manager.py").exists():
        sys.path.insert(0, str(_hooks))
        break

from state_manager import validate_ac_audit  # noqa: E402

GATE_PASS = 0
GATE_FAIL = 2
GATE_AC_VIOLATION = 3
GATE_NO_ARTIFACT = 4
GATE_PARSE_ERROR = 5

# Orchestrate phase artifacts that mark an issue as pipeline-tracked (and
# therefore REQUIRED to have a PROVE artifact before shipping).
TRACKED_PHASES = ("map", "map-plan", "plan", "patch", "contract", "test-plan")


class ArtifactParseError(Exception):
    """PROVE artifact exists but its frontmatter cannot be parsed."""


def _frontmatter(text: str) -> dict:
    """Parse the YAML frontmatter block of an artifact. Raises
    ArtifactParseError on any shape problem — the gate fails closed."""
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise ArtifactParseError("no frontmatter block found")
    try:
        import yaml
    except ImportError as exc:
        raise ArtifactParseError("PyYAML unavailable — cannot parse verdict") from exc
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ArtifactParseError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ArtifactParseError("frontmatter is not a mapping")
    return data


def latest_artifact(outputs_dir: Path, issue: int, phase: str = "prove") -> Path | None:
    candidates = sorted(
        outputs_dir.glob(f"{phase}-{issue}-*.md"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def is_orchestrate_tracked(outputs_dir: Path, issue: int) -> bool:
    return any(
        latest_artifact(outputs_dir, issue, phase) is not None
        for phase in TRACKED_PHASES
    )


def check_gate(outputs_dir: Path, issue: int) -> tuple[int, str]:
    """Pure decision: (exit_code, human-readable reason)."""
    artifact = latest_artifact(outputs_dir, issue)
    if artifact is None:
        if is_orchestrate_tracked(outputs_dir, issue):
            return GATE_NO_ARTIFACT, (
                f"issue #{issue} has orchestrate artifacts but NO PROVE artifact — "
                "verification was skipped. Run PROVE before shipping."
            )
        return GATE_PASS, (
            f"issue #{issue} is not orchestrate-tracked (no phase artifacts) — "
            "no PROVE verdict expected; gate passes."
        )

    try:
        fm = _frontmatter(artifact.read_text(encoding="utf-8"))
    except (OSError, ArtifactParseError) as exc:
        return GATE_PARSE_ERROR, (
            f"{artifact.name}: cannot read verdict ({exc}) — failing CLOSED."
        )

    status = str(fm.get("status", "")).upper()
    if status in ("FAIL", "BLOCKED"):
        return GATE_FAIL, f"{artifact.name}: status={status} — merge blocked."
    if status != "PASS":
        return GATE_PARSE_ERROR, (
            f"{artifact.name}: status={status or '(absent)'} is not "
            "PASS/FAIL/BLOCKED — failing CLOSED."
        )

    audit = validate_ac_audit(fm.get("ac_audit"))
    if audit.get("downgrade_to") == "FAIL":
        offenders = "; ".join(
            f"{m.get('status', '?')}: {str(m.get('ac', ''))[:80]}"
            for m in audit.get("missing", [])
        )
        return GATE_AC_VIOLATION, (
            f"{artifact.name}: status=PASS but ac_audit forbids approval "
            f"(AC-FORBIDS-APPROVE) — {offenders}"
        )

    return GATE_PASS, f"{artifact.name}: status=PASS, ac_audit clean — merge may proceed."


def record_override(outputs_dir: Path, issue: int, reason: str,
                    gate_code: int, gate_reason: str) -> Path:
    log = outputs_dir / "prove-overrides.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "issue": issue,
        "override_reason": reason,
        "gate_exit": gate_code,
        "gate_reason": gate_reason,
    }
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="prove_gate", description=__doc__.splitlines()[0])
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--outputs-dir", type=Path, default=Path(".agents/outputs"))
    ap.add_argument(
        "--override", metavar="REASON",
        help="bypass a blocking verdict; the bypass is recorded to "
             "prove-overrides.jsonl (never silent)",
    )
    args = ap.parse_args(argv)

    code, reason = check_gate(args.outputs_dir, args.issue)
    print(f"prove-gate: {reason}")
    if code != GATE_PASS and args.override:
        log = record_override(args.outputs_dir, args.issue, args.override, code, reason)
        print(f"prove-gate: OVERRIDDEN ({args.override!r}) — recorded to {log}")
        return GATE_PASS
    return code


if __name__ == "__main__":
    raise SystemExit(main())
