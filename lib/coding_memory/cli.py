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
import shlex
import subprocess
import sys

from . import DEFAULT_SOURCES, is_remote, load_config
from . import parse as P


def _sources_from_args(pairs):
    if not pairs:
        return dict(DEFAULT_SOURCES)
    out = {}
    for item in pairs:
        ns, _, path = item.partition("=")
        if not path:
            raise SystemExit(f"--source expects ns=path, got: {item}")
        out[ns.strip()] = path.strip()
    return out


def _ssh(cfg, remote_args, stdin_data=None):
    host = cfg["CODING_MEMORY_SSH"]
    remote = f"{cfg['CODING_MEMORY_REMOTE_BIN']} " + " ".join(
        shlex.quote(a) for a in remote_args
    )
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
    records = P.build_records(sources)
    print(
        f"parsed {len(records)} fact(s) from {len(sources)} namespace(s): {', '.join(sources)}",
        file=sys.stderr,
    )
    if args.dry_run:
        for r in records:
            print(f"  [{r['namespace']}] {r['name']}  ({r['source_path']})")
        return 0
    ndjson = "\n".join(json.dumps(r) for r in records)
    if is_remote(cfg):
        return _ssh(cfg, ["_embed-store"], stdin_data=ndjson)
    return _embed_store(ndjson, cfg)


def _embed_store(ndjson, cfg):
    from . import embedder, store

    records = [json.loads(line) for line in ndjson.splitlines() if line.strip()]
    cache = cfg.get("FASTEMBED_CACHE")
    conn = store.connect(cfg["DATABASE_URL"])
    try:
        store.ensure_schema(conn)
        namespaces = sorted({r["namespace"] for r in records})
        existing = store.existing_hashes(conn, namespaces)
        changed = [
            r
            for r in records
            if existing.get((r["namespace"], r["source_path"])) != r["content_hash"]
        ]
        report = {
            "parsed": len(records),
            "changed": len(changed),
            "unchanged": len(records) - len(changed),
        }
        if changed:
            vecs = embedder.embed_docs(
                [P.embed_text(r) for r in changed], cache_dir=cache
            )
            for r, v in zip(changed, vecs):
                store.upsert(conn, r, v)
        # prune rows whose source file disappeared
        pruned = 0
        for ns in namespaces:
            keep = [r["source_path"] for r in records if r["namespace"] == ns]
            pruned += store.delete_missing(conn, ns, keep)
        conn.commit()
        report["pruned"] = pruned
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
        for ns in args.namespace or []:
            remote += ["--namespace", ns]
        remote += ["--", text]
        return _ssh(cfg, remote)
    return _query(text, args, cfg)


def _query(text, args, cfg):
    from . import embedder, store

    cache = cfg.get("FASTEMBED_CACHE")
    qvec = embedder.embed_query(text, cache_dir=cache)
    conn = store.connect(cfg["DATABASE_URL"])
    try:
        rows = store.search(
            conn,
            qvec,
            text=text,
            k=args.k,
            namespaces=args.namespace or None,
            mode=args.mode,
        )
    finally:
        conn.close()
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

    sub.add_parser("stats", help="row counts per namespace")

    # internal (server-side on jns)
    sub.add_parser("_embed-store")
    qq = sub.add_parser("_query")
    qq.add_argument("text", nargs="+")
    qq.add_argument("-k", type=int, default=8)
    qq.add_argument("--mode", choices=["hybrid", "vector", "fts"], default="hybrid")
    qq.add_argument("--namespace", action="append")
    sub.add_parser("_stats")
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
    if args.cmd == "_embed-store":
        return _embed_store(sys.stdin.read(), cfg)
    if args.cmd == "_query":
        return _query(" ".join(args.text).strip(), args, cfg)
    if args.cmd == "_stats":
        return cmd_stats(args, cfg)
    raise SystemExit(2)


if __name__ == "__main__":
    sys.exit(main())
