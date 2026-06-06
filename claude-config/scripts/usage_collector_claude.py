"""Claude transcript usage collector + activity-miner (fleet-usage-monitor §8 step 1).

Walks `~/.claude/projects/<proj>/<session>.jsonl`, emits ONE normalized usage record per assistant
message (attributed by the message's OWN timestamp so 55-day sessions span 55 days of trend), and
appends them to the per-host shard `telemetry/<host>/usage.jsonl` (same convention as failures shards).

Attribution is by ACTIVITY-MINING (§4.3) — task/project/work_host are derived from the session's own
git/`gh`/`ssh` tool calls, with NO manual tags. State is tracked chronologically so a session that
spans several tasks/repos is SEGMENTED (each message attributed to the task active at its time). Under
SSH-develop (§4.2) `cwd`/`gitBranch` are local, so mined `ssh <host>` commands set `work_host`/`project`
while tokens stay on `inference_host` (this collector's host). Parallel sessions are independent
transcripts → no double-count, no cross-session bleed (§4.4). `account`/`billing_type` are left null
here (filled by the #265 join). Unknown model → loud error (reuses `token_collector` strict).
"""

from __future__ import annotations

import glob
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import token_collector as C  # noqa: E402  (session_cost strict — wraps otel_sink pricing; unknown model = loud error)

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
    from project_resolver import get_host_name
except Exception:  # pragma: no cover - fallback when lib not importable
    import socket

    def get_host_name():
        return socket.gethostname().split(".")[0]


PROVIDER = "claude"

# usage field name → normalized token field
_USAGE_MAP = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cache_read_input_tokens": "cache_read",
    "cache_creation_input_tokens": "cache_creation",
}

# Claude Code internal non-API model markers (injected/synthetic messages) — these are NOT billable
# inference, so they are SKIPPED (not cost-computed). A genuinely unknown REAL model still raises
# loudly via token_collector strict (the AC distinction; verified against real transcripts).
_SKIP_MODELS = {"<synthetic>", "<compact>"}

_ISSUE_RE = re.compile(r"issue-(\d+)", re.IGNORECASE)
_CLOSES_RE = re.compile(r"\b(?:closes|fixes|resolves)\s+#(\d+)", re.IGNORECASE)
_CHECKOUT_RE = re.compile(r"git\s+checkout\s+-b\s+(\S+)")
_CD_RE = re.compile(r"\bcd\s+([~\w./-]+)")
_NONTASK_BRANCHES = {"head", "main", "master", "", None}
# OpenSSH short flags that consume the NEXT token as their argument — so the host parser skips both
# (else `ssh -p 22 host` mis-reads "22" as the host; Codex #262).
_SSH_ARG_FLAGS = set("bcDEeFIiJLlmOopQRSWw")


def _msg(entry: dict) -> dict:
    """The entry's message as a dict — never crashes on transcript shape drift (a non-dict message
    or usage becomes {}). Codex #262: real transcripts can carry unexpected shapes."""
    m = entry.get("message") if isinstance(entry, dict) else None
    return m if isinstance(m, dict) else {}


def _ssh_host(tokens: list) -> str | None:
    """First real host token after `ssh`, correctly skipping flags AND their arguments (`-p 22`,
    `-i key`, `-pVALUE`). Returns the host (user@ stripped), or None."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            i += 1  # ssh has no GNU long opts; treat as a lone flag
            continue
        if t.startswith("-"):
            cluster = t[1:]
            # In a short-option cluster only the LAST option can take an argument, and only if it has
            # no INLINE value (so `-p 22` and `-vp 22` skip the next token; `-p22`/`-v` do not). Codex #262.
            if cluster and cluster[-1] in _SSH_ARG_FLAGS:
                i += 2
            else:
                i += 1
            continue
        return t.split("@")[-1]
    return None


def _task_from_branch(branch) -> str | None:
    """A branch → task: `feat/issue-42-x` → `issue:42`; a real named branch → that branch; main/HEAD → None."""
    if not branch:
        return None
    m = _ISSUE_RE.search(branch)
    if m:
        return f"issue:{m.group(1)}"
    return None if branch.strip().lower() in _NONTASK_BRANCHES else branch


def _project_from_path(path) -> str | None:
    """Repo/project name from a cwd path: `~/agents`→`agents`, `.../projects/scratch`→`scratch`."""
    if not path:
        return None
    name = Path(str(path).rstrip("/")).name
    return name or None


def _iter_commands(entry: dict):
    """Yield Bash command strings from the assistant message's tool_use blocks."""
    content = _msg(entry).get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            inp = block.get("input") or {}
            cmd = inp.get("command")
            if isinstance(cmd, str):
                yield cmd


def mine_command(cmd: str) -> dict:
    """Derive {task?, project?, work_host?} from one shell command. The basis of automated, manual-tag-
    free attribution (§4.3): a `git checkout -b feat/issue-N` names the task even cross-repo, and an
    `ssh host 'cd repo'` names the work_host + project under SSH-develop."""
    out: dict = {}
    try:
        toks = shlex.split(cmd)
    except ValueError:
        toks = cmd.split()
    if "ssh" in toks:
        host = _ssh_host(toks[toks.index("ssh") + 1 :])
        if host:
            out["work_host"] = host
    co = _CHECKOUT_RE.search(cmd)
    if co:
        t = _task_from_branch(co.group(1))
        if t:
            out["task"] = t
    closes = _CLOSES_RE.search(cmd)
    if closes and "task" not in out:
        out["task"] = f"issue:{closes.group(1)}"
    cd = _CD_RE.search(cmd)
    if cd and cd.group(1) not in (
        "-",
        "~",
        "..",
    ):  # skip cd -, cd ~, cd .. (bogus project names)
        proj = _project_from_path(cd.group(1))
        if proj:
            out["project"] = proj
    return out


def _is_compaction(entry: dict) -> bool:
    """A compaction/continuation boundary (re-seeds the prompt cache → a cache_creation spike, §4.5)."""
    if entry.get("isCompactSummary") or entry.get("subtype") == "compact":
        return True
    content = _msg(entry).get("content", "")
    text = content if isinstance(content, str) else json.dumps(content)
    return (
        "being continued from a previous conversation" in text
        or "ran out of context" in text
    )


def _is_assistant_usage(entry: dict) -> bool:
    msg = _msg(entry)
    return isinstance(msg.get("usage"), dict) and (
        msg.get("role") == "assistant" or entry.get("type") == "assistant"
    )


def extract_records(entries: list, *, inference_host: str, strict: bool = True) -> list:
    """Core walker: chronological pass over ONE transcript's entries → normalized usage records.
    Tracks active task/project/work_host (segmentation); attributes each assistant message to the
    state active at its timestamp; mines each entry's commands to update state for SUBSEQUENT messages."""
    entries = sorted(entries, key=lambda e: e.get("timestamp") or "")
    active = {"task": "unattributed", "project": None, "work_host": inference_host}
    pending_compaction = False
    records = []
    for idx, entry in enumerate(entries):
        if _is_compaction(entry):
            pending_compaction = True
        msg = _msg(entry)
        if _is_assistant_usage(entry) and msg.get("model") not in _SKIP_MODELS:
            # gitBranch is GROUND TRUTH for THIS message (Claude Code captures it at message start, so a
            # `git checkout -b` message still shows the OLD branch → it naturally gives the "subsequent
            # message" boundary). Mined `active` is the fallback when gitBranch is unusable (cross-repo).
            cur_task = _task_from_branch(entry.get("gitBranch")) or active["task"]
            cur_project = active["project"] or _project_from_path(entry.get("cwd"))
            usage = msg.get("usage") or {}
            tok = {
                norm: int(usage.get(raw, 0) or 0) for raw, norm in _USAGE_MAP.items()
            }
            cost_rec = {**tok, "model": msg.get("model")}
            sid, uuid = entry.get("sessionId"), entry.get("uuid")
            # dedup_key must be UNIQUE even when sessionId/uuid are missing (else malformed records
            # collapse to "None:None" and undercount, Codex #262) — fall back to a position+content key.
            dedup_key = (
                f"{sid}:{uuid}"
                if uuid
                else f"{sid}:{entry.get('timestamp')}:{idx}:{tok['input']}:{tok['output']}"
            )
            rec = {
                "provider": PROVIDER,
                "account": None,
                "billing_type": None,
                "inference_host": inference_host,
                "work_host": active["work_host"],
                "project": cur_project,
                "model": msg.get("model"),
                "task": cur_task,
                **tok,
                "cost_usd": C.session_cost(cost_rec, strict=strict),
                "ts": entry.get("timestamp"),
                "session_id": sid,
                "compaction": pending_compaction,
                "dedup_key": dedup_key,
            }
            records.append(rec)
            pending_compaction = False
        # mine this entry's commands → update active state for subsequent messages (segmentation)
        for cmd in _iter_commands(entry):
            active.update(mine_command(cmd))
    return records


def read_transcript(path) -> list:
    """Parse a transcript JSONL into entries (skips corrupt lines)."""
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


def _existing_dedup_keys(shard_path: Path) -> set:
    if not shard_path.exists():
        return set()
    keys = set()
    for line in shard_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            keys.add(json.loads(line).get("dedup_key"))
        except json.JSONDecodeError:
            continue
    return keys


def collect(
    projects_dir, shard_path, *, inference_host: str | None = None, strict: bool = True
) -> dict:
    """Walk all transcripts under `projects_dir`, emit normalized records, and APPEND new ones to
    `shard_path` (append-only, idempotent: records whose dedup_key already exists are skipped)."""
    inference_host = inference_host or get_host_name()
    shard_path = Path(shard_path)
    seen = _existing_dedup_keys(shard_path)
    written = skipped = 0
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    with shard_path.open("a", encoding="utf-8") as fh:
        for tpath in sorted(glob.glob(str(Path(projects_dir) / "*" / "*.jsonl"))):
            for rec in extract_records(
                read_transcript(tpath), inference_host=inference_host, strict=strict
            ):
                if rec["dedup_key"] in seen:
                    skipped += 1
                    continue
                seen.add(rec["dedup_key"])
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
    return {"written": written, "skipped": skipped, "shard": str(shard_path)}
