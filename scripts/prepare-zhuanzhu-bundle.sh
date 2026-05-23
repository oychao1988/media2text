#!/usr/bin/env bash
# Download portable Node + openclaw npm + media2text site-packages for 转注 Work (P7).
# Slow network: export HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/desktop/zhuanzhu-work/resources"
NODE_VERSION="${NODE_PIN:-22.14.0}"
OPENCLAW_VERSION="${OPENCLAW_PIN:-2026.5.5}"
GENERATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

log() { printf '[prepare-bundle] %s\n' "$*"; }

detect_node_platform() {
  case "$(uname -s)" in
    Darwin)
      case "$(uname -m)" in
        arm64) echo "darwin-arm64" ;;
        x86_64) echo "darwin-x64" ;;
        *) echo "unsupported" >&2; return 1 ;;
      esac
      ;;
    Linux)
      case "$(uname -m)" in
        x86_64) echo "linux-x64" ;;
        aarch64 | arm64) echo "linux-arm64" ;;
        *) echo "unsupported" >&2; return 1 ;;
      esac
      ;;
    MINGW* | MSYS* | CYGWIN*)
      echo "win-x64"
      ;;
    *)
      echo "unsupported" >&2
      return 1
      ;;
  esac
}

download_node() {
  if [[ "${ZHUANZHU_SKIP_NODE_DOWNLOAD:-0}" == "1" ]]; then
    log "skip node download (ZHUANZHU_SKIP_NODE_DOWNLOAD=1)"
    return 0
  fi

  if [[ -n "${NODE_SOURCE:-}" && -d "$NODE_SOURCE" ]]; then
    log "copy Node from NODE_SOURCE=$NODE_SOURCE"
    rm -rf "$RES/node"
    mkdir -p "$RES/node"
    cp -R "$NODE_SOURCE"/. "$RES/node/"
    "$RES/node/bin/node" -v
    return 0
  fi

  local platform
  platform="$(detect_node_platform)"
  local archive="node-v${NODE_VERSION}-${platform}.tar.xz"
  local url="https://nodejs.org/dist/v${NODE_VERSION}/${archive}"
  local tmp
  tmp="$(mktemp -d)"

  log "download Node ${NODE_VERSION} (${platform})"
  if ! curl -fsSL --connect-timeout 30 --max-time 600 "$url" -o "$tmp/${archive}"; then
    log "download failed; set NODE_SOURCE to a Node prefix or retry with network"
    rm -rf "$tmp"
    return 1
  fi
  rm -rf "$RES/node"
  mkdir -p "$RES/node"
  tar -xJf "$tmp/${archive}" -C "$RES/node" --strip-components=1
  rm -rf "$tmp"
  "$RES/node/bin/node" -v
}

install_openclaw() {
  if [[ "${ZHUANZHU_SKIP_OPENCLAW_INSTALL:-0}" == "1" ]]; then
    log "skip openclaw install (ZHUANZHU_SKIP_OPENCLAW_INSTALL=1)"
    return 0
  fi

  local node_bin="$RES/node/bin/node"
  local npm_bin="$RES/node/bin/npm"
  if [[ ! -x "$node_bin" ]]; then
    log "bundled node missing; using PATH node for openclaw install"
    node_bin="$(command -v node)"
    npm_bin="$(command -v npm)"
  fi

  log "npm install openclaw@${OPENCLAW_VERSION} -> resources/openclaw"
  rm -rf "$RES/openclaw/node_modules" "$RES/openclaw/package.json" "$RES/openclaw/package-lock.json"
  mkdir -p "$RES/openclaw"
  "$npm_bin" install "openclaw@${OPENCLAW_VERSION}" --prefix "$RES/openclaw" --omit=dev --no-fund --no-audit --ignore-scripts
  if [[ -f "$RES/openclaw/node_modules/.bin/openclaw" ]]; then
    chmod +x "$RES/openclaw/node_modules/.bin/openclaw"
  fi
  PATH="$RES/node/bin:${PATH:-}" "$RES/openclaw/node_modules/.bin/openclaw" --version
}

bundle_media2text() {
  if [[ "${ZHUANZHU_SKIP_M2T_BUNDLE:-0}" == "1" ]]; then
    log "skip media2text bundle (ZHUANZHU_SKIP_M2T_BUNDLE=1)"
    return 0
  fi

  local py site="$RES/media2text/site-packages" bin="$RES/media2text/bin"
  py=""
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      py="$candidate"
      break
    fi
  done
  if [[ -z "$py" ]]; then
    log "python3.12+ not found; skip media2text bundle"
    return 0
  fi

  log "pip install media2text -> resources/media2text/site-packages (using $py)"
  rm -rf "$site"
  mkdir -p "$site" "$bin"
  "$py" -m pip install "$ROOT" --target "$site" --upgrade --no-warn-script-location

  cat >"$bin/media2text" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")/.." && pwd)"
export PYTHONPATH="\${ROOT}/site-packages\${PYTHONPATH:+:\${PYTHONPATH}}"
PY=""
for candidate in python3.13 python3.12 python3; do
  if command -v "\$candidate" >/dev/null 2>&1 &&
    "\$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PY="\$candidate"
    break
  fi
done
if [[ -z "\$PY" ]]; then
  echo "需要 Python 3.12+。请安装 python.org 或 brew install python@3.12。" >&2
  exit 1
fi
exec "\$PY" -c "from media2text.cli.main import app; app()" "\$@"
WRAP
  chmod +x "$bin/media2text"
  "$bin/media2text" version
}

write_manifest() {
  local bundled="false"
  local node_ok="false" openclaw_ok="false" m2t_ok="false"

  [[ -x "$RES/node/bin/node" ]] && node_ok="true"
  [[ -x "$RES/openclaw/node_modules/.bin/openclaw" ]] && openclaw_ok="true"
  [[ -x "$RES/media2text/bin/media2text" ]] && m2t_ok="true"
  if [[ "$node_ok" == "true" && "$openclaw_ok" == "true" && "$m2t_ok" == "true" ]]; then
    bundled="true"
  fi

  cat >"$RES/bundle-manifest.json" <<EOF
{
  "generated_at": "$GENERATED_AT",
  "note": "Portable Node + openclaw npm + media2text site-packages (P7). media2text wrapper uses system python3.",
  "pins": {
    "node": "$NODE_VERSION",
    "openclaw": "$OPENCLAW_VERSION"
  },
  "paths": {
    "node": "resources/node",
    "openclaw": "resources/openclaw",
    "media2text": "resources/media2text"
  },
  "components": {
    "node": $node_ok,
    "openclaw": $openclaw_ok,
    "media2text": $m2t_ok
  },
  "bundled": $bundled
}
EOF
  log "wrote $RES/bundle-manifest.json (bundled=$bundled)"
}

mkdir -p "$RES"
download_node
install_openclaw
bundle_media2text
write_manifest
