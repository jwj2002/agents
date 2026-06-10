#!/usr/bin/env python3
"""Read/write VitalAILabs client documents on SharePoint via Microsoft Graph.

App-only (client credentials) auth — the SAME app registration used for mail
(see send_mail.py). Reads credentials from ~/.claude/m365/agent.json:
    {"tenant_id": ..., "client_id": ..., "client_secret": ..., "sender_upn": ...}

Access is structurally confined to ONE site (SITE_ID below); the app's
Sites.Selected grant only covers that site, and this helper never accepts a
site argument, so an agent cannot wander to other company SharePoint sites.

This capability is gated by the machine-local credential file: it works on any
machine where ~/.claude/m365/agent.json exists (this work laptop, and any other
work machine where the file is dropped + chmod 600) and is inert everywhere
else. The site id and folder layout are not secrets; the credential never
leaves the machine.

Usage:
    python3 sharepoint.py list-clients
    python3 sharepoint.py list "Broken Top Club"
    python3 sharepoint.py list "Broken Top Club" "Transcripts"
    python3 sharepoint.py read "Broken Top Club/Transcripts/kickoff.txt"
    python3 sharepoint.py read "Broken Top Club/Legal Docs/nda.pdf" --out ./nda.pdf
    python3 sharepoint.py write "Broken Top Club/Product Requirement Docs/prd.md" --file ./prd.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

import msal
import requests

# The one site this helper is allowed to touch (VItalAILabs). Hardcoded on
# purpose: the app's Sites.Selected grant is scoped to this site, and refusing
# a site argument keeps the agent confined to client documents.
SITE_ID = (
    "vtmgroup.sharepoint.com,"
    "31a916e3-c46d-488c-aa22-ddc828ce2375,"
    "a237ae52-7be8-4a71-b4b5-43bf98183439"
)
GRAPH_ROOT = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]

CREDS_PATH = Path.home() / ".claude" / "m365" / "agent.json"
CACHE_PATH = Path.home() / ".claude" / "m365" / "token-cache.bin"

# Graph small-upload (PUT …/content) caps at 4 MB; above this we use an
# upload session. We switch a little early to leave headroom.
SIMPLE_UPLOAD_MAX_BYTES = 4 * 1024 * 1024 - 1024
UPLOAD_CHUNK_BYTES = 5 * 1024 * 1024  # multiple of 320 KiB, Graph requirement


class SharePointError(Exception):
    """Raised when credentials are bad or Graph rejects a request."""


def load_creds(creds_path: Path = CREDS_PATH) -> dict:
    creds_path = Path(creds_path).expanduser()
    if not creds_path.exists():
        raise SharePointError(
            f"Missing credentials at {creds_path}. This machine isn't set up "
            "for M365/SharePoint. Drop the JSON with tenant_id / client_id / "
            "client_secret / sender_upn and `chmod 600` it. See the SharePoint "
            "section of ~/.claude/rules/m365-graph.md."
        )
    if (creds_path.stat().st_mode & 0o077) != 0:
        raise SharePointError(
            f"{creds_path} has loose permissions; run `chmod 600 {creds_path}`."
        )
    with creds_path.open() as f:
        creds = json.load(f)
    required = {"tenant_id", "client_id", "client_secret"}
    missing = required - creds.keys()
    if missing:
        raise SharePointError(f"{creds_path} missing fields: {sorted(missing)}")
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
        raise SharePointError(
            f"Token request failed: {result.get('error')} — "
            f"{result.get('error_description', '')[:300]}"
        )
    if cache.has_state_changed:
        CACHE_PATH.write_text(cache.serialize())
        CACHE_PATH.chmod(0o600)
    return result["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _encode_path(item_path: str) -> str:
    """Percent-encode a drive-relative path, preserving the folder slashes.

    Client/folder names contain spaces, dots, parentheses and apostrophes
    (e.g. "Sera Custom Integrators (Stereo Planet)"); quote() with safe="/"
    keeps the path structure while escaping the rest.
    """
    return quote(item_path.strip("/"), safe="/")


def _check(resp: requests.Response, action: str) -> requests.Response:
    if not resp.ok:
        raise SharePointError(
            f"{action} failed: HTTP {resp.status_code} — {resp.text[:500]}"
        )
    return resp


def list_children(token: str, item_path: str | None = None) -> list[dict]:
    """List children of the drive root (clients) or of a folder path."""
    if item_path:
        url = f"{GRAPH_ROOT}/root:/{_encode_path(item_path)}:/children"
    else:
        url = f"{GRAPH_ROOT}/root/children"
    items: list[dict] = []
    while url:
        data = _check(
            requests.get(url, headers=_headers(token), timeout=30),
            f"List '{item_path or '/'}'",
        ).json()
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items


def read_file(token: str, item_path: str) -> bytes:
    url = f"{GRAPH_ROOT}/root:/{_encode_path(item_path)}:/content"
    return _check(
        requests.get(url, headers=_headers(token), timeout=120),
        f"Read '{item_path}'",
    ).content


def write_file(token: str, item_path: str, data: bytes) -> dict:
    encoded = _encode_path(item_path)
    if len(data) <= SIMPLE_UPLOAD_MAX_BYTES:
        url = f"{GRAPH_ROOT}/root:/{encoded}:/content"
        headers = {**_headers(token), "Content-Type": "application/octet-stream"}
        return _check(
            requests.put(url, headers=headers, data=data, timeout=120),
            f"Write '{item_path}'",
        ).json()
    return _upload_large(token, encoded, item_path, data)


def _upload_large(token: str, encoded: str, item_path: str, data: bytes) -> dict:
    session_url = f"{GRAPH_ROOT}/root:/{encoded}:/createUploadSession"
    body = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    upload_url = _check(
        requests.post(session_url, headers=_headers(token), json=body, timeout=30),
        f"Create upload session for '{item_path}'",
    ).json()["uploadUrl"]

    total = len(data)
    resp = None
    for start in range(0, total, UPLOAD_CHUNK_BYTES):
        chunk = data[start : start + UPLOAD_CHUNK_BYTES]
        end = start + len(chunk) - 1
        resp = _check(
            requests.put(
                upload_url,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{total}",
                },
                data=chunk,
                timeout=300,
            ),
            f"Upload chunk {start}-{end} of '{item_path}'",
        )
    return resp.json() if resp is not None and resp.content else {"name": item_path}


def _cmd_list_clients(token: str, _args: argparse.Namespace) -> None:
    for item in list_children(token):
        kind = "dir " if "folder" in item else "file"
        print(f"{kind}  {item['name']}")


def _cmd_list(token: str, args: argparse.Namespace) -> None:
    path = args.client if not args.sub else f"{args.client}/{args.sub}"
    for item in list_children(token, path):
        kind = "dir " if "folder" in item else "file"
        size = item.get("size", "")
        print(f"{kind}  {item['name']}\t{size}")


def _cmd_read(token: str, args: argparse.Namespace) -> None:
    content = read_file(token, args.path)
    if args.out:
        Path(args.out).write_bytes(content)
        print(f"Wrote {len(content)} bytes to {args.out}")
    else:
        sys.stdout.buffer.write(content)


def _cmd_write(token: str, args: argparse.Namespace) -> None:
    data = Path(args.file).read_bytes()
    result = write_file(token, args.path, data)
    print(f"Uploaded {len(data)} bytes to '{args.path}' (id={result.get('id', '?')})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read/write VitalAILabs client docs on SharePoint via Graph."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-clients", help="List client folders at the site root.")

    p_list = sub.add_parser("list", help="List a client folder (or a subfolder).")
    p_list.add_argument("client", help="Client folder name.")
    p_list.add_argument("sub", nargs="?", default="", help="Subfolder (optional).")

    p_read = sub.add_parser("read", help="Read a file's content.")
    p_read.add_argument("path", help="client/sub/file path within the site.")
    p_read.add_argument("--out", help="Write to this local path instead of stdout.")

    p_write = sub.add_parser("write", help="Upload a local file to a site path.")
    p_write.add_argument("path", help="client/sub/file destination path.")
    p_write.add_argument("--file", required=True, help="Local file to upload.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "list-clients": _cmd_list_clients,
        "list": _cmd_list,
        "read": _cmd_read,
        "write": _cmd_write,
    }
    try:
        token = get_token(load_creds())
        handlers[args.command](token, args)
    except SharePointError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
