# systemd units (jns / Linux)

## `coding-memory-embed.service` — warm embedding service

Keeps the FastEmbed `nomic-embed-text-v1.5` model loaded on jns so
`bin/coding-memory query`/`ingest` skip the ~5s per-call cold start. Binds
**127.0.0.1 only** (never externally reachable). The CLI opts in by setting
`CODING_MEMORY_EMBED_URL=http://127.0.0.1:8788` in `~/.coding_memory.env`; if the
service is down, embedding falls back to the in-process model (no failure).

It uses `embedder._embed_local_*` directly, so it never calls itself.

### Deploy (on jns)

```bash
sudo cp ~/agents/claude-config/systemd/coding-memory-embed.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coding-memory-embed
systemctl status coding-memory-embed --no-pager
curl -s localhost:8788/health        # {"ok": true, ...}
```

Then add to `~/.coding_memory.env` on jns: `CODING_MEMORY_EMBED_URL=http://127.0.0.1:8788`.
