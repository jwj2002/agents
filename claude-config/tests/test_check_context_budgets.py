"""Tests for the context-budget checker (issue #384).

The script lives in claude-config/scripts/; import it the same way
test_prove_gate.py imports prove_gate.
"""

import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import importlib  # noqa: E402

cb = importlib.import_module("check-context-budgets")


def _write(path: Path, n_lines: int, frontmatter: str | None = None) -> None:
    """Write a file with exactly n_lines lines (frontmatter counts toward n)."""
    parts: list[str] = []
    if frontmatter is not None:
        parts.append(frontmatter.rstrip("\n"))
    remaining = n_lines - len(("\n".join(parts)).splitlines() if parts else [])
    parts.extend(f"line {i}" for i in range(remaining))
    text = "\n".join(parts) + "\n"
    path.write_text(text, encoding="utf-8")
    # Sanity: splitlines() is what the checker counts.
    assert len(path.read_text().splitlines()) == n_lines


def _rule(path: Path, n_lines: int, paths_value: str | None = "missing") -> None:
    """Create a rule file. paths_value:
    - "missing" → no paths key (always-load)
    - None      → no frontmatter at all (always-load)
    - a literal → e.g. '["**"]' (always-load) or '["**/specs/**"]' (scoped)
    """
    if paths_value is None:
        fm = None
    elif paths_value == "missing":
        fm = "---\ndescription: x\n---"
    else:
        fm = f"---\npaths: {paths_value}\n---"
    _write(path, n_lines, fm)


def _run(tmp_path, claude_lines=150, rules=None, claude_budget=200, rules_budget=450):
    claude_md = tmp_path / "CLAUDE.md"
    _write(claude_md, claude_lines)
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    for i, (n, paths_value) in enumerate(rules or []):
        _rule(rules_dir / f"rule{i}.md", n, paths_value)
    return cb.check(claude_md, rules_dir, claude_budget, rules_budget)


def test_under_budget(tmp_path):
    # CLAUDE.md 150, one always-load rule of 400 → under both budgets.
    assert _run(tmp_path, claude_lines=150, rules=[(400, '["**"]')]) == 0


def test_over_claude(tmp_path):
    assert _run(tmp_path, claude_lines=201, rules=[(100, '["**"]')]) == 1


def test_over_rules(tmp_path):
    # Two always-load rules summing to 451 → over the 450 rules budget.
    assert (
        _run(tmp_path, claude_lines=150, rules=[(300, '["**"]'), (151, '["**"]')]) == 1
    )


def test_exact_boundary_claude(tmp_path):
    # Exactly 200 lines is inclusive → pass.
    assert _run(tmp_path, claude_lines=200, rules=[(100, '["**"]')]) == 0


def test_exact_boundary_rules(tmp_path):
    # Always-load sum exactly 450 is inclusive → pass.
    assert (
        _run(tmp_path, claude_lines=150, rules=[(250, '["**"]'), (200, '["**"]')]) == 0
    )


def test_scoped_rule_excluded(tmp_path):
    # A scoped rule (narrow glob) does NOT count toward the always-load sum.
    # 400 always-load + 600 scoped → sum is 400, under budget.
    rules = [(400, '["**"]'), (600, '["**/specs/**"]')]
    assert _run(tmp_path, claude_lines=150, rules=rules) == 0


def test_no_frontmatter_counts_as_always_load(tmp_path):
    # A rule with NO frontmatter is always-load (matches validate-paths-globs).
    # 451 with no frontmatter → over budget.
    assert _run(tmp_path, claude_lines=150, rules=[(451, None)]) == 1


def test_no_paths_key_counts_as_always_load(tmp_path):
    # Frontmatter present but no `paths:` key → always-load.
    assert _run(tmp_path, claude_lines=150, rules=[(451, "missing")]) == 1


def test_real_tree_passes(tmp_path):
    # The actual repo tree must pass at the production budgets — the gate
    # proves itself (design constraint).
    assert cb.main([]) == 0


# ---------------------------------------------------------------------------
# payload_report() tests (issue #409)
# ---------------------------------------------------------------------------


def _make_memory(tmp_path: Path, critical_bytes: int = 50, full_bytes: int | None = 80) -> Path:
    """Create a fake memory/ dir with controlled file sizes.

    Returns the memory directory path. If full_bytes is None, patterns-full.md
    is omitted entirely to test the missing-file path.
    """
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "patterns-critical.md").write_bytes(b"x" * critical_bytes)
    if full_bytes is not None:
        (mem / "patterns-full.md").write_bytes(b"x" * full_bytes)
    return mem


def test_payload_report_no_hooks_no_memory(tmp_path, capsys):
    # Empty repo dir — no hooks/, no memory/. Should complete without raising.
    cb.payload_report(tmp_path)
    out = capsys.readouterr().out
    # Report header always printed.
    assert "Payload report" in out
    assert "TOTAL" in out


def test_payload_report_measures_memory_files(tmp_path, capsys):
    # Memory files present — their byte sizes must appear in the output.
    _make_memory(tmp_path, critical_bytes=50, full_bytes=80)
    cb.payload_report(tmp_path)
    out = capsys.readouterr().out
    assert "patterns-critical.md" in out
    assert "patterns-full.md" in out
    # The exact sizes appear somewhere in the output.
    assert "50" in out
    assert "80" in out


def test_payload_report_token_estimate(tmp_path, capsys):
    # Token estimate (~bytes//4) must be present in output.
    _make_memory(tmp_path, critical_bytes=400, full_bytes=400)
    cb.payload_report(tmp_path)
    out = capsys.readouterr().out
    # 400 bytes → 100 tokens; verify the token column header and a value.
    assert "Tokens" in out or "tokens" in out
    assert "100" in out


def test_payload_report_missing_patterns_full(tmp_path, capsys):
    # Only patterns-critical.md present — patterns-full.md absent.
    # Report must run cleanly and show 0 for patterns-full.
    _make_memory(tmp_path, critical_bytes=50, full_bytes=None)
    cb.payload_report(tmp_path)
    out = capsys.readouterr().out
    assert "patterns-full.md" in out
    # patterns-full row shows 0 bytes.
    lines = [ln for ln in out.splitlines() if "patterns-full" in ln]
    assert lines, "patterns-full.md row missing from output"
    assert "0" in lines[0]


def test_payload_report_never_raises(tmp_path):
    # Even with a completely empty dir, payload_report must not raise.
    try:
        cb.payload_report(tmp_path)
    except Exception as exc:
        raise AssertionError(f"payload_report raised unexpectedly: {exc}") from exc


def test_payload_report_exits_0_via_main(tmp_path):
    # --payload-report flag always returns 0 from main().
    assert cb.main(["--payload-report"]) == 0
