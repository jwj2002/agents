"""Read inbox via Microsoft Graph using app-only auth.

Reads credentials from ~/.claude/m365/agent.json:
    {"tenant_id": ..., "client_id": ..., "client_secret": ..., "sender_upn": ...}

The same app/credentials cover both send (send_mail.py) and read; the
ApplicationAccessPolicy scopes the app to a single mailbox, so this
script can only read sender_upn's inbox.

Usage:
    python3 read_mail.py                            # 10 most recent inbox messages
    python3 read_mail.py --top 25
    python3 read_mail.py --from someone@example.com
    python3 read_mail.py --subject-contains "digest"
    python3 read_mail.py --since 2026-05-04
    python3 read_mail.py --unread-only
    python3 read_mail.py --json                     # raw JSON output for piping
    python3 read_mail.py --folder sentItems         # default: inbox
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import msal
import requests


CREDS_PATH = Path.home() / ".claude" / "m365" / "agent.json"
CACHE_PATH = Path.home() / ".claude" / "m365" / "token-cache.bin"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class ReadMailError(Exception):
    """Bubble up a single-line error to stderr."""


def load_creds() -> dict:
    if not CREDS_PATH.exists():
        raise ReadMailError(
            f"Missing credentials at {CREDS_PATH}. Drop the JSON with "
            "tenant_id / client_id / client_secret / sender_upn fields "
            "and chmod 600. See ~/.claude/CLAUDE.md for the M365 section."
        )
    if (CREDS_PATH.stat().st_mode & 0o077) != 0:
        raise ReadMailError(
            f"{CREDS_PATH} has loose permissions; run `chmod 600 {CREDS_PATH}`."
        )
    with CREDS_PATH.open() as f:
        creds = json.load(f)
    required = {"tenant_id", "client_id", "client_secret", "sender_upn"}
    missing = required - creds.keys()
    if missing:
        raise ReadMailError(f"{CREDS_PATH} missing fields: {sorted(missing)}")
    return creds


def get_token(creds: dict) -> str:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text())
    app = msal.ConfidentialClientApplication(
        client_id=creds["client_id"],
        client_credential=creds["client_secret"],
        authority=f"https://login.microsoftonline.com/{creds['tenant_id']}",
        token_cache=cache,
    )
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        raise ReadMailError(
            f"Token acquisition failed: {result.get('error_description', result)}"
        )
    if cache.has_state_changed:
        CACHE_PATH.write_text(cache.serialize())
        os.chmod(CACHE_PATH, 0o600)
    return result["access_token"]


def build_filter(args: argparse.Namespace) -> str | None:
    """Compose the OData $filter expression from CLI flags."""
    parts: list[str] = []
    if args.from_addr:
        parts.append(
            f"from/emailAddress/address eq '{args.from_addr.replace(chr(39), chr(39)*2)}'"
        )
    if args.unread_only:
        parts.append("isRead eq false")
    if args.since:
        # Accept YYYY-MM-DD or full ISO. Graph wants ISO 8601 UTC.
        s = args.since
        if len(s) == 10:
            s = f"{s}T00:00:00Z"
        parts.append(f"receivedDateTime ge {s}")
    return " and ".join(parts) if parts else None


def list_messages(
    *,
    sender_upn: str,
    token: str,
    folder: str,
    top: int,
    odata_filter: str | None,
    select_fields: list[str],
) -> list[dict]:
    base = f"https://graph.microsoft.com/v1.0/users/{sender_upn}/mailFolders/{folder}/messages"
    params = {
        "$top": str(top),
        "$select": ",".join(select_fields),
        "$orderby": "receivedDateTime desc",
    }
    if odata_filter:
        params["$filter"] = odata_filter
    qs = "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())
    url = f"{base}?{qs}"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        raise ReadMailError(f"Graph returned {response.status_code}: {response.text}")
    return response.json().get("value", [])


def filter_subject(messages: list[dict], needle: str | None) -> list[dict]:
    """Subject substring filter applied client-side (Graph $search uses different semantics)."""
    if not needle:
        return messages
    n = needle.lower()
    return [m for m in messages if n in (m.get("subject") or "").lower()]


def render_pretty(messages: list[dict]) -> str:
    if not messages:
        return "(no matching messages)"
    lines = []
    for m in messages:
        ts = m.get("receivedDateTime", "")[:16].replace("T", " ")
        sender = (m.get("from") or {}).get("emailAddress", {}).get("address", "?")
        unread = " [UNREAD]" if not m.get("isRead", True) else ""
        subject = m.get("subject", "(no subject)")
        preview = (m.get("bodyPreview") or "").strip().replace("\n", " ")[:80]
        lines.append(f"{ts}  {sender:<40}{unread}")
        lines.append(f"            {subject}")
        if preview:
            lines.append(f"            {preview}")
        lines.append("")
    return "\n".join(lines).rstrip()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top", type=int, default=10, help="Max messages (default: 10)")
    p.add_argument("--from", dest="from_addr", help="Filter to a specific sender address")
    p.add_argument("--subject-contains", help="Substring match on subject (case-insensitive)")
    p.add_argument("--since", help="ISO date or full timestamp (YYYY-MM-DD or 2026-05-04T08:00:00Z)")
    p.add_argument("--unread-only", action="store_true")
    p.add_argument(
        "--folder",
        default="inbox",
        help="Mail folder name (default: inbox; e.g. sentItems, drafts)",
    )
    p.add_argument("--json", dest="as_json", action="store_true", help="Emit raw JSON")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        creds = load_creds()
        token = get_token(creds)
        odata_filter = build_filter(args)
        # Pull a wider window when we'll do client-side subject filtering, so
        # results stay meaningful even when the in-window subject matches are
        # past the first N rows.
        fetch_top = args.top * 5 if args.subject_contains else args.top
        fetch_top = min(fetch_top, 200)
        messages = list_messages(
            sender_upn=creds["sender_upn"],
            token=token,
            folder=args.folder,
            top=fetch_top,
            odata_filter=odata_filter,
            select_fields=["id", "subject", "from", "receivedDateTime", "bodyPreview", "isRead"],
        )
        messages = filter_subject(messages, args.subject_contains)
        messages = messages[: args.top]
    except ReadMailError as e:
        print(f"read_mail: {e}", file=sys.stderr)
        return 1

    if args.as_json:
        json.dump(messages, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(render_pretty(messages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
