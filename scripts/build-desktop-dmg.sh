#!/usr/bin/env bash
# Build a self-contained macOS DMG for 灵犀 (m2t-desktop).
# Bundles Python runtime into Resources/m2t-runtime before `tauri build`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT/apps/m2t-desktop/src-tauri/resources/m2t-runtime"
PYTHON="${PYTHON:-python3.12}"

echo "==> Preparing bundled Python runtime at $RUNTIME_DIR"
rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"

cp "$ROOT/pyproject.toml" "$ROOT/README.md" "$RUNTIME_DIR/"
cp -R "$ROOT/src" "$RUNTIME_DIR/"
cp "$ROOT/config.example.yaml" "$RUNTIME_DIR/config.example.yaml"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found (set PYTHON=... or install Python 3.12+)" >&2
  exit 1
fi

"$PYTHON" -m venv "$RUNTIME_DIR/.venv"
# shellcheck disable=SC1091
source "$RUNTIME_DIR/.venv/bin/activate"
python -m pip install -U pip wheel
python -m pip install "$RUNTIME_DIR[desktop,transcribe-deepgram]"

mkdir -p "$RUNTIME_DIR/bin"
if command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG_SRC="$(command -v ffmpeg)"
  cp "$FFMPEG_SRC" "$RUNTIME_DIR/bin/ffmpeg.bin"
  chmod 644 "$RUNTIME_DIR/bin/ffmpeg.bin"
  xattr -cr "$RUNTIME_DIR/bin/ffmpeg.bin" 2>/dev/null || true
  echo "==> Bundled ffmpeg from $FFMPEG_SRC (as bin/ffmpeg.bin)"
else
  echo "warning: ffmpeg not found in PATH — 打包前请安装 ffmpeg（macOS: brew install ffmpeg）" >&2
fi

echo "==> Runtime ready ($(du -sh "$RUNTIME_DIR" | awk '{print $1}'))"
echo "==> Building Tauri app (DMG name follows productName: 灵犀)"
cd "$ROOT/apps/m2t-desktop"
pnpm tauri build --config src-tauri/tauri.release.conf.json --bundles app

BUNDLE_DIR="$ROOT/apps/m2t-desktop/src-tauri/target/release/bundle/macos"
if [[ ! -d "$BUNDLE_DIR/灵犀.app" ]]; then
  APP_PATH="$(find "$ROOT/apps/m2t-desktop/src-tauri" /var/folders "$HOME" -path '*/release/bundle/macos/灵犀.app' -print 2>/dev/null | head -1)"
  if [[ -n "${APP_PATH:-}" ]]; then
    BUNDLE_DIR="$(dirname "$APP_PATH")"
  fi
fi

if [[ ! -d "$BUNDLE_DIR/灵犀.app" ]]; then
  echo "error: 灵犀.app not found after tauri build" >&2
  exit 1
fi

OUT_DIR="$ROOT/dist/desktop"
mkdir -p "$OUT_DIR"
DMG_PATH="$OUT_DIR/灵犀_0.1.0_x64.dmg"
rm -f "$DMG_PATH"
echo "==> Creating DMG at $DMG_PATH"
hdiutil create -volname "灵犀" -srcfolder "$BUNDLE_DIR/灵犀.app" -ov -format UDZO "$DMG_PATH"

echo
echo "Install DMG, then put API keys in:"
echo "  ~/Library/Application Support/dev.media2text.desktop/.env"
echo "First launch also seeds config.yaml in the same folder."
echo "Run once: playwright install chromium  (if not already installed)"
