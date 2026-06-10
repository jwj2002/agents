#!/usr/bin/env python3
"""
Enforce context budgets (issue #384).

Two budgets, both measured in lines:

  1. CLAUDE.md         — the always-loaded system-prompt orientation file.
  2. Always-load rules — the sum of every rules/*.md that loads on EVERY
     session. A rule is always-load when its frontmatter `paths:` is
     exactly `["**"]`, OR when it has no `paths:` key at all (per
     validate-paths-globs.py: "no paths frontmatter == all sessions").

Scoped rules (a narrow `paths:` glob list) are NOT counted toward the
always-load sum — they only load when a matching file is in context.

Exit 0 with a per-check summary on pass; exit 1 with a GitHub-Actions
`::error::` annotation per breach. Defaults: CLAUDE.md <=200, rules <=450.

Run: python3 claude-config/scripts/check-context-budgets.py
     [--claude-budget N] [--rules-budget N]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)


DEFAULT_CLAUDE_BUDGET = 200
DEFAULT_RULES_BUDGET = 450

REPO = Path(__file__).resolve().parent.parent  # claude-config/
CLAUDE_MD = REPO / "CLAUDE.md"
RULES_DIR = REPO / "rules"


def parse_frontmatter(path: Path) -> dict | None:
    """Return the YAML frontmatter dict, or None if there is no frontmatter.

    Mirrors validate-paths-globs.py so the two checkers agree on what
    counts as a rule's frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    fm_text = text[4:end]
    try:
        return yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        return {"_error": str(e)}


def is_always_load(path: Path) -> bool:
    """True when this rule loads on EVERY session.

    Always-load == no frontmatter, no `paths:` key, or `paths == ["**"]`.
    A malformed-frontmatter file is treated as always-load (conservative:
    it would load until fixed) — validate-paths-globs.py flags it as an
    issue separately.
    """
    fm = parse_frontmatter(path)
    if fm is None:
        return True
    if "_error" in fm:
        return True
    paths = fm.get("paths")
    if paths is None:
        return True
    return paths == ["**"]


def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def check(
    claude_md: Path,
    rules_dir: Path,
    claude_budget: int,
    rules_budget: int,
) -> int:
    breaches = 0

    # Check 1 — CLAUDE.md.
    if not claude_md.is_file():
        print(f"::error::{claude_md} not found", file=sys.stderr)
        breaches += 1
    else:
        claude_lines = count_lines(claude_md)
        if claude_lines > claude_budget:
            print(
                f"::error::{claude_md.name} {claude_lines} lines "
                f"exceeds budget {claude_budget}"
            )
            breaches += 1
        else:
            print(f"OK: {claude_md.name} {claude_lines}/{claude_budget} lines")

    # Check 2 — always-load rules sum.
    if not rules_dir.is_dir():
        print(f"::error::rules dir not found at {rules_dir}", file=sys.stderr)
        breaches += 1
    else:
        always_total = 0
        counted: list[tuple[str, int]] = []
        for rule in sorted(rules_dir.glob("*.md")):
            if is_always_load(rule):
                n = count_lines(rule)
                always_total += n
                counted.append((rule.name, n))
        if always_total > rules_budget:
            print(
                f"::error::always-load rules total {always_total} lines "
                f"exceeds budget {rules_budget}"
            )
            for name, n in counted:
                print(f"    {name}: {n}")
            breaches += 1
        else:
            print(
                f"OK: always-load rules {always_total}/{rules_budget} lines "
                f"across {len(counted)} files"
            )

    return 1 if breaches else 0


def _run_hook(script: Path, seed_memory: Path | None, stdin_text: str | None, timeout: int = 5) -> int:
    """Run a hook script with a fresh temp HOME, capturing stdout bytes.

    Returns the number of bytes written to stdout. On timeout or subprocess
    error, falls back to returning the byte size of the script file itself.
    The temp HOME is always cleaned up before returning.

    Args:
        script: Absolute path to the hook script.
        seed_memory: Optional directory whose contents are copied into
            tmp/.claude/memory/ before the hook runs. Use this to seed the
            patterns files so the hook exercises its real injection paths.
        stdin_text: If not None, fed to the hook's stdin as UTF-8 bytes.
        timeout: Maximum seconds to wait for the subprocess (default 5).
    """
    tmp_home = tempfile.mkdtemp(prefix="cbp_")
    try:
        if seed_memory is not None and seed_memory.is_dir():
            dest = Path(tmp_home) / ".claude" / "memory"
            dest.mkdir(parents=True, exist_ok=True)
            for src_file in seed_memory.iterdir():
                if src_file.is_file():
                    shutil.copy2(src_file, dest / src_file.name)

        env = {"HOME": tmp_home, "PATH": "/usr/bin:/bin:/usr/local/bin"}
        stdin_bytes = stdin_text.encode() if stdin_text is not None else None
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(script.parent),
            env=env,
            input=stdin_bytes,
            capture_output=True,
            timeout=timeout,
        )
        return len(result.stdout)
    except subprocess.TimeoutExpired:
        return script.stat().st_size
    except OSError:
        return script.stat().st_size
    finally:
        shutil.rmtree(tmp_home, ignore_errors=True)


def payload_report(repo: Path) -> None:
    """Print a table of hook-injected context payload sizes (bytes + ~tokens).

    Always exits 0 (report-only — never enforces). The four sources measured:
      1. SessionStart hook output — run with seeded memory, stdin='{}'
      2. load_learning_rules output — run with seeded memory, no stdin
      3. memory/patterns-critical.md — direct file byte size
      4. memory/patterns-full.md    — direct file byte size (0 if absent)

    Args:
        repo: Path to the claude-config/ directory (REPO constant in normal use).
    """
    hooks_dir = repo / "hooks"
    memory_dir = repo / "memory"

    sessionstart = hooks_dir / "sessionstart_restore_state.py"
    load_rules = hooks_dir / "load_learning_rules.py"
    patterns_critical = memory_dir / "patterns-critical.md"
    patterns_full = memory_dir / "patterns-full.md"

    # Seed memory dir is the repo's memory/ directory.
    seed = memory_dir if memory_dir.is_dir() else None

    sources: list[tuple[str, int]] = []

    # 1. SessionStart hook output (stdin='{}' required — hook calls json.load(stdin)).
    if sessionstart.is_file():
        size = _run_hook(sessionstart, seed_memory=seed, stdin_text="{}")
    else:
        size = 0
    sources.append(("sessionstart hook output", size))

    # 2. load_learning_rules hook output (no stdin).
    if load_rules.is_file():
        size = _run_hook(load_rules, seed_memory=seed, stdin_text=None)
    else:
        size = 0
    sources.append(("load_learning_rules hook output", size))

    # 3. patterns-critical.md — always injected by sessionstart.
    if patterns_critical.is_file():
        size = patterns_critical.stat().st_size
    else:
        size = 0
    sources.append(("memory/patterns-critical.md", size))

    # 4. patterns-full.md — injected when present.
    if patterns_full.is_file():
        size = patterns_full.stat().st_size
    else:
        size = 0
    sources.append(("memory/patterns-full.md", size))

    total_bytes = sum(b for _, b in sources)
    total_tokens = total_bytes // 4

    col_w = max(len(label) for label, _ in sources)
    header = f"{'Source':<{col_w}}  {'Bytes':>8}  {'~Tokens':>8}"
    sep = "-" * len(header)
    print("Payload report (hook-injected context sources):")
    print(sep)
    print(header)
    print(sep)
    for label, b in sources:
        print(f"{label:<{col_w}}  {b:>8}  {b // 4:>8}")
    print(sep)
    print(f"{'TOTAL':<{col_w}}  {total_bytes:>8}  {total_tokens:>8}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce context budgets (#384)")
    parser.add_argument("--claude-budget", type=int, default=DEFAULT_CLAUDE_BUDGET)
    parser.add_argument("--rules-budget", type=int, default=DEFAULT_RULES_BUDGET)
    parser.add_argument(
        "--claude-md", type=Path, default=CLAUDE_MD, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--rules-dir", type=Path, default=RULES_DIR, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--payload-report",
        action="store_true",
        help="Print hook-payload byte/token report (report only, never fails)",
    )
    args = parser.parse_args(argv)
    if args.payload_report:
        payload_report(REPO)
        return 0
    return check(args.claude_md, args.rules_dir, args.claude_budget, args.rules_budget)


if __name__ == "__main__":
    sys.exit(main())
