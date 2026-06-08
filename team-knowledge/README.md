# Moved → KnowledgeMesh

This project was extracted into its own repository on 2026-06-07 (lineage `agents@e9e1348`):

- **Repo:** https://github.com/jwj2002/knowledgemesh
- **Local:** `~/projects/knowledgemesh`
- **Renamed:** Team Knowledge Hub → **KnowledgeMesh**

The hub (patterns / private review / shareable components) and its specs
(`knowledgemesh-mvp-v1.md`, `telemetry-validation.md`, `knowledge-surfaces.md`) live there now.

**What stays here in `~/agents`:** the SENSE-layer sensors that feed the hub —
`claude-config/scripts/{defect_tracer,positive_signal_sensor,watchdog,telemetry_gate}.py`
and the fleet usage-monitor — per the SENSE→TARGET→INVEST split (telemetry is the sensor,
generated per-host; KnowledgeMesh is the TARGET/INVEST hub that consumes the outputs).
