#!/usr/bin/env bash
# Download portable Node + openclaw npm + media2text site-packages for 转注 Work (P7/P9).
# P9: stage → prune → runtime-bundle.tar.gz (+ optional expanded dirs for dev).
# Slow network: export HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/desktop/zhuanzhu-work/resources"
NODE_VERSION="${NODE_PIN:-22.14.0}"
OPENCLAW_VERSION="${OPENCLAW_PIN:-2026.5.5}"
GENERATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
RUNTIME_MODE="${ZHUANZHU_RUNTIME_MODE:-archive}"
M2T_SLIM="${ZHUANZHU_M2T_SLIM:-1}"

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

download_node_to() {
  local dest="$1"
  if [[ "${ZHUANZHU_SKIP_NODE_DOWNLOAD:-0}" == "1" ]]; then
    if [[ -d "$RES/node/bin" && -x "$RES/node/bin/node" ]]; then
      log "skip node download: copy from resources/node (ZHUANZHU_SKIP_NODE_DOWNLOAD=1)"
      rm -rf "$dest"
      mkdir -p "$dest"
      cp -R "$RES/node"/. "$dest/"
      "$dest/bin/node" -v
      return 0
    fi
    log "skip node download (ZHUANZHU_SKIP_NODE_DOWNLOAD=1) but no resources/node"
    return 0
  fi

  if [[ -n "${NODE_SOURCE:-}" && -d "$NODE_SOURCE" ]]; then
    log "copy Node from NODE_SOURCE=$NODE_SOURCE"
    rm -rf "$dest"
    mkdir -p "$dest"
    cp -R "$NODE_SOURCE"/. "$dest/"
    "$dest/bin/node" -v
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
  rm -rf "$dest"
  mkdir -p "$dest"
  tar -xJf "$tmp/${archive}" -C "$dest" --strip-components=1
  rm -rf "$tmp"
  "$dest/bin/node" -v
}

prune_node_bundle() {
  local node_dir="$1"
  if [[ ! -d "$node_dir" ]]; then
    return 0
  fi

  log "prune bundled node (runtime only; drop nvm global modules & headers)"
  rm -rf "$node_dir/lib/node_modules"
  rm -rf "$node_dir/include"
  rm -f "$node_dir/README.md" "$node_dir/CHANGELOG.md" "$node_dir/LICENSE"

  if [[ -d "$node_dir/bin" ]]; then
    while IFS= read -r -d '' entry; do
      base="$(basename "$entry")"
      case "$base" in
        node | npm | npx) ;;
        *) rm -rf "$entry" ;;
      esac
    done < <(find "$node_dir/bin" -mindepth 1 -maxdepth 1 -print0 2>/dev/null || true)
  fi

  local size
  size="$(du -sh "$node_dir" 2>/dev/null | awk '{print $1}')"
  log "node bundle size after prune: ${size:-unknown}"
}

install_openclaw_to() {
  local dest="$1"
  local node_bin="$2/bin/node"
  local npm_bin="$2/bin/npm"

  if [[ "${ZHUANZHU_SKIP_OPENCLAW_INSTALL:-0}" == "1" ]]; then
    log "skip openclaw install (ZHUANZHU_SKIP_OPENCLAW_INSTALL=1)"
    return 0
  fi

  if [[ ! -x "$node_bin" ]]; then
    node_bin="$(command -v node)"
    npm_bin="$(command -v npm)"
  fi

  log "npm install openclaw@${OPENCLAW_VERSION} -> $dest"
  rm -rf "$dest/node_modules" "$dest/package.json" "$dest/package-lock.json"
  mkdir -p "$dest"
  "$npm_bin" install "openclaw@${OPENCLAW_VERSION}" --prefix "$dest" --omit=dev --no-fund --no-audit --ignore-scripts
  if [[ -f "$dest/node_modules/.bin/openclaw" ]]; then
    chmod +x "$dest/node_modules/.bin/openclaw"
  fi
  PATH="$2/bin:${PATH:-}" "$dest/node_modules/.bin/openclaw" --version
}

prune_openclaw_bundle() {
  local oc="$1"
  local node_prefix="${2:-}"
  if [[ ! -d "$oc/node_modules" ]]; then
    return 0
  fi

  log "prune openclaw bundle (drop tests, docs, source maps)"
  while IFS= read -r -d '' dir; do
    rm -rf "$dir"
  done < <(find "$oc" -type d \( -name test -o -name tests -o -name __tests__ -o -name .github \) -print0 2>/dev/null || true)
  find "$oc" -type f \( -name '*.md' -o -name '*.markdown' -o -name '*.map' -o -name '*.ts' -o -name '*.flow' \) ! -name 'LICENSE*' -delete 2>/dev/null || true

  local npm_bin=""
  if [[ -n "$node_prefix" && -x "$node_prefix/bin/npm" ]]; then
    npm_bin="$node_prefix/bin/npm"
  elif [[ -x "$RES/node/bin/npm" ]]; then
    npm_bin="$RES/node/bin/npm"
  elif command -v npm >/dev/null 2>&1; then
    npm_bin="$(command -v npm)"
  fi
  if [[ -n "$npm_bin" ]]; then
    "$npm_bin" prune --omit=dev --prefix "$oc" 2>/dev/null || true
  fi

  local size
  size="$(du -sh "$oc" 2>/dev/null | awk '{print $1}')"
  log "openclaw bundle size after prune: ${size:-unknown}"
}

bundle_media2text_to() {
  local dest="$1"
  if [[ "${ZHUANZHU_SKIP_M2T_BUNDLE:-0}" == "1" ]]; then
    log "skip media2text bundle (ZHUANZHU_SKIP_M2T_BUNDLE=1)"
    return 0
  fi

  local py site="$dest/site-packages" bin="$dest/bin"
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

  rm -rf "$site"
  mkdir -p "$site" "$bin"

  if [[ "$M2T_SLIM" == "1" ]]; then
    log "pip install media2text (slim, playwright package without browser driver) -> $site (using $py)"
    "$py" -m pip install "$ROOT" --target "$site" --upgrade --no-warn-script-location --no-deps
    "$py" -m pip install \
      "typer>=0.12" "pydantic>=2.6" "pydantic-settings>=2.2" "httpx>=0.27" \
      "playwright>=1.42" \
      "structlog>=24.1" "pyyaml>=6.0" "python-dotenv>=1.0" \
      --target "$site" --upgrade --no-warn-script-location
    rm -rf "$site/playwright/driver" "$site/playwright/drivers" 2>/dev/null || true
  else
    log "pip install media2text (full) -> $site (using $py)"
    "$py" -m pip install "$ROOT" --target "$site" --upgrade --no-warn-script-location
  fi

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

  local size
  size="$(du -sh "$dest" 2>/dev/null | awk '{print $1}')"
  log "media2text bundle size: ${size:-unknown}"
}

write_stage_manifest() {
  local stage="$1"
  cat >"$stage/manifest.json" <<EOF
{
  "generated_at": "$GENERATED_AT",
  "layout": "archive",
  "pins": {
    "node": "$NODE_VERSION",
    "openclaw": "$OPENCLAW_VERSION",
    "media2text_slim": $([[ "$M2T_SLIM" == "1" ]] && echo "true" || echo "false")
  }
}
EOF
}

archive_runtime_bundle() {
  local stage="$1"
  write_stage_manifest "$stage"

  local tar_path="$RES/runtime-bundle.tar.gz"
  local version_path="$RES/runtime-bundle.version"

  log "create runtime-bundle.tar.gz"
  rm -f "$tar_path"
  tar -czf "$tar_path" -C "$stage" .

  local hash
  hash="$(shasum -a 256 "$tar_path" | awk '{print substr($1,1,12)}')"
  echo "$hash" >"$version_path"

  local tar_size
  tar_size="$(du -sh "$tar_path" 2>/dev/null | awk '{print $1}')"
  log "runtime-bundle.tar.gz size: ${tar_size:-unknown} (hash=$hash)"
}

write_manifest() {
  local bundled="false"
  local node_ok="false" openclaw_ok="false" m2t_ok="false"
  local layout="expanded"
  local hash=""

  if [[ -f "$RES/runtime-bundle.tar.gz" && -f "$RES/runtime-bundle.version" ]]; then
    layout="archive"
    hash="$(tr -d '[:space:]' <"$RES/runtime-bundle.version")"
    bundled="true"
  fi

  if [[ -d "$RES/node/bin" && -x "$RES/node/bin/node" ]]; then
    node_ok="true"
  elif [[ -f "$RES/runtime-bundle.tar.gz" ]]; then
    node_ok="true"
  fi

  if [[ -x "$RES/openclaw/node_modules/.bin/openclaw" ]]; then
    openclaw_ok="true"
  elif [[ -f "$RES/runtime-bundle.tar.gz" ]]; then
    openclaw_ok="true"
  fi

  if [[ -x "$RES/media2text/bin/media2text" ]]; then
    m2t_ok="true"
  elif [[ -f "$RES/runtime-bundle.tar.gz" ]]; then
    m2t_ok="true"
  fi

  if [[ "$node_ok" == "true" && "$openclaw_ok" == "true" && "$m2t_ok" == "true" ]]; then
    bundled="true"
  fi

  cat >"$RES/bundle-manifest.json" <<EOF
{
  "generated_at": "$GENERATED_AT",
  "note": "P9 archive: runtime-bundle.tar.gz extracted on first launch to userData/runtime/{hash}/.",
  "layout": "$layout",
  "archive_hash": "$hash",
  "pins": {
    "node": "$NODE_VERSION",
    "openclaw": "$OPENCLAW_VERSION",
    "media2text_slim": $([[ "$M2T_SLIM" == "1" ]] && echo "true" || echo "false")
  },
  "paths": {
    "archive": "resources/runtime-bundle.tar.gz",
    "runtime_version": "resources/runtime-bundle.version",
    "extracted": "userData/runtime/$hash"
  },
  "components": {
    "node": $node_ok,
    "openclaw": $openclaw_ok,
    "media2text": $m2t_ok
  },
  "bundled": $bundled
}
EOF
  log "wrote $RES/bundle-manifest.json (layout=$layout bundled=$bundled)"
}

mkdir -p "$RES"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

download_node_to "$STAGE/node"
prune_node_bundle "$STAGE/node"

if [[ "${ZHUANZHU_SKIP_OPENCLAW_INSTALL:-0}" == "1" && -d "$RES/openclaw/node_modules" ]]; then
  log "copy openclaw from existing resources/openclaw (ZHUANZHU_SKIP_OPENCLAW_INSTALL=1)"
  rm -rf "$STAGE/openclaw"
  cp -R "$RES/openclaw" "$STAGE/openclaw"
else
  install_openclaw_to "$STAGE/openclaw" "$STAGE/node"
fi
prune_openclaw_bundle "$STAGE/openclaw" "$STAGE/node"
bundle_media2text_to "$STAGE/media2text"

if [[ "$RUNTIME_MODE" == "archive" ]]; then
  archive_runtime_bundle "$STAGE"
  rm -rf "$RES/node" "$RES/openclaw" "$RES/media2text"
  if [[ "${ZHUANZHU_KEEP_EXPANDED:-0}" == "1" ]]; then
    log "ZHUANZHU_KEEP_EXPANDED=1: also copy expanded dirs to resources/"
    cp -R "$STAGE/node" "$RES/node"
    cp -R "$STAGE/openclaw" "$RES/openclaw"
    cp -R "$STAGE/media2text" "$RES/media2text"
  fi
else
  log "ZHUANZHU_RUNTIME_MODE=expanded: copy staged dirs to resources/ (no tar.gz)"
  rm -rf "$RES/node" "$RES/openclaw" "$RES/media2text" "$RES/runtime-bundle.tar.gz" "$RES/runtime-bundle.version"
  cp -R "$STAGE/node" "$RES/node"
  cp -R "$STAGE/openclaw" "$RES/openclaw"
  cp -R "$STAGE/media2text" "$RES/media2text"
fi

write_manifest
