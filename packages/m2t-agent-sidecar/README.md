# Deprecated — Hermes M2

The Node `m2t-agent-sidecar` package is **deprecated** as of Hermes M2 (#182).

Agent turns and streaming now run in the Python API sidecar:

- `POST /api/agent/threads/{id}/turn`
- `WS /api/agent/stream?threadId=...`

Tauri no longer spawns a Node agent process. This package is retained temporarily for reference and may be removed in a later milestone.
