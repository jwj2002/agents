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
# Cross-repo attribution signals (issue #311):
#   _GH_REPO_RE  — `gh ... --repo owner/name`  → project = <name>
#   _GIT_C_RE    — `git -C <path> ...`          → project = _project_from_path(<path>)
# Paths that start with '$' or '"$' are shell variables and cannot be resolved at parse time.
_GH_REPO_RE = re.compile(r"--repo\s+[a-zA-Z0-9_.-]+/([a-zA-Z0-9_.-]+)")
_GIT_C_RE = re.compile(r"\bgit\s+-C\s+(\S+)")
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
    # Cross-repo attribution: fill project gap when cd gave nothing (issue #311).
    #
    # PRECEDENCE (precision over recall — false attribution is worse than none):
    #   1. cd <path>  — already handled above; most specific (context-setting)
    #   2. --repo owner/name  — explicit gh flag; fills gap when cd is absent
    #   3. git -C <path>  — fills gap when neither cd nor --repo is present
    #   4. If BOTH --repo and git -C fire on the SAME command with DIFFERENT values
    #      → clear project (conflicting signals, do not guess).
    #   5. Per-message cwd-vs-mined precedence is enforced in extract_records (not here):
    #      cwd-derived project wins for local work; mined wins under SSH-develop (§4.2);
    #      mined fills the gap when cwd yields nothing (the #311 scratch-session target).
    if "project" not in out:
        # Determine candidates from --repo and git -C
        repo_match = _GH_REPO_RE.search(cmd)
        gitc_match = _GIT_C_RE.search(cmd)

        repo_proj = repo_match.group(1) if repo_match else None

        gitc_proj = None
        if gitc_match:
            raw_path = gitc_match.group(1)
            # Skip shell variables (unresolvable at parse time)
            if not raw_path.startswith("$") and not raw_path.startswith('"$'):
                gitc_proj = _project_from_path(raw_path)
                # Also extract task from `git -C <path> checkout -b <branch>` — the
                # existing _CHECKOUT_RE requires `git\s+checkout` (no gap) and misses
                # this form, so we handle it here alongside project extraction.
                if gitc_proj and "task" not in out:
                    gitc_co = re.search(r"\bcheckout\s+-b\s+(\S+)", cmd)
                    if gitc_co:
                        t = _task_from_branch(gitc_co.group(1))
                        if t:
                            out["task"] = t

        if repo_proj and gitc_proj and repo_proj != gitc_proj:
            # Conflicting signals in the same command — stay unattributed (precision over recall)
            pass
        elif repo_proj:
            out["project"] = repo_proj
        elif gitc_proj:
            out["project"] = gitc_proj
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


def load_account_map(sidecar_path) -> dict:
    """Read the SessionStart sidecar (account-map.jsonl) → {session_id: account-fields} (#265 §4.1)."""
    p = Path(sidecar_path)
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict) and e.get(
            "session_id"
        ):  # ignore non-object lines (no crash)
            out[e["session_id"]] = e  # last write wins
    return out


def current_account(claude_json_path) -> dict:
    """The CURRENT logged-in account from ~/.claude.json — the historical fallback for sessions with no
    sidecar entry (#265 §4.1). `account_uuid: "unknown"` ONLY when the file is ABSENT; a malformed/
    unreadable file is `account_source: "unreadable"` (a distinct reason, never silently `unknown`)."""
    p = Path(claude_json_path)
    if not p.exists():
        return {
            "account_uuid": "unknown",
            "org": None,
            "email": None,
            "billing_type": None,
            "account_source": "unknown",
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "account_uuid": None,
            "org": None,
            "email": None,
            "billing_type": None,
            "account_source": "unreadable",
        }
    if not isinstance(data, dict):
        data = {}
    oa = data.get("oauthAccount")
    oa = oa if isinstance(oa, dict) else {}
    return {
        "account_uuid": oa.get("accountUuid"),
        "org": oa.get("organizationName"),
        "email": oa.get("emailAddress"),
        "billing_type": _classify_billing(oa.get("billingType")),
        "account_source": "current_fallback",
    }


def _classify_billing(raw) -> str | None:
    """subscription | metered (raw passthrough if unknown) — mirrors the hook's classifier (§6)."""
    r = str(raw or "").lower()
    if not r:
        return None
    if "subscription" in r or r in ("max", "pro", "team", "enterprise"):
        return "subscription"
    if r in ("console", "api", "metered", "usage_based", "pay_as_you_go"):
        return "metered"
    return raw


def _apply_account(rec: dict, account_map: dict | None, fallback: dict | None) -> dict:
    """Join account fields onto a record by session_id: sidecar entry → current-account fallback →
    None (the #262 default). billing_type carries an account_source reason so it's never silently null."""
    src = (account_map or {}).get(rec.get("session_id"))
    if src:
        rec.update(
            account=src.get("account_uuid"),
            org=src.get("org"),
            email=src.get("email"),
            billing_type=src.get("billing_type"),
            account_source="sidecar",
        )
    elif fallback:
        rec.update(
            account=fallback.get("account_uuid"),
            org=fallback.get("org"),
            email=fallback.get("email"),
            billing_type=fallback.get("billing_type"),
            account_source=fallback.get("account_source", "current_fallback"),
        )
    return rec


def extract_records(
    entries: list,
    *,
    inference_host: str,
    strict: bool = True,
    account_map: dict | None = None,
    fallback_account: dict | None = None,
) -> list:
    """Core walker: chronological pass over ONE transcript's entries → normalized usage records.
    Tracks active task/project/work_host (segmentation); attributes each assistant message to the
    state active at its timestamp; mines each entry's commands to update state for SUBSEQUENT messages.
    `account_map`/`fallback_account` (from #265) fill account/billing_type by session_id."""
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
            # Per-message project precedence (AC3 precision — enforced here, not in mine_command):
            #   1. SSH-develop (§4.2): when work_host != inference_host, cwd is LOCAL and meaningless
            #      for attribution.  The ssh-mined active["project"] (set by ssh 'cd repo') wins.
            #   2. Local work: the current message's cwd is GROUND TRUTH.  If cwd resolves to a repo,
            #      use that — regardless of any mined active["project"] from a stray --repo flag in an
            #      earlier message.  This prevents a one-off `gh pr view --repo other/repo` from
            #      hijacking all subsequent messages in a real cwd=agents session.
            #   3. Fallback: cwd yields nothing (scratch dir, temp path) → use mined active["project"].
            #      This is the #311 target: scratch sessions with cross-repo `--repo`/`git -C` signals.
            cwd_project = _project_from_path(entry.get("cwd"))
            on_remote = active["work_host"] != inference_host
            if on_remote:
                # SSH-develop: trust the ssh-mined project; cwd is local and irrelevant.
                cur_project = active["project"] or cwd_project
            elif cwd_project:
                # Local work with a real cwd repo: cwd wins over any stray mined signal.
                cur_project = cwd_project
            else:
                # Local work, no cwd repo (scratch / temp): fall back to mined active project.
                cur_project = active["project"]
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
            records.append(_apply_account(rec, account_map, fallback_account))
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
    projects_dir,
    shard_path,
    *,
    inference_host: str | None = None,
    strict: bool = True,
    sidecar_path=None,
    claude_json_path=None,
) -> dict:
    """Walk all transcripts under `projects_dir`, emit normalized records (with #265 account join), and
    APPEND new ones to `shard_path` (append-only, idempotent: dedup_key skip)."""
    inference_host = inference_host or get_host_name()
    home = Path.home()
    account_map = load_account_map(
        sidecar_path or home / ".claude" / "telemetry" / "account-map.jsonl"
    )
    fallback_account = current_account(claude_json_path or home / ".claude.json")
    shard_path = Path(shard_path)
    seen = _existing_dedup_keys(shard_path)
    written = skipped = project_attributed = 0
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    with shard_path.open("a", encoding="utf-8") as fh:
        for tpath in sorted(glob.glob(str(Path(projects_dir) / "*" / "*.jsonl"))):
            for rec in extract_records(
                read_transcript(tpath),
                inference_host=inference_host,
                strict=strict,
                account_map=account_map,
                fallback_account=fallback_account,
            ):
                if rec["dedup_key"] in seen:
                    skipped += 1
                    continue
                seen.add(rec["dedup_key"])
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
                if rec.get("project") is not None:
                    project_attributed += 1
    # AC4: attribution OUTCOME of THIS run's written records — honest and non-silent. We do NOT
    # diff the append-only shard (its project=None total only ever grows as rows accumulate, so it
    # can never show a "reduction"). The feature's actual EFFECT — records rescued from project=None
    # by a mined --repo/git-C target that cwd alone would miss — is demonstrated by the with/without
    # counterfactual in test_collect_repo_target_reduces_unattributed.
    return {
        "written": written,
        "skipped": skipped,
        "shard": str(shard_path),
        "project_attributed": project_attributed,
        "project_unattributed": written - project_attributed,
    }
