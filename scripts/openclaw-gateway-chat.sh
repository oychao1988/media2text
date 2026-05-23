#!/usr/bin/env bash
# PoC: OpenClaw Gateway WebSocket chat.send (same path as 转注 Work L7).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MESSAGE="${1:-用一句话介绍你自己}"
RUNS="${RUNS:-1}"
MODE="${MODE:-fast}"
exec node "$ROOT/scripts/benchmark_chat_latency_ws.js" \
  --runs "$RUNS" \
  --mode "$MODE" \
  --message "$MESSAGE"
