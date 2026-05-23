#!/usr/bin/env bash
# Prepare bundled-resource manifest for 转注 Work (P2).
# Full portable Node + openclaw npm download is deferred; this script pins versions only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/desktop/zhuanzhu-work/resources"
mkdir -p "$RES"

OPENCLAW_VERSION="${OPENCLAW_PIN:-2026.5.5}"
NODE_VERSION="${NODE_PIN:-22.14.0}"
GENERATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat >"$RES/bundle-manifest.json" <<EOF
{
  "generated_at": "$GENERATED_AT",
  "note": "Placeholder manifest. A future release will download portable Node and openclaw npm into resources/.",
  "pins": {
    "node": "$NODE_VERSION",
    "openclaw": "$OPENCLAW_VERSION"
  },
  "paths": {
    "node": "resources/node",
    "openclaw": "resources/openclaw"
  },
  "bundled": false
}
EOF

echo "Wrote $RES/bundle-manifest.json (node=$NODE_VERSION, openclaw=$OPENCLAW_VERSION)"
