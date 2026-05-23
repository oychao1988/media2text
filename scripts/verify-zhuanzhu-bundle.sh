#!/usr/bin/env bash
# Verify bundled runtime (archive tar.gz or expanded dirs).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/desktop/zhuanzhu-work/resources"
RUNTIME_MODE="${ZHUANZHU_RUNTIME_MODE:-archive}"
TAR=""

fail() { printf 'verify-bundle: FAIL %s\n' "$*" >&2; exit 1; }
ok() { printf 'verify-bundle: OK %s\n' "$*"; }

VERIFY_ROOT=""
cleanup() {
  if [[ -n "${TMP_EXTRACT:-}" && -d "$TMP_EXTRACT" ]]; then
    rm -rf "$TMP_EXTRACT"
  fi
}
trap cleanup EXIT

if [[ "$RUNTIME_MODE" == "archive" ]]; then
  TAR="$RES/runtime-bundle.tar.gz"
  VER="$RES/runtime-bundle.version"
  [[ -f "$TAR" ]] || fail "missing $TAR (run npm run prepare-bundle)"
  [[ -f "$VER" ]] || fail "missing $VER"
  TMP_EXTRACT="$(mktemp -d)"
  tar -xzf "$TAR" -C "$TMP_EXTRACT"
  VERIFY_ROOT="$TMP_EXTRACT"
  ok "extracted runtime-bundle.tar.gz ($(tr -d '[:space:]' <"$VER"))"
else
  VERIFY_ROOT="$RES"
fi

NODE_BIN="$VERIFY_ROOT/node/bin/node"
OC_BIN="$VERIFY_ROOT/openclaw/node_modules/.bin/openclaw"
M2T_BIN="$VERIFY_ROOT/media2text/bin/media2text"

[[ -x "$NODE_BIN" ]] || fail "missing $NODE_BIN"
[[ -x "$OC_BIN" ]] || fail "missing $OC_BIN"

ver="$("$NODE_BIN" -v)"
ok "node $ver"

export PATH="$VERIFY_ROOT/node/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
unset OPENCLAW_BIN 2>/dev/null || true
oc_ver="$("$OC_BIN" --version 2>&1 | head -1)"
ok "openclaw $oc_ver"

if [[ -x "$M2T_BIN" ]]; then
  m2t_ver="$("$M2T_BIN" version 2>&1 | tail -1)" || fail "media2text version failed"
  ok "media2text $m2t_ver"
else
  printf 'verify-bundle: WARN media2text bundle missing (optional if python3 absent at prepare time)\n'
fi

if [[ -f "$TAR" ]]; then
  tar_size="$(du -sh "$TAR" 2>/dev/null | awk '{print $1}')"
  ok "runtime-bundle.tar.gz size ${tar_size:-unknown}"
fi

node -e "
const path = require('path');
const gw = require(path.join('$ROOT/desktop/zhuanzhu-work/lib/gateway.js'));
const bin = gw.resolveOpenClawBin('$VERIFY_ROOT');
if (!bin || !bin.includes('openclaw')) {
  console.error('resolveOpenClawBin did not pick bundled openclaw:', bin);
  process.exit(1);
}
console.log('resolveOpenClawBin ->', bin);
"

ok "gateway.js resolves bundled openclaw"
