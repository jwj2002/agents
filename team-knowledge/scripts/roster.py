"""Roster + path-ownership validation for the Team Knowledge Hub (§5, §6).

Pure-logic module — no network, no side effects. Backs issue #238's acceptance tests.

The load-bearing rule (Codex F4/N3): the trust check for a change to a trust-bearing path keys on
the **platform-verified merge actor**, NEVER the forgeable git `author` field. This module makes
that explicit so the CI/branch-protection wiring (deferred to repo-admin) has a tested contract.
"""
from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a soft dep for file loading only
    yaml = None

REQUIRED_DEV_FIELDS = ("dev_id", "agent_name", "machine", "team_tag")

# audit/<dev>.jsonl  ->  <dev>  (dev_id chars: alnum, dash, underscore)
_AUDIT_PATH_RE = re.compile(r"(?:^|/)audit/(?P<dev>[A-Za-z0-9_-]+)\.jsonl$")


def load_roster(path) -> dict:
    """Load roster.yaml into a dict. Raises if PyYAML is unavailable."""
    if yaml is None:
        raise RuntimeError("PyYAML is required to load roster.yaml")
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def validate_roster(roster: dict) -> list:
    """Return a list of human-readable errors; an empty list means the roster is valid."""
    errors: list = []
    if roster.get("schema_version") != 1:
        errors.append(f"schema_version must be 1, got {roster.get('schema_version')!r}")
    devs = roster.get("devs")
    if not isinstance(devs, list) or not devs:
        errors.append("roster.devs must be a non-empty list")
        return errors
    seen: set = set()
    for i, dev in enumerate(devs):
        if not isinstance(dev, dict):
            errors.append(f"devs[{i}] is not a mapping")
            continue
        for field in REQUIRED_DEV_FIELDS:
            if not dev.get(field):
                errors.append(
                    f"devs[{i}] ({dev.get('dev_id', '?')}) missing required field {field!r}"
                )
        did = dev.get("dev_id")
        if did in seen:
            errors.append(f"duplicate dev_id {did!r}")
        seen.add(did)
    return errors


def roster_dev_ids(roster: dict) -> set:
    return {d.get("dev_id") for d in roster.get("devs", []) if isinstance(d, dict)}


def is_known_dev(roster: dict, dev_id: str) -> bool:
    return dev_id in roster_dev_ids(roster)


def classify_sender(roster: dict, dev_id: str) -> str:
    """'known' if dev_id is in the roster, else 'quarantine' (§5: unknown senders quarantined)."""
    return "known" if is_known_dev(roster, dev_id) else "quarantine"


def audit_path_owner(path: str):
    """dev_id that owns an audit shard: audit/<dev>.jsonl -> <dev>; None if not an audit path."""
    m = _AUDIT_PATH_RE.search(str(path).replace("\\", "/"))
    return m.group("dev") if m else None


def is_path_owned_by(path: str, dev_id: str) -> bool:
    return audit_path_owner(path) == dev_id


def verify_merge_actor(owner_dev: str, *, pr_actor: str, git_author=None) -> bool:
    """Trust check for a change to an owned path (Codex F4/N3).

    Returns True ONLY if the platform-verified merge actor equals ``owner_dev``. ``git_author`` is
    accepted but DELIBERATELY IGNORED for the decision — it is user-controlled text and exists in
    this signature only to document that ``pr_actor`` and ``git_author`` can differ (the
    forgeable-attribution trap). Never substitute ``git_author`` into the comparison.
    """
    return pr_actor == owner_dev


def catalog_entry_valid(entry: dict, approvals: dict) -> bool:
    """A catalog entry is importable only if its ``scan_audit`` row carries a protected-approval
    record (§6 / Codex F4). ``approvals`` maps a scan_audit ref -> approval record; a falsy/absent
    record means un-gated provenance, which is refused.
    """
    if not isinstance(entry, dict):
        return False
    ref = entry.get("scan_audit")
    if not ref:
        return False
    return bool(approvals.get(ref))
