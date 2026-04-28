#!/usr/bin/env python3
"""
Score a regression-set run.

Usage:
    python3 score.py results/2026-04-28-baseline.md
    python3 score.py results/run-A.md results/run-B.md   # compare two runs

Result file format (Markdown with YAML frontmatter):

    ---
    run_name: baseline
    date: 2026-04-28
    config_version: <hash or label>
    ---

    # 001 enum-mismatch
    - critical_expected: 1
    - critical_caught: 1
    - warning_expected: 1
    - warning_caught: 1
    - false_positives: 0
    - false_positives_known: 0
    - reviewer_output_lines: 14

    # 002 clean-refactor
    - critical_expected: 0
    - critical_caught: 0
    - warning_expected: 0
    - warning_caught: 0
    - false_positives: 1
    - false_positives_known: 0
    - reviewer_output_lines: 8
    ...

The scorer aggregates per-run metrics: CRITICAL recall, WARNING recall,
average noise rate, average output length.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


KEY = re.compile(r"-\s*(\w+):\s*(\S+)")


def parse_results(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    cases = []
    current = None
    for line in text.splitlines():
        if line.startswith("# ") and not line.startswith("# Run"):
            if current:
                cases.append(current)
            current = {"name": line[2:].strip()}
            continue
        m = KEY.search(line)
        if m and current is not None:
            try:
                current[m.group(1)] = int(m.group(2))
            except ValueError:
                current[m.group(1)] = m.group(2)
    if current:
        cases.append(current)

    crit_e = sum(c.get("critical_expected", 0) for c in cases)
    crit_c = sum(c.get("critical_caught", 0) for c in cases)
    warn_e = sum(c.get("warning_expected", 0) for c in cases)
    warn_c = sum(c.get("warning_caught", 0) for c in cases)
    fp = sum(c.get("false_positives", 0) for c in cases)
    fpk = sum(c.get("false_positives_known", 0) for c in cases)
    out_lens = [c.get("reviewer_output_lines", 0) for c in cases if "reviewer_output_lines" in c]

    return {
        "path": str(path),
        "n_cases": len(cases),
        "critical_recall": crit_c / crit_e if crit_e else 1.0,
        "warning_recall": warn_c / warn_e if warn_e else 1.0,
        "noise_rate": (fp + fpk) / len(cases) if cases else 0.0,
        "avg_output_lines": sum(out_lens) / len(out_lens) if out_lens else 0,
        "totals": {
            "critical_expected": crit_e,
            "critical_caught": crit_c,
            "warning_expected": warn_e,
            "warning_caught": warn_c,
            "false_positives": fp,
            "false_positives_known": fpk,
        },
    }


def fmt(r: dict) -> str:
    return (
        f"  cases:           {r['n_cases']}\n"
        f"  CRITICAL recall: {r['critical_recall']:.1%} "
        f"({r['totals']['critical_caught']}/{r['totals']['critical_expected']})\n"
        f"  WARNING recall:  {r['warning_recall']:.1%} "
        f"({r['totals']['warning_caught']}/{r['totals']['warning_expected']})\n"
        f"  noise rate:      {r['noise_rate']:.2f} per case "
        f"(FP={r['totals']['false_positives']}, NP={r['totals']['false_positives_known']})\n"
        f"  avg output:      {r['avg_output_lines']:.0f} lines\n"
    )


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    runs = [parse_results(Path(p)) for p in sys.argv[1:]]
    for r in runs:
        print(f"{r['path']}")
        print(fmt(r))

    if len(runs) == 2:
        a, b = runs
        print("Delta (B − A):")
        print(f"  CRITICAL recall: {(b['critical_recall'] - a['critical_recall']) * 100:+.1f}pp")
        print(f"  WARNING recall:  {(b['warning_recall'] - a['warning_recall']) * 100:+.1f}pp")
        print(f"  noise rate:      {b['noise_rate'] - a['noise_rate']:+.2f} per case")
        print(f"  avg output:      {b['avg_output_lines'] - a['avg_output_lines']:+.0f} lines")
        regressed = (
            b["critical_recall"] < a["critical_recall"]
            or (b["warning_recall"] < a["warning_recall"] - 0.05 and b["noise_rate"] >= a["noise_rate"])
        )
        print()
        print("Verdict:", "REGRESSED — do not ship" if regressed else "OK to ship")

    return 0


if __name__ == "__main__":
    sys.exit(main())
