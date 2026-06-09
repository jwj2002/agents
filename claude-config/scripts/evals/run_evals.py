"""Executable-evals runner (issue #361).

Usage (from any project repo):
  python3 ~/agents/claude-config/scripts/evals/run_evals.py \
      [--diff-range origin/main...HEAD] [--repo .] [--evals E01,E15] [--all]

Selects applicable evals per rules/eval-file-mapping.md from the changed
files, runs them, prints a report, exits 1 on findings / 0 clean / 2 on
operational error (cannot read the diff). PROVE runs this FIRST, then does
the prose evals (E02/E03/E05–E12) on top — this is the mechanical floor,
not the whole check.

Allowlist: a line containing `eval-ok: <ID>` is skipped by that eval.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import (  # noqa: E402
    e01_enum_value,
    e04_model_migration,
    e13_fk_index,
    e14_docker_user,
    e15_secrets,
)
from evals.common import ChangeSet, DiffError, changeset_from_git  # noqa: E402

EVALS = {
    "E01": e01_enum_value.run,
    "E04": e04_model_migration.run,
    "E13": e13_fk_index.run,
    "E14": e14_docker_user.run,
    "E15": e15_secrets.run,
}

# Applicability per rules/eval-file-mapping.md (subset that is automated).
_FRONTEND_RE = re.compile(r"\.(jsx?|tsx?|vue|svelte)$")
_MODEL_RE = re.compile(r"(^|/)models?(/|\.py$)")
_DOCKER_RE = re.compile(r"(^|/)(Dockerfile[^/]*|.*\.dockerfile)$", re.IGNORECASE)


def applicable(cs: ChangeSet) -> list[str]:
    ids = {"E15"}  # catch-all, always
    for p in cs.paths:
        if _FRONTEND_RE.search(p):
            ids.add("E01")
        if _MODEL_RE.search(p) and p.endswith(".py"):
            ids.update(("E04", "E13"))
        elif p.endswith(".py"):
            ids.add("E13")
        if _DOCKER_RE.search(p):
            ids.add("E14")
    return sorted(ids)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_evals", description=__doc__.splitlines()[0])
    ap.add_argument("--diff-range", default="origin/main...HEAD")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--evals", help="comma-separated subset (e.g. E01,E15)")
    ap.add_argument("--all", action="store_true",
                    help="run every automated eval regardless of file mapping")
    args = ap.parse_args(argv)

    try:
        cs = changeset_from_git(args.repo.resolve(), args.diff_range)
    except DiffError as exc:
        print(f"evals: ERROR — {exc}", file=sys.stderr)
        return 2

    if not cs.paths:
        print(f"evals: no changed files in {args.diff_range} — nothing to check")
        return 0

    if args.evals:
        ids = [e.strip().upper() for e in args.evals.split(",") if e.strip()]
        unknown = [e for e in ids if e not in EVALS]
        if unknown:
            print(f"evals: unknown eval id(s): {', '.join(unknown)} "
                  f"(automated: {', '.join(EVALS)})", file=sys.stderr)
            return 2
    elif args.all:
        ids = sorted(EVALS)
    else:
        ids = applicable(cs)

    print(f"evals: {len(cs.paths)} changed file(s); running {', '.join(ids)}")
    findings = []
    for eval_id in ids:
        findings.extend(EVALS[eval_id](cs))

    if not findings:
        print("evals: CLEAN — no mechanical findings "
              "(prose evals E02/E03/E05–E12 still apply)")
        return 0
    print(f"evals: {len(findings)} finding(s):")
    for f in findings:
        print(f"  {f.render()}")
    print("evals: fix the findings, or allowlist a false positive with "
          "`eval-ok: <ID>` + a reason comment.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
