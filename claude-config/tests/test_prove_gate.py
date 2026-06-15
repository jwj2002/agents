"""Tests for the PROVE verdict merge gate (issue #360)."""

import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import prove_gate as G  # noqa: E402


def _artifact(
    tmp_path, name, status="PASS", ac_audit=None, raw=None, runtime_smoke="__default__"
):
    outputs = tmp_path / ".agents" / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    if raw is None:
        # runtime_smoke (#460):
        #   "__default__" → a valid n/a block (keeps pre-#460 PASS tests green).
        #   None          → emit NO runtime_smoke key (the absent case).
        #   dict          → render as a nested YAML block.
        #   str           → render as a scalar (#459 backward-compat form).
        if runtime_smoke == "__default__":
            smoke_lines = (
                "runtime_smoke:\n"
                "  status: n/a\n"
                "  command: \"\"\n"
                '  evidence: "test fixture — no runnable surface"\n'
            )
        elif runtime_smoke is None:
            smoke_lines = ""
        elif isinstance(runtime_smoke, dict):
            smoke_lines = "runtime_smoke:\n" + "".join(
                f"  {k}: \"{v}\"\n" for k, v in runtime_smoke.items()
            )
        else:
            smoke_lines = f'runtime_smoke: "{runtime_smoke}"\n'

        audit_lines = ""
        if ac_audit is not None:
            audit_lines = "ac_audit:\n" + "".join(
                f'  - ac: "{a["ac"]}"\n    status: {a["status"]}\n'
                f'    evidence: "{a.get("evidence", "x")}"\n'
                for a in ac_audit
            )
        raw = (
            f"---\nissue: 42\nagent: PROVE\nstatus: {status}\n"
            f"{smoke_lines}{audit_lines}---\n\n# body\n"
        )
    (outputs / name).write_text(raw, encoding="utf-8")
    return outputs


OK_AUDIT = [{"ac": "does the thing", "status": "implemented", "evidence": "file.py:1"}]


def test_pass_with_clean_audit(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT)
    code, reason = G.check_gate(outputs, 42)
    assert code == G.GATE_PASS
    assert "merge may proceed" in reason


def test_fail_blocks(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "FAIL", OK_AUDIT)
    code, reason = G.check_gate(outputs, 42)
    assert code == G.GATE_FAIL
    assert "blocked" in reason


def test_blocked_blocks(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "BLOCKED", OK_AUDIT)
    assert G.check_gate(outputs, 42)[0] == G.GATE_FAIL


def test_pass_with_partial_audit_is_violation(tmp_path):
    audit = OK_AUDIT + [{"ac": "second thing", "status": "partial", "evidence": "meh"}]
    outputs = _artifact(tmp_path, "prove-42-060926.md", "PASS", audit)
    code, reason = G.check_gate(outputs, 42)
    assert code == G.GATE_AC_VIOLATION
    assert "AC-FORBIDS-APPROVE" in reason


def test_pass_with_no_audit_is_violation(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "PASS", ac_audit=None)
    assert G.check_gate(outputs, 42)[0] == G.GATE_AC_VIOLATION


def test_no_artifact_but_tracked_blocks(tmp_path):
    outputs = _artifact(tmp_path, "map-plan-42-060926.md", raw="---\nissue: 42\n---\nbody\n")
    code, reason = G.check_gate(outputs, 42)
    assert code == G.GATE_NO_ARTIFACT
    assert "verification was skipped" in reason


def test_no_artifact_untracked_passes(tmp_path):
    outputs = tmp_path / ".agents" / "outputs"
    outputs.mkdir(parents=True)
    code, reason = G.check_gate(outputs, 42)
    assert code == G.GATE_PASS
    assert "not orchestrate-tracked" in reason


def test_unparseable_artifact_fails_closed(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", raw="no frontmatter here\n")
    assert G.check_gate(outputs, 42)[0] == G.GATE_PARSE_ERROR


def test_unknown_status_fails_closed(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "MAYBE", OK_AUDIT)
    assert G.check_gate(outputs, 42)[0] == G.GATE_PARSE_ERROR


def test_latest_artifact_wins(tmp_path):
    import os
    outputs = _artifact(tmp_path, "prove-42-060826.md", "FAIL", OK_AUDIT)
    _artifact(tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT)
    os.utime(outputs / "prove-42-060826.md", (1, 1))  # force older mtime
    assert G.check_gate(outputs, 42)[0] == G.GATE_PASS


def test_other_issues_artifacts_ignored(tmp_path):
    outputs = _artifact(tmp_path, "prove-99-060926.md", "FAIL", OK_AUDIT)
    code, _ = G.check_gate(outputs, 42)
    assert code == G.GATE_PASS  # issue 42 untracked; 99's FAIL is irrelevant


def test_override_records_and_passes(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "FAIL", OK_AUDIT)
    rc = G.main(["--issue", "42", "--outputs-dir", str(outputs),
                 "--override", "hotfix: prod down, verified manually"])
    assert rc == G.GATE_PASS
    rows = [json.loads(line) for line in
            (outputs / "prove-overrides.jsonl").read_text().splitlines()]
    assert rows[0]["issue"] == 42
    assert rows[0]["gate_exit"] == G.GATE_FAIL
    assert "hotfix" in rows[0]["override_reason"]


def test_override_not_recorded_when_gate_passes(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT)
    rc = G.main(["--issue", "42", "--outputs-dir", str(outputs),
                 "--override", "unnecessary"])
    assert rc == G.GATE_PASS
    assert not (outputs / "prove-overrides.jsonl").exists()


def test_cli_exit_codes(tmp_path):
    outputs = _artifact(tmp_path, "prove-42-060926.md", "FAIL", OK_AUDIT)
    assert G.main(["--issue", "42", "--outputs-dir", str(outputs)]) == G.GATE_FAIL


# ── runtime_smoke gate (issue #460) ─────────────────────────────────────────


def test_pass_with_smoke_pass_proceeds(tmp_path):
    smoke = {"status": "PASS", "command": "python -m m --help", "evidence": "exit 0"}
    outputs = _artifact(
        tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT, runtime_smoke=smoke
    )
    code, reason = G.check_gate(outputs, 42)
    assert code == G.GATE_PASS
    assert "merge may proceed" in reason


def test_pass_with_smoke_absent_is_violation(tmp_path):
    outputs = _artifact(
        tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT, runtime_smoke=None
    )
    code, reason = G.check_gate(outputs, 42)
    assert code == G.GATE_SMOKE_VIOLATION
    assert "re-run PROVE" in reason


def test_pass_with_smoke_fail_is_violation(tmp_path):
    smoke = {"status": "FAIL", "command": "x", "evidence": "crashed"}
    outputs = _artifact(
        tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT, runtime_smoke=smoke
    )
    assert G.check_gate(outputs, 42)[0] == G.GATE_SMOKE_VIOLATION


def test_pass_with_smoke_pass_no_command_is_violation(tmp_path):
    smoke = {"status": "PASS", "command": "", "evidence": "ran"}
    outputs = _artifact(
        tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT, runtime_smoke=smoke
    )
    assert G.check_gate(outputs, 42)[0] == G.GATE_SMOKE_VIOLATION


def test_pass_with_smoke_pass_no_evidence_is_violation(tmp_path):
    smoke = {"status": "PASS", "command": "x", "evidence": ""}
    outputs = _artifact(
        tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT, runtime_smoke=smoke
    )
    assert G.check_gate(outputs, 42)[0] == G.GATE_SMOKE_VIOLATION


def test_pass_with_smoke_na_proceeds(tmp_path):
    smoke = {"status": "n/a", "command": "", "evidence": "docs only"}
    outputs = _artifact(
        tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT, runtime_smoke=smoke
    )
    assert G.check_gate(outputs, 42)[0] == G.GATE_PASS


def test_pass_with_smoke_unknown_status_is_violation(tmp_path):
    smoke = {"status": "maybe", "command": "x", "evidence": "y"}
    outputs = _artifact(
        tmp_path, "prove-42-060926.md", "PASS", OK_AUDIT, runtime_smoke=smoke
    )
    assert G.check_gate(outputs, 42)[0] == G.GATE_SMOKE_VIOLATION


def test_pass_with_smoke_scalar_string_proceeds(tmp_path):
    outputs = _artifact(
        tmp_path,
        "prove-42-060926.md",
        "PASS",
        OK_AUDIT,
        runtime_smoke="n/a (no runnable surface)",
    )
    assert G.check_gate(outputs, 42)[0] == G.GATE_PASS
