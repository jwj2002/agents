#!/usr/bin/env python3
"""Retro-map free-text root_causes onto a coded taxonomy for /learn clustering.

READ-SIDE ONLY: classifies records for clustering/counting. It never mutates
telemetry — record_failure still writes raw free-text. A failure to classify is
SAFE: the row stays UNMAPPED (surfaced as signal), never force-bucketed. Worst
case is "not learned yet", never "learned wrong".

Discriminator: a `root_cause` with NO spaces is a code ONLY if it is in
`_VALID_ROOT_CAUSES` (so a typo'd code is surfaced as UNMAPPED, not a phantom
code). Free-text (has spaces, or unrecognized) goes through conservative keyword
rules; unmatched -> UNMAPPED. Non-string root_cause -> MALFORMED (surfaced, never
crashes). Empty/missing -> NO_ROOT_CAUSE.

Usage:
  map_freetext_root_causes.py <union.jsonl>            # cluster counts (Step 2)
  map_freetext_root_causes.py <union.jsonl> --mine CODE # detail/evidence in a cluster (Step 5)
  map_freetext_root_causes.py <union.jsonl> --json      # structured {code: [records]}
"""
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

# Recognized coded vocabulary. The canonical enum (claude-config/agents/_base.md
# §10) is authoritative; observed agent-emitted codes extend it. A spaceless token
# is treated as a code ONLY if it is a member here — so a typo ("VERIFICATON_GAP")
# or a lowercase word ("regression") falls through to UNMAPPED instead of becoming
# a phantom code. Extend deliberately (governance): a new code earns a slot when an
# UNMAPPED cluster recurs with a genuinely distinct prevention.
_VALID_ROOT_CAUSES = frozenset({
    # canonical (_base.md §10) — these MUST all be present or real clusters vanish
    "ENUM_VALUE", "COMPONENT_API", "MULTI_MODEL", "API_MISMATCH", "ACCESS_CONTROL",
    "MISSING_TEST", "SQLITE_COMPAT", "STRUCTURE_VIOLATION", "SCOPE_CREEP",
    "VERIFICATION_GAP", "OTHER",
    # mapped-from-free-text classes
    "AMBIGUITY_UNRESOLVED", "DOCUMENTATION",
    # observed agent-emitted extensions
    "LINT_ERROR", "STUB_HANDLERS", "ASYNCPG_POOL_VS_CONNECTION",
    "PIPECAT_PIPELINE_DEADLOCK", "OPENAI_STRICT_SCHEMA", "LLM_OUTPUT_SCHEMA",
    "SQL_RESERVED_WORD", "WRONG_TABLE_NAME", "INVALID_SQL_CONSTRUCT",
    "MISSING_SERVICE_WIRING", "WRONG_CONN_ID_SCOPE", "MISSING_INTERFACE_METHODS",
    "SEQUENTIAL_IO", "BLOCKING_FIRE_AND_FORGET", "PATH_EXPANSION",
    "SERVER_DEP_MANAGEMENT", "LEGACY_COMPOUND",
})

# Buckets that are signal/noise, never an apply-eligible learnable pattern.
_NON_PATTERN = frozenset({"UNMAPPED", "NO_ROOT_CAUSE", "MALFORMED"})

# Negation/no-verify variants, on normalized (lowercased, straight-apostrophe) text.
_DIDNT = r"(?:didn'?t|did not|doesn'?t|don'?t|without)"

# Conservative keyword rules on NORMALIZED text. Order matters (first match wins):
# AMBIGUITY before SCOPE so "didn't consider both interpretations" -> ambiguity, not
# scope. Known limitation: pure negation ("no assumption; explicit API mismatch") and
# compound failures ("only implemented X and didn't verify Y") are inherently
# multi-label — the conservative UNMAPPED default + the consensus-validation gate
# (see specs) bound the damage; semantic clustering is the deferred upgrade.
RULES = [
    ("AMBIGUITY_UNRESOLVED", [r"both interpretations", r"identified contradiction",
                              rf"{_DIDNT} pick", r"failed to resolve",
                              rf"{_DIDNT} call out"]),
    ("SCOPE_CREEP", [r"only implemented", r"missed implicit",
                     rf"{_DIDNT} consider\b.{{0,40}}(scenario|case|edge|deficit|type|path)",
                     r"secondary (deficit|scenario|type)"]),
    ("DOCUMENTATION", [rf"{_DIDNT} document", rf"{_DIDNT} specify",
                       r"missing docs?\b", r"forgot to document"]),
    ("VERIFICATION_GAP", [r"\bassum(?:e|ed|es|ing|ption)\b",
                          rf"{_DIDNT}\b.{{0,30}}(verif|validat|check)",
                          rf"{_DIDNT} add validation",
                          r"stated\b.{0,40}resolved", r"defensive comment without"]),
]


def _normalize(text):
    """NFKC + curly->straight apostrophe + lowercase, for robust regex matching."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    return t.lower()


def classify(root_cause):
    """Map a root_cause to a coded value, or a surfaced non-pattern bucket.

    None/missing/empty/"?" -> NO_ROOT_CAUSE; non-string -> MALFORMED (surfaced,
    never crashes); recognized spaceless token -> that code; free-text matching a
    rule -> the code; anything else -> UNMAPPED.
    """
    if root_cause is None:
        return "NO_ROOT_CAUSE"
    if not isinstance(root_cause, str):
        return "MALFORMED"          # non-string -> surfaced, never .strip()-crashes
    raw = root_cause.strip()
    if not raw or raw == "?":
        return "NO_ROOT_CAUSE"
    if " " not in raw and raw.upper() in _VALID_ROOT_CAUSES:
        return raw.upper()          # recognized code -> normalize, pass through
    low = _normalize(raw)
    for code, pats in RULES:
        if any(re.search(p, low) for p in pats):
            return code
    return "UNMAPPED"               # conservative default: never force-bucket


def cluster(path):
    """Return ({code: [record, ...]}, skipped_line_count). Records (not just the
    root_cause string) are retained so --mine/--json can surface `details` — the
    prevention evidence Step 5 needs."""
    clusters = defaultdict(list)
    skipped = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(r, dict):
                skipped += 1
                continue
            clusters[classify(r.get("root_cause"))].append(r)
    return clusters, skipped


def _evidence(record):
    """The specific prevention evidence for detail-mining: prefer `details`,
    fall back to the root_cause text."""
    detail = record.get("details")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    rc = record.get("root_cause")
    return rc.strip() if isinstance(rc, str) else ""


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = argv[0]
    if not os.path.exists(path):
        print(f"error: union file not found: {path}", file=sys.stderr)
        return 2
    clusters, skipped = cluster(path)
    if skipped:
        print(f"warning: skipped {skipped} malformed JSON line(s)", file=sys.stderr)

    # --mine takes precedence over --json (more specific).
    if "--mine" in argv:
        idx = argv.index("--mine")
        if idx + 1 >= len(argv):
            print("error: --mine requires a CODE argument", file=sys.stderr)
            return 2
        code = argv[idx + 1].upper()
        seen = set()
        for record in clusters.get(code, []):
            ev = _evidence(record)
            if ev and ev not in seen:
                seen.add(ev)
                print(ev)
        return 0

    if "--json" in argv:
        print(json.dumps({k: v for k, v in clusters.items()}, indent=2, default=str))
        return 0

    # Default: cluster counts; apply-eligibility flagged (>=5, excluding non-patterns).
    for code, recs in sorted(clusters.items(), key=lambda x: -len(x[1])):
        flag = "  <== APPLY-ELIGIBLE (>=5)" if len(recs) >= 5 and code not in _NON_PATTERN else ""
        print(f"{len(recs):4}  {code}{flag}")
    if clusters.get("MALFORMED"):
        print(f"warning: {len(clusters['MALFORMED'])} record(s) had a non-string "
              f"root_cause (MALFORMED) — telemetry corruption", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
