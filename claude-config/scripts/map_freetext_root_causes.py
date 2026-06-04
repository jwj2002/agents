#!/usr/bin/env python3
"""Retro-map free-text root_causes onto a coded taxonomy for /learn clustering.

READ-SIDE ONLY: this classifies records for clustering/counting. It never
mutates telemetry — record_failure still writes raw free-text. A failure to
classify is SAFE: the row stays UNMAPPED (surfaced as signal), never
force-bucketed. Worst case is "not learned yet", never "learned wrong".

Discriminator: a `root_cause` with NO spaces is treated as already-coded
(passed through, upper-cased). A `root_cause` WITH spaces is free-text and is
matched against conservative keyword rules; an unmatched free-text row -> UNMAPPED.

Usage:
  map_freetext_root_causes.py <union.jsonl>            # cluster counts (Step 2)
  map_freetext_root_causes.py <union.jsonl> --mine CODE # detail texts in a cluster (Step 5)
  map_freetext_root_causes.py <union.jsonl> --json      # structured {code: [details]}
"""
import json
import re
import sys
from collections import defaultdict

# Frozen seed vocab — conservative keyword rules. Order matters: first match wins.
# Extend deliberately (decision 3 governance): a new code is minted only when an
# UNMAPPED cluster recurs with a genuinely distinct prevention.
RULES = [
    # Conservative: clear verify/validate/check signals only. Borderline rows
    # (e.g. "copied verbatim without understanding") deliberately fall through to
    # UNMAPPED rather than being force-mapped here — surfacing as signal is safer
    # than over-bucketing into VERIFICATION_GAP.
    ("VERIFICATION_GAP", [r"assum", r"without (verif|validat|check)", r"didn'?t verif",
                          r"didn'?t validate", r"didn'?t add validation", r"didn'?t check",
                          r"stated .*resolved", r"defensive comment without"]),
    ("SCOPE_CREEP", [r"only implemented", r"missed implicit", r"didn'?t consider",
                     r"secondary (deficit|scenario|type)"]),
    ("AMBIGUITY_UNRESOLVED", [r"both interpretations", r"identified contradiction",
                              r"didn'?t pick", r"failed to resolve", r"didn'?t call out"]),
    ("DOCUMENTATION", [r"didn'?t document", r"didn'?t specify"]),
]

_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]+$")  # no spaces => already coded


def classify(root_cause):
    """Map a root_cause string to a coded value, or 'UNMAPPED' (fail-safe)."""
    if not root_cause or not root_cause.strip() or root_cause.strip() == "?":
        return "UNMAPPED"
    rc = root_cause.strip()
    if _TOKEN_RE.match(rc):          # already a code (any case) -> normalize, pass through
        return rc.upper()
    low = rc.lower()
    for code, pats in RULES:
        if any(re.search(p, low) for p in pats):
            return code
    return "UNMAPPED"                # conservative default: never force-bucket


def cluster(path):
    """Return {code: [original_root_cause, ...]} from a union JSONL file."""
    clusters = defaultdict(list)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rc = r.get("root_cause", "?")
            clusters[classify(rc)].append(rc)
    return clusters


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    path = argv[0]
    clusters = cluster(path)
    if "--json" in argv:
        print(json.dumps({k: v for k, v in clusters.items()}, indent=2))
        return 0
    if "--mine" in argv:
        code = argv[argv.index("--mine") + 1]
        # Detail-mining: the specific (deduped) preventions inside a coded cluster.
        for detail in sorted(set(clusters.get(code.upper(), []))):
            print(detail)
        return 0
    # Default: cluster counts, apply-eligibility flagged (>=5, excluding UNMAPPED).
    for code, members in sorted(clusters.items(), key=lambda x: -len(x[1])):
        flag = "  <== APPLY-ELIGIBLE (>=5)" if len(members) >= 5 and code != "UNMAPPED" else ""
        print(f"{len(members):4}  {code}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
