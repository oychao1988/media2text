#!/usr/bin/env bash
# Benchmark OpenClaw Gateway chat latency over WebSocket (TTFT vs HTTP baseline).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec node "$ROOT/scripts/benchmark_chat_latency_ws.js" "$@"
