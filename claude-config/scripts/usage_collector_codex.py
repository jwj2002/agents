"""Codex/ChatGPT session usage collector (fleet-usage-monitor §8 step 2, §4.6).

Walks `~/.codex/sessions/**/*.jsonl` and appends normalized usage records to the SAME per-host shard
`telemetry/<host>/usage.jsonl` as the Claude collector (mixed-provider, distinguished by `provider`).
Reuses the Claude collector's activity-miner so attribution is consistent across providers.

Codex session format (verified 2026-06-06):
- a session-meta first line whose payload holds `cwd`, a `git` block (`branch`, `repository_url`), and
  `id`; `model` (e.g. `gpt-5.5`) appears in a payload during the run.
- `token_count` events with `info.last_token_usage` (per-turn delta) and `info.total_token_usage`
  (cumulative). Summing `last_token_usage` equals the final total → one record per `token_count` event,
  no double-count. Codex `input_tokens` INCLUDES `cached_input_tokens`, so fresh input = input − cached;
  `reasoning_output_tokens` are billed as output; OpenAI has no separate cache-write (cache_creation=0).
- account identity comes from `~/.codex/auth.json` (account_id + JWT email) — the AUTH KEY IS NEVER
  written to a shard. One OpenAI account spans hosts, so `inference_host` is the per-PC separator (§4.6);
  the agent-b bridge on jns-server is captured by that host's collector as `inference_host=jns-server`.
"""

from __future__ import annotations

import base64
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import token_collector as C  # noqa: E402
import usage_collector_claude as UC  # noqa: E402  (shared activity-miner: mine_command, _task_from_branch, …)

PROVIDER = "codex"


def _norm_tokens(last: dict) -> dict:
    """Map a Codex `last_token_usage` to the normalized schema. input_tokens INCLUDES cached, so fresh
    input = input − cached; reasoning tokens bill as output; OpenAI has no separate cache-write."""
    inp = int(last.get("input_tokens", 0) or 0)
    cached = int(last.get("cached_input_tokens", 0) or 0)
    out = int(last.get("output_tokens", 0) or 0) + int(
        last.get("reasoning_output_tokens", 0) or 0
    )
    return {
        "input": max(0, inp - cached),
        "output": out,
        "cache_read": cached,
        "cache_creation": 0,
    }


def _b64json(segment: str) -> dict:
    segment += "=" * (-len(segment) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(segment))
    except Exception:
        return {}


def read_codex_account(auth_path) -> dict:
    """Account identity from `~/.codex/auth.json` — NEVER returns the API key/token. `billing_type` is
    `subscription` when a ChatGPT OAuth account_id is present, else `metered` (API key)."""
    p = Path(auth_path)
    if not p.exists():
        return {"account": None, "email": None, "billing_type": None}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"account": None, "email": None, "billing_type": None}
    tokens = d.get("tokens") or {}
    account_id = tokens.get("account_id")
    email = None
    jwt = tokens.get("id_token") or tokens.get("access_token")
    if isinstance(jwt, str) and jwt.count(".") >= 2:
        email = _b64json(jwt.split(".")[1]).get("email")
    billing = (
        "subscription"
        if account_id
        else ("metered" if d.get("OPENAI_API_KEY") else None)
    )
    return {"account": account_id or email, "email": email, "billing_type": billing}


def _project_from_repo_url(url) -> str | None:
    if not url:
        return None
    name = str(url).rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else (name or None)


def _payload(entry: dict) -> dict:
    p = entry.get("payload") if isinstance(entry, dict) else None
    return p if isinstance(p, dict) else {}


def _command_from_function_call(p: dict) -> str | None:
    """Extract the shell command from a Codex function_call payload (arguments.command)."""
    args = p.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return args
    if isinstance(args, dict):
        cmd = args.get("command")
        if isinstance(cmd, list):
            return " ".join(map(str, cmd))
        if isinstance(cmd, str):
            return cmd
    return None


def _session_context(entries: list, *, inference_host: str) -> dict:
    """Scan a session for cwd/git/model + mined work_host/task, producing the session-level attribution
    shared by all its token_count records (a Codex `exec` is one task)."""
    cwd = git = model = session_id = None
    mined = {}
    for entry in entries:
        p = _payload(entry)
        cwd = cwd or p.get("cwd")
        git = git or p.get("git")
        model = model or p.get("model")
        session_id = session_id or p.get("id")
        if p.get("type") == "function_call":
            cmd = _command_from_function_call(p)
            if cmd:
                mined.update(UC.mine_command(cmd))
    git = git if isinstance(git, dict) else {}
    task = (
        UC._task_from_branch(git.get("branch")) or mined.get("task") or "unattributed"
    )
    project = (
        _project_from_repo_url(git.get("repository_url"))
        or mined.get("project")
        or UC._project_from_path(cwd)
    )
    return {
        "model": model,
        "session_id": session_id,
        "task": task,
        "project": project,
        "work_host": mined.get("work_host", inference_host),
    }


def extract_records(
    entries: list,
    *,
    inference_host: str,
    account_info: dict | None = None,
    strict: bool = True,
) -> list:
    """One normalized record per `token_count` event (per turn), using `last_token_usage`."""
    ctx = _session_context(entries, inference_host=inference_host)
    acct = account_info or {"account": None, "email": None, "billing_type": None}
    records = []
    idx = 0
    for entry in entries:
        p = _payload(entry)
        if p.get("type") != "token_count":
            continue
        last = (p.get("info") or {}).get("last_token_usage") or {}
        if not last:
            continue
        tok = _norm_tokens(last)
        cost_rec = {**tok, "model": ctx["model"]}
        records.append(
            {
                "provider": PROVIDER,
                "account": acct.get("account"),
                "billing_type": acct.get("billing_type"),
                "inference_host": inference_host,
                "work_host": ctx["work_host"],
                "project": ctx["project"],
                "model": ctx["model"],
                "task": ctx["task"],
                **tok,
                "cost_usd": C.session_cost(cost_rec, strict=strict),
                "ts": entry.get("timestamp"),
                "session_id": ctx["session_id"],
                "email": acct.get("email"),
                "dedup_key": f"codex:{ctx['session_id']}:{idx}",
            }
        )
        idx += 1
    return records


def read_session(path) -> list:
    out = []
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def collect(
    sessions_dir,
    shard_path,
    *,
    inference_host: str | None = None,
    auth_path=None,
    strict: bool = True,
) -> dict:
    """Walk all Codex sessions and APPEND new records to the shared `usage.jsonl` shard (idempotent
    via dedup_key, same as the Claude collector)."""
    inference_host = inference_host or UC.get_host_name()
    auth_path = auth_path or (Path.home() / ".codex" / "auth.json")
    account_info = read_codex_account(auth_path)
    shard_path = Path(shard_path)
    seen = UC._existing_dedup_keys(shard_path)
    written = skipped = 0
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    with shard_path.open("a", encoding="utf-8") as fh:
        for spath in sorted(
            glob.glob(str(Path(sessions_dir) / "**" / "*.jsonl"), recursive=True)
        ):
            for rec in extract_records(
                read_session(spath),
                inference_host=inference_host,
                account_info=account_info,
                strict=strict,
            ):
                if rec["dedup_key"] in seen:
                    skipped += 1
                    continue
                seen.add(rec["dedup_key"])
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
    return {"written": written, "skipped": skipped, "shard": str(shard_path)}
