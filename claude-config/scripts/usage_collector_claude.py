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
# Cross-repo attribution signals (issue #311) are extracted by TOKEN PARSING in mine_command —
# NOT by raw-string regex (which would fire inside echo/comments/quoted strings).
# _GH_REPO_RE / _GIT_C_RE are intentionally absent; see mine_command for the tokenized approach.
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


def _gh_repo_project(toks: list) -> str | None:
    """Extract the `name` from `--repo owner/name` in a TOKENIZED gh argv.
    Only fires when `toks[0]` is `gh` (or a bare `gh` invocation) — prevents matching
    `echo "--repo x/y"`, comments, or strings that contain --repo but are not actual gh calls.
    Handles both `--repo owner/name` (separate token) and `--repo=owner/name` (inline value).
    Returns the repo name (the part after `/`), or None."""
    if not toks or toks[0] != "gh":
        return None
    i = 1
    while i < len(toks):
        tok = toks[i]
        if tok == "--repo" and i + 1 < len(toks):
            val = toks[i + 1]
            if "/" in val:
                return val.split("/", 1)[1]
        elif tok.startswith("--repo="):
            val = tok[len("--repo=") :]
            if "/" in val:
                return val.split("/", 1)[1]
        i += 1
    return None


def _git_c_project_and_task(
    toks: list, existing_task: str | None
) -> tuple[str | None, str | None]:
    """Extract (project, task) from a TOKENIZED `git -C <path> ...` invocation.
    Only fires when `toks[0]` is `git` — prevents matching `echo "git -C ..."` or shell strings.
    Skips shell-variable paths (start with `$`).
    Returns (project, task) where either may be None."""
    if not toks or toks[0] != "git":
        return None, None
    # Find -C flag and its path argument
    raw_path = None
    checkout_branch = None
    i = 1
    while i < len(toks):
        tok = toks[i]
        if tok == "-C" and i + 1 < len(toks):
            raw_path = toks[i + 1]
            i += 2
        elif tok == "checkout" or tok == "switch":
            # Look for -b <branch> (or --branch <branch>)
            j = i + 1
            while j < len(toks):
                if toks[j] in ("-b", "--branch") and j + 1 < len(toks):
                    checkout_branch = toks[j + 1]
                    break
                j += 1
            i += 1
        else:
            i += 1
    if raw_path is None:
        return None, None
    # Skip shell variables (unresolvable at parse time)
    if raw_path.startswith("$") or raw_path.startswith('"$'):
        return None, None
    proj = _project_from_path(raw_path)
    task = None
    if proj and checkout_branch and existing_task is None:
        task = _task_from_branch(checkout_branch)
    return proj, task


def mine_command(cmd: str) -> dict:
    """Derive {task?, project?, work_host?} from one shell command. The basis of automated, manual-tag-
    free attribution (§4.3): a `git checkout -b feat/issue-N` names the task even cross-repo, and an
    `ssh host 'cd repo'` names the work_host + project under SSH-develop.

    Cross-repo signals (issue #311) use TOKENIZED matching — `--repo` and `-C` are only recognised
    when they appear as actual argv of a `gh`/`git` invocation, not inside echo/quoted strings."""
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
    # PRECEDENCE within a single command (precision over recall — false attribution is worse than none):
    #   1. cd <path>  — already handled above; most specific (context-setting)
    #   2. gh --repo owner/name  — explicit gh flag; fills gap when cd is absent (TOKENIZED: only
    #      fires for actual `gh` invocations, never inside echo/comments/strings)
    #   3. git -C <path>  — fills gap when neither cd nor --repo is present (TOKENIZED: only fires
    #      for actual `git` invocations)
    #   4. If BOTH --repo and git -C fire on the SAME command with DIFFERENT values → stay
    #      unattributed (conflicting signals, precision over recall).
    # Per-message precedence (gitBranch vs mined) is enforced in extract_records (not here).
    if "project" not in out:
        # Tokenized extraction — only matches real gh/git argv, not substrings or quoted strings
        repo_proj = _gh_repo_project(toks)

        gitc_proj, gitc_task = _git_c_project_and_task(toks, out.get("task"))

        if repo_proj and gitc_proj and repo_proj != gitc_proj:
            # Conflicting signals in the same command — stay unattributed (precision over recall)
            pass
        elif repo_proj:
            out["project"] = repo_proj
        elif gitc_proj:
            out["project"] = gitc_proj
            if gitc_task and "task" not in out:
                out["task"] = gitc_task
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
        # Identity (account/org/email) is stable across sessions → safe to back-fill from the current
        # account. billing MODE is NOT: a historical session may have been on an API key. We did not
        # capture it (the sidecar only began #265), so it is genuinely UNKNOWN — never assume the
        # current account's mode (that falsely labels all history 'subscription'). Honest > convenient.
        rec.update(
            account=fallback.get("account_uuid"),
            org=fallback.get("org"),
            email=fallback.get("email"),
            billing_type="unknown",
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
            # Per-message project precedence (AC3/issue #311 — gitBranch presence as discriminant):
            #
            #   1. SSH-develop (§4.2): work_host ≠ inference_host means an ssh command set it.
            #      cwd is local and irrelevant; trust the ssh-mined active["project"].
            #
            #   2. gitBranch present/non-empty → cwd IS a real local git repo.  Use
            #      _project_from_path(cwd): the repo the user is PHYSICALLY IN is authoritative.
            #      A stray `gh --repo other` CANNOT override it (hijack prevented).
            #
            #   3. gitBranch absent/empty AND a mined project exists → cwd is NOT a git repo
            #      (e.g. ~/projects/scratch).  The mined --repo/git-C target is the actual work
            #      target.  THIS is the #311 target case: cwd basename ("scratch") is useless
            #      but the explicit --repo/git-C signal tells us where the work happens.
            #
            #   4. Everything else → cwd basename fallback, else None/unattributed.
            #
            # Precision over recall: genuinely ambiguous → prefer unattributed over a guess.
            on_remote = active["work_host"] != inference_host
            git_branch = entry.get("gitBranch")
            git_branch_present = bool(
                git_branch
            )  # non-empty string = inside a git repo
            cwd_project = _project_from_path(entry.get("cwd"))
            if on_remote:
                # Branch 1 — SSH-develop: trust ssh-mined project; cwd is local, irrelevant.
                cur_project = active["project"] or cwd_project
            elif git_branch_present:
                # Branch 2 — real local repo (gitBranch confirms it): cwd is authoritative.
                # Stray --repo flag from an earlier message cannot hijack.
                cur_project = cwd_project
            elif active["project"]:
                # Branch 3 — no gitBranch (not in a repo, e.g. ~/projects/scratch): use mined
                # signal.  This is the #311 target: cwd basename would mis-attribute to "scratch",
                # but the explicit --repo/git-C mine is what the work is actually for.
                cur_project = active["project"]
            else:
                # Branch 4 — fallback: no repo, no mined signal → cwd basename or None.
                cur_project = cwd_project
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
        # Cross-command conflict guard (issue #311 Finding 4): if two commands in the SAME assistant
        # message mine DIFFERENT projects, last-write-win is a mis-attribution risk.  Detect conflict
        # and clear project for that message so it stays unattributed rather than wrong.
        mined_project: str | None = None
        cross_cmd_conflict = False
        for cmd in _iter_commands(entry):
            mined = mine_command(cmd)
            new_proj = mined.get("project")
            if new_proj and mined_project and new_proj != mined_project:
                cross_cmd_conflict = True  # two commands disagree — clear project below
            if new_proj:
                mined_project = new_proj
            active.update(mined)
        if cross_cmd_conflict:
            active["project"] = None  # ambiguous — do not mis-attribute
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
