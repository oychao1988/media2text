# Removed — MLS-3 (#389)

The Node `m2t-agent-sidecar` package was **removed** in Monitor/Live simplify MLS-3.

Agent turns and streaming run in the Python API sidecar (`media2text serve`):

- `POST /api/agent/threads/{id}/turn`
- `WS /api/agent/stream?threadId=...`

Tauri only spawns the Python sidecar. See Hermes M2 (#182) and
[2026-07-06 monitor/live simplify spec](../../docs/superpowers/specs/2026-07-06-monitor-live-simplify-refactor-design.md).
