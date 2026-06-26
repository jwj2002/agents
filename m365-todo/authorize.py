"""One-time device-code authorization for Microsoft To Do (personal account).

Two steps so the device code can be surfaced before the (blocking) poll:

    authorize.py start    # prints the URL + code, saves flow.json, exits immediately
    authorize.py finish   # blocks until you approve in the browser, saves the token
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import auth  # same directory

FLOW_PATH = Path(__file__).resolve().parent / "flow.json"
CODE_PATH = Path(__file__).resolve().parent / ".device_code.txt"


def start() -> int:
    app = auth.build_app()
    flow = app.initiate_device_flow(scopes=auth.scopes())
    if "user_code" not in flow:
        print("FAILED to start device flow:", flow.get("error_description") or flow)
        return 2
    FLOW_PATH.write_text(json.dumps(flow), encoding="utf-8")
    CODE_PATH.write_text(flow["message"], encoding="utf-8")
    print(flow["message"], flush=True)
    print(f"\nverification_uri: {flow.get('verification_uri')}")
    print(f"user_code: {flow.get('user_code')}")
    print(f"expires_in: {flow.get('expires_in')}s")
    return 0


def finish() -> int:
    if not FLOW_PATH.exists():
        print("No flow.json — run `authorize.py start` first.")
        return 2
    flow = json.loads(FLOW_PATH.read_text(encoding="utf-8"))
    cache = auth._load_cache()
    app = auth.build_app(cache)
    result = app.acquire_token_by_device_flow(flow)  # blocks until approved/expired
    if "access_token" not in result:
        print("AUTH FAILED:", result.get("error_description") or result)
        return 1
    auth._save_cache(cache)
    FLOW_PATH.unlink(missing_ok=True)
    CODE_PATH.unlink(missing_ok=True)
    print("AUTHORIZED OK")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    sys.exit(start() if cmd == "start" else finish())
