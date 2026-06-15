"""coding-memory CLI.

Front-door commands (run anywhere): ingest, query, stats.
  - On jns (DATABASE_URL set) they run locally (embed + DB here).
  - On a laptop (CODING_MEMORY_SSH set) they dispatch to jns over SSH; the laptop
    only parses markdown and ships records — no model, no DB driver needed.
Internal server commands (executed on jns via SSH): _embed-store, _query, _stats.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys

from . import (
    ALLOWED_NAMESPACES,
    DEFAULT_SOURCES,
    RECALL_MIN_SCORE,
    is_remote,
    load_config,
    valid_remote_bin,
)
from . import parse as P


def _sources_from_args(pairs):
    out = dict(DEFAULT_SOURCES) if not pairs else {}
    for item in pairs or []:
        ns, _, path = item.partition("=")
        if not path:
            raise SystemExit(f"--source expects ns=path, got: {item}")
        out[ns.strip()] = path.strip()
    # residency guard: a source must be a KNOWN personal namespace AND resolve under
    # THAT namespace's canonical root — not merely under the shared ~/.claude/projects
    # parent, which also holds work-project memory on the work laptop.
    for ns, path in out.items():
        root = DEFAULT_SOURCES.get(ns)
        if root is None:
            raise SystemExit(
                f"refusing source ns '{ns}': not a known personal source {sorted(DEFAULT_SOURCES)}"
            )
        root_real = os.path.realpath(os.path.expanduser(root))
        real = os.path.realpath(os.path.expanduser(path))
        if real != root_real and not real.startswith(root_real + os.sep):
            raise SystemExit(
                f"refusing source path '{path}' for ns '{ns}': must resolve under {root_real}"
            )
    return out


def _ssh(cfg, remote_args, stdin_data=None):
    host = cfg["CODING_MEMORY_SSH"]
    remote_bin = cfg["CODING_MEMORY_REMOTE_BIN"]
    if not valid_remote_bin(remote_bin):
        raise SystemExit(f"unsafe CODING_MEMORY_REMOTE_BIN: {remote_bin!r}")
    remote = f"{remote_bin} " + " ".join(shlex.quote(a) for a in remote_args)
    # Keepalives: server-side embedding holds the channel idle for ~15s while the
    # model loads + embeds; a Cloudflare-tunneled SSH drops idle connections (-> 255).
    ssh = [
        "ssh",
        "-o",
        "ServerAliveInterval=10",
        "-o",
        "ServerAliveCountMax=18",
        host,
        remote,
    ]
    proc = subprocess.run(
        ssh,
        input=stdin_data.encode() if stdin_data is not None else None,
        capture_output=True,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr.decode(errors="replace"))
    sys.stdout.write(proc.stdout.decode(errors="replace"))
    return proc.returncode


# ---------- ingest ----------


def cmd_ingest(args, cfg):
    sources = _sources_from_args(args.source)
    parsed = P.build_records(sources)
    records = parsed["records"]
    prune = parsed["prune_namespaces"]
    print(
        f"parsed {len(records)} fact(s) from {len(sources)} namespace(s): "
        f"{', '.join(sources)} | prune-safe: {', '.join(prune) or '(none)'}",
        file=sys.stderr,
    )
    if args.dry_run:
        for r in records:
            print(f"  [{r['namespace']}] {r['name']}  ({r['source_path']})")
        return 0
    payload = json.dumps(parsed)
    if is_remote(cfg):
        return _ssh(cfg, ["_embed-store"], stdin_data=payload)
    return _embed_store(payload, cfg)


# embed + upsert this many records per chunk so a large ingest stays memory-bounded
_INGEST_CHUNK = 64


def _embed_store(payload, cfg):
    from . import embedder, store

    env = json.loads(payload)
    if isinstance(env, list):  # back-compat: bare record list
        env = {"records": env, "prune_namespaces": []}
    incoming = env.get("records", [])
    # residency: server-side allowlist — never store a non-personal namespace,
    # even from a misconfigured client.
    records = [r for r in incoming if r.get("namespace") in ALLOWED_NAMESPACES]
    rejected = len(incoming) - len(records)
    prune_ns = [n for n in env.get("prune_namespaces", []) if n in ALLOWED_NAMESPACES]

    cache = cfg.get("FASTEMBED_CACHE")
    conn = store.connect(cfg["DATABASE_URL"])
    stored = pruned = 0
    try:
        store.ensure_schema(conn)
        # group by each record's own origin: project namespaces use the machine
        # hostname; shared (git-synced) namespaces use "shared". Each origin is
        # diffed/pruned independently so machines never clobber each other.
        for origin in sorted({r.get("origin") or "unknown" for r in records}):
            orecs = [r for r in records if (r.get("origin") or "unknown") == origin]
            onamespaces = sorted({r["namespace"] for r in orecs})
            store.claim_unowned(conn, origin, onamespaces)  # adopt legacy rows once
            existing = store.existing_hashes(conn, origin, onamespaces)
            changed = [
                r
                for r in orecs
                if existing.get((r["namespace"], r["source_path"])) != r["content_hash"]
            ]
            for i in range(0, len(changed), _INGEST_CHUNK):
                batch = changed[i : i + _INGEST_CHUNK]
                vecs = embedder.embed_docs(
                    [P.embed_text(r) for r in batch], cache_dir=cache
                )
                for r, v in zip(batch, vecs):
                    store.upsert(conn, r, v, origin)
                conn.commit()
            stored += len(changed)
            for ns in onamespaces:
                if ns in prune_ns:
                    keep = [r["source_path"] for r in orecs if r["namespace"] == ns]
                    if keep:
                        pruned += store.delete_missing(conn, origin, ns, keep)
            conn.commit()
        report = {
            "parsed": len(incoming),
            "stored": stored,
            "unchanged": len(records) - stored,
            "rejected_nonpersonal": rejected,
            "pruned": pruned,
        }
        print(json.dumps(report))
        return 0
    finally:
        conn.close()


# ---------- query ----------


def cmd_query(args, cfg):
    text = " ".join(args.text).strip()
    if not text:
        raise SystemExit("query text required")
    if is_remote(cfg):
        remote = ["_query", "-k", str(args.k), "--mode", args.mode]
        if getattr(args, "for_prompt", False):
            remote.append("--for-prompt")
        if getattr(args, "min_score", None) is not None:
            remote += ["--min-score", str(args.min_score)]
        for ns in args.namespace or []:
            remote += ["--namespace", ns]
        remote += ["--", text]
        return _ssh(cfg, remote)
    return _query(text, args, cfg)


# This text is injected into phase prompts, so screen fact content for
# instruction-injection (a fact could contain "ignore prior instructions" etc.).
_INJECT_RE = re.compile(
    r"(ignore|disregard)\b.*\b(previous|prior|above|earlier)\b.*\b(instruction|context|prompt)"
    r"|you are now\b|system\s*prompt\s*:|\[/?INST\]|<\|im_start\|>",
    re.IGNORECASE | re.DOTALL,
)


def _scrub_recall(text: str) -> str:
    """Sanitize a recalled name/summary before it enters a prompt: drop control
    chars, strip leading markdown structure (no fake headers/lists), and withhold
    anything that looks like an instruction-injection attempt."""
    t = _sanitize(text).lstrip("#>*-` \t")
    return "[withheld — injection-like content]" if _INJECT_RE.search(t) else t


def _prompt_block(rows, max_chars=700):
    """A bounded, prompt-ready recall block: header + one summary line per fact,
    hard char cap. Empty when there's nothing relevant (fail-open: inject nothing).
    Budget is deliberately small — this rides inside an orchestrate phase prompt."""
    if not rows:
        return ""
    lines = [
        f"## Recalled coding-memory ({len(rows)} relevant; verify before trusting)"
    ]
    for r in rows:
        summ = _scrub_recall((r.get("summary") or "").replace("\n", " "))
        if len(summ) > 100:
            summ = summ[:97] + "..."
        lines.append(
            f"- [{r['namespace']}] {_scrub_recall(r['name'])}"
            + (f" — {summ}" if summ else "")
        )
    block = "\n".join(lines)
    return block[: max_chars - 3].rstrip() + "..." if len(block) > max_chars else block


def _query(text, args, cfg):
    from . import embedder, store

    cache = cfg.get("FASTEMBED_CACHE")
    qvec = embedder.embed_query(text, cache_dir=cache)
    for_prompt = getattr(args, "for_prompt", False)
    # --for-prompt is RELEVANCE-GATED: vector cosine, keep only facts above the
    # threshold (usually 0-1), so weak/irrelevant matches never bloat a phase prompt.
    mode = "vector" if for_prompt else args.mode
    conn = store.connect(cfg["DATABASE_URL"])
    try:
        rows = store.search(
            conn,
            qvec,
            text=text,
            k=args.k,
            namespaces=args.namespace or None,
            mode=mode,
        )
    finally:
        conn.close()
    if for_prompt:
        ms = getattr(args, "min_score", None)
        min_score = ms if ms is not None else RECALL_MIN_SCORE  # allow explicit 0.0
        rows = [r for r in rows if r.get("score", 0.0) >= min_score]
        block = _prompt_block(rows)  # empty -> nothing injected (fail-open)
        if block:
            print(block)
        return 0
    if not rows:
        print("(no matches)")
        return 0
    for r in rows:
        summ = (r.get("summary") or "").replace("\n", " ")
        if len(summ) > 110:
            summ = summ[:107] + "..."
        print(f"{r['score']:.4f}  [{r['namespace']}] {r['name']}")
        if summ:
            print(f"         {summ}")
        print(f"         {r['source_path']}")
    return 0


# ---------- stats ----------


def cmd_stats(args, cfg):
    if is_remote(cfg):
        return _ssh(cfg, ["_stats"])
    from . import store

    conn = store.connect(cfg["DATABASE_URL"])
    try:
        rows = store.stats(conn)
    finally:
        conn.close()
    total = sum(r[1] for r in rows)
    print(f"{'namespace':<16}{'facts':>8}{'embedded':>10}")
    for ns, cnt, emb in rows:
        print(f"{ns:<16}{cnt:>8}{emb:>10}")
    print(f"{'TOTAL':<16}{total:>8}")
    return 0


# ---------- doctor ----------


def cmd_doctor(args, cfg):
    # client gathers the laptop's filesystem view (which source files still exist)
    # so jns can detect drift; only cleanly-scanned namespaces are prune-eligible.
    if args.prune_missing and args.source:
        # a custom --source can be a subdir of the canonical root; pruning "missing"
        # against it would wipe the rest of the namespace. Only the default roots
        # (full scan) may drive --prune-missing.
        raise SystemExit(
            "--prune-missing cannot be combined with --source (use default roots)"
        )
    sources = _sources_from_args(args.source)
    parsed = P.build_records(sources)
    existing: dict = {}
    for r in parsed["records"]:
        existing.setdefault(r["namespace"], []).append(r["source_path"])
    payload = json.dumps(
        {
            "origin": P.current_origin(),
            "existing": existing,
            "scanned": parsed["prune_namespaces"],
            "prune_expired": args.prune_expired,
            "prune_missing": args.prune_missing,
            "json": args.json,
        }
    )
    if is_remote(cfg):
        return _ssh(cfg, ["_doctor"], stdin_data=payload)
    return _doctor(payload, cfg)


def _sanitize(s: str) -> str:
    # strip control chars so DB-derived names/paths can't injure the terminal/log
    return "".join(ch if ch.isprintable() else "?" for ch in str(s or ""))


def _doctor(payload, cfg):
    from . import store

    env = json.loads(payload)
    origin = env.get("origin") or "unknown"
    existing = env.get("existing", {})
    scanned = [n for n in env.get("scanned", []) if n in ALLOWED_NAMESPACES]
    allowed = sorted(ALLOWED_NAMESPACES)
    conn = store.connect(cfg["DATABASE_URL"])
    try:
        store.ensure_schema(conn)
        expired = store.expired_rows(conn, allowed)
        dups = store.duplicate_names(conn)
        drift = {
            ns: store.drift_rows(conn, origin, ns, existing.get(ns, []))
            for ns in scanned
        }
        pruned_expired = (
            store.prune_expired(conn, allowed) if env.get("prune_expired") else 0
        )
        pruned_missing = 0
        if env.get("prune_missing"):
            for ns in scanned:  # scanned => root present, fully read, >=1 file
                keep = existing.get(ns, [])
                if keep:
                    pruned_missing += store.delete_missing(conn, origin, ns, keep)
        conn.commit()
    finally:
        conn.close()

    report = {
        "expired": expired,
        "duplicates": dups,
        "drift": {k: v for k, v in drift.items() if v},
        "scanned_namespaces": scanned,
        "pruned_expired": pruned_expired,
        "pruned_missing": pruned_missing,
    }
    if env.get("json"):
        print(json.dumps(report, indent=2))
        return 0
    drift_total = sum(len(v) for v in report["drift"].values())
    print(
        f"expired: {len(expired)}   drift: {drift_total}   duplicate-names: {len(dups)}"
    )
    for e in expired:
        print(
            f"  EXPIRED [{e['namespace']}] {_sanitize(e['name'])} (expires {e['expires']})"
        )
    for ns, rows in report["drift"].items():
        for d in rows:
            print(
                f"  DRIFT   [{ns}] {_sanitize(d['name'])} — source gone: {_sanitize(d['source_path'])}"
            )
    for d in dups:
        print(f"  DUP     [{d['namespace']}] {_sanitize(d['name'])} x{d['count']}")
    if env.get("prune_expired") or env.get("prune_missing"):
        print(f"pruned: expired={pruned_expired} missing={pruned_missing}")
    return 0


# ---------- eval (recall quality) ----------


def cmd_eval(args, cfg):
    if is_remote(cfg):
        return _ssh(cfg, ["_eval"] + (["--json"] if args.json else []))
    return _eval_run(args.json, cfg)


def _eval_run(as_json, cfg):
    from . import embedder, eval_recall, store

    cache = cfg.get("FASTEMBED_CACHE")
    conn = store.connect(cfg["DATABASE_URL"])
    try:

        def search_fn(query, mode, k):
            qvec = embedder.embed_query(query, cache_dir=cache)
            return store.search(conn, qvec, text=query, k=k, mode=mode)

        result = eval_recall.score(search_fn)
    finally:
        conn.close()
    if as_json:
        print(json.dumps(result))
        return 0
    n = result["n"]
    print(f"recall eval over {n} pairs   (hit@k)")
    print(f"{'mode':<8}{'@1':>6}{'@3':>6}{'@5':>6}")
    for m in eval_recall.MODES:
        h = result[m]
        print(f"{m:<8}{h[1]:>6}{h[3]:>6}{h[5]:>6}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="coding-memory", description="Personal coding-memory store (jns)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser(
        "ingest", help="parse local markdown facts and (re)embed into the store"
    )
    g.add_argument(
        "--source",
        action="append",
        help="ns=path (repeatable); default = personal sources",
    )
    g.add_argument("--dry-run", action="store_true")

    q = sub.add_parser("query", help="semantic/hybrid recall")
    q.add_argument("text", nargs="+")
    q.add_argument("-k", type=int, default=8)
    q.add_argument("--mode", choices=["hybrid", "vector", "fts"], default="hybrid")
    q.add_argument("--namespace", action="append")
    q.add_argument(
        "--for-prompt",
        action="store_true",
        help="emit a relevance-gated recall block for injection into a phase prompt",
    )
    q.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="cosine threshold for --for-prompt (default: calibrated RECALL_MIN_SCORE)",
    )

    sub.add_parser("stats", help="row counts per namespace")

    d = sub.add_parser(
        "doctor", help="report freshness/expiry/drift/duplicates (+ optional prune)"
    )
    d.add_argument("--source", action="append")
    d.add_argument(
        "--prune-expired",
        action="store_true",
        help="delete rows past their expires date",
    )
    d.add_argument(
        "--prune-missing",
        action="store_true",
        help="delete drift rows in cleanly-scanned namespaces only",
    )
    d.add_argument("--json", action="store_true")

    ev = sub.add_parser(
        "eval", help="recall-quality scoreboard (fixed query/fact pairs)"
    )
    ev.add_argument("--json", action="store_true")

    # internal (server-side on jns)
    sub.add_parser("_embed-store")
    qq = sub.add_parser("_query")
    qq.add_argument("text", nargs="+")
    qq.add_argument("-k", type=int, default=8)
    qq.add_argument("--mode", choices=["hybrid", "vector", "fts"], default="hybrid")
    qq.add_argument("--namespace", action="append")
    qq.add_argument("--for-prompt", action="store_true")
    qq.add_argument("--min-score", type=float, default=None)
    sub.add_parser("_stats")
    sub.add_parser("_doctor")
    _ev = sub.add_parser("_eval")
    _ev.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = load_config()
    if args.cmd == "ingest":
        return cmd_ingest(args, cfg)
    if args.cmd == "query":
        return cmd_query(args, cfg)
    if args.cmd == "stats":
        return cmd_stats(args, cfg)
    if args.cmd == "doctor":
        return cmd_doctor(args, cfg)
    if args.cmd == "eval":
        return cmd_eval(args, cfg)
    if args.cmd == "_embed-store":
        return _embed_store(sys.stdin.read(), cfg)
    if args.cmd == "_query":
        return _query(" ".join(args.text).strip(), args, cfg)
    if args.cmd == "_stats":
        return cmd_stats(args, cfg)
    if args.cmd == "_doctor":
        return _doctor(sys.stdin.read(), cfg)
    if args.cmd == "_eval":
        return _eval_run(args.json, cfg)
    raise SystemExit(2)


if __name__ == "__main__":
    sys.exit(main())
