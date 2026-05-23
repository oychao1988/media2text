#!/usr/bin/env bash
# Benchmark OpenClaw Gateway chat latency (TTFB / TTFT / total).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/scripts/benchmark_chat_latency.py" "$@"
