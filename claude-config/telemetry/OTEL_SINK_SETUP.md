# OTEL → readable token-usage sink (issue #230, telemetry-validation §1.1/§1.5)

Claude Code **pushes** `claude_code.token.usage` over OTEL; it is not in a file by default. This is
the "sleeper" prerequisite: stand up a local **OTLP file sink** so the token collector (#231) can
read cache-aware cost. The *code* that reads the sink + computes cost + alarms on staleness lives in
`claude-config/scripts/otel_sink.py` (host-agnostic, tested against simulated pushes). This doc is
the *deploy recipe* — the live wiring is per-host.

## 1. Enable Claude Code OTEL export (env, per host)
```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc          # or http/protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

## 2. Run a collector with a file exporter (the sink producer)
Claude Code emits OTLP → a local **otel-collector** maps it to the readable JSONL sink. Minimal
`otelcol` config:
```yaml
receivers:
  otlp: { protocols: { grpc: { endpoint: localhost:4317 } } }
exporters:
  file: { path: ${HOME}/.claude/telemetry/otel.jsonl }   # the sink read by otel_sink.py
service:
  pipelines:
    metrics: { receivers: [otlp], exporters: [file] }
```
The sink is normalized JSONL of usage records `{ts, session_id, model, input, output,
cache_creation, cache_read}`. If the collector emits raw OTLP datapoints instead, map them with
`otel_sink.normalize_from_datapoints(...)` (a thin shim or a collector transform) before the file
exporter — that mapping is implemented + tested in `otel_sink.py`.

## 3. Sink location
Default: `~/.claude/telemetry/otel.jsonl`. Append-only; the collector (single writer per host) keeps
it append-safe. `otel_sink.read_sink()` skips partial/corrupt lines and **errors loudly on a missing
sink** (never a silent empty read).

## 4. Freshness alarm
`otel_sink.check_exporter_freshness(path, now_ts, sla_seconds=24h)` returns the stale-exporter alarm
state (§0.1) — wired into the watchdog (#232). `sink_missing` and `stale_exporter` are distinct
alarm reasons.

## Host notes / deferred (no server-a)
- **macOS (scratch):** run the collector via `launchd`; paths as above. This host can be validated
  end-to-end locally.
- **Linux (jns-server):** run the collector via `systemd`; same env + config. **DEPLOY + LIVE
  VALIDATION ON jns-server IS DEFERRED** until server-a is reachable — the code + simulated-push
  tests are complete and host-agnostic, but a real Claude-Code-session → sink confirmation on Linux
  has not been run. This is a deploy task, not a code gap. (And per §0.1, a host whose sink goes
  stale/missing is *itself* the fleet alarm — exactly the current server-a situation.)
