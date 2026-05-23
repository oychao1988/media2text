#!/usr/bin/env bash
# Verify bundled Node / openclaw / media2text without global CLI on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/desktop/zhuanzhu-work/resources"
NODE_BIN="$RES/node/bin/node"
OC_BIN="$RES/openclaw/node_modules/.bin/openclaw"
M2T_BIN="$RES/media2text/bin/media2text"

fail() { printf 'verify-bundle: FAIL %s\n' "$*" >&2; exit 1; }
ok() { printf 'verify-bundle: OK %s\n' "$*"; }

[[ -x "$NODE_BIN" ]] || fail "missing $NODE_BIN (run npm run prepare-bundle)"
[[ -x "$OC_BIN" ]] || fail "missing $OC_BIN"

ver="$("$NODE_BIN" -v)"
ok "node $ver"

export PATH="$RES/node/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
unset OPENCLAW_BIN 2>/dev/null || true
oc_ver="$("$OC_BIN" --version 2>&1 | head -1)"
ok "openclaw $oc_ver"

if [[ -x "$M2T_BIN" ]]; then
  m2t_ver="$("$M2T_BIN" version 2>&1 | tail -1)" || fail "media2text version failed"
  ok "media2text $m2t_ver"
else
  printf 'verify-bundle: WARN media2text bundle missing (optional if python3 absent at prepare time)\n'
fi

node -e "
const path = require('path');
const gw = require(path.join('$ROOT/desktop/zhuanzhu-work/lib/gateway.js'));
const bin = gw.resolveOpenClawBin('$RES');
if (!bin || !bin.includes('resources/openclaw')) {
  console.error('resolveOpenClawBin did not pick bundled openclaw:', bin);
  process.exit(1);
}
console.log('resolveOpenClawBin ->', bin);
"

ok "gateway.js resolves bundled openclaw"
