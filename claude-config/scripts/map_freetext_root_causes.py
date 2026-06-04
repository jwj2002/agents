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

# Recognized coded vocabulary (seed). A spaceless token is treated as a code
# ONLY if it is a known member here — otherwise it falls through to UNMAPPED.
# This enforces the spec's typo-guard (a typo'd code like "VERIFICATON_GAP" is
# NOT in the set, so it surfaces as UNMAPPED instead of becoming a phantom code)
# and blocks lowercase single words ("regression") from being promoted to fake
# codes. Extend deliberately (decision-3 governance): a new code earns a slot
# here only when an UNMAPPED cluster recurs with a genuinely distinct prevention.
_VALID_ROOT_CAUSES = frozenset({
    # mapped-from-free-text classes
    "VERIFICATION_GAP", "SCOPE_CREEP", "AMBIGUITY_UNRESOLVED", "DOCUMENTATION",
    # agent-emitted codes observed in telemetry
    "ENUM_VALUE", "COMPONENT_API", "MISSING_TEST", "LINT_ERROR", "MULTI_MODEL",
    "STUB_HANDLERS", "ASYNCPG_POOL_VS_CONNECTION", "PIPECAT_PIPELINE_DEADLOCK",
    "OPENAI_STRICT_SCHEMA", "LLM_OUTPUT_SCHEMA", "SQL_RESERVED_WORD",
    "WRONG_TABLE_NAME", "INVALID_SQL_CONSTRUCT", "MISSING_SERVICE_WIRING",
    "WRONG_CONN_ID_SCOPE", "MISSING_INTERFACE_METHODS", "SEQUENTIAL_IO",
    "BLOCKING_FIRE_AND_FORGET", "PATH_EXPANSION", "SERVER_DEP_MANAGEMENT",
    "STRUCTURE_VIOLATION", "LEGACY_COMPOUND",
})


def classify(root_cause):
    """Map a root_cause string to a coded value, NO_ROOT_CAUSE, or UNMAPPED.

    - empty / missing / "?"          -> NO_ROOT_CAUSE  (recording noise, not signal)
    - spaceless KNOWN-vocab token    -> that code      (case-normalized pass-through)
    - free-text matching a rule      -> the matched code
    - anything else (incl. unknown spaceless tokens / typo'd codes) -> UNMAPPED
      (surfaced for governance; never force-bucketed)
    """
    if not root_cause or not root_cause.strip() or root_cause.strip() == "?":
        return "NO_ROOT_CAUSE"
    rc = root_cause.strip()
    if " " not in rc and rc.upper() in _VALID_ROOT_CAUSES:
        return rc.upper()            # recognized code -> normalize, pass through
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
