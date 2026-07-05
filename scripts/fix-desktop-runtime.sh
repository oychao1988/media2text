#!/usr/bin/env bash
# Hotfix materialized desktop runtime (venv paths + latest src + python-socks).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$HOME/Library/Application Support/dev.media2text.desktop/runtime/m2t-runtime"
OLD="$ROOT/apps/m2t-desktop/src-tauri/resources/m2t-runtime"
BUNDLED="/Applications/灵犀.app/Contents/Resources/m2t-runtime"

rewrite_text_file() {
  local file="$1"
  local from="$2"
  local to="$3"
  [[ -f "$file" ]] || return 0
  python3 - <<PY
from pathlib import Path
path = Path(${file@Q})
text = path.read_text(encoding="utf-8", errors="ignore")
updated = text.replace(${from@Q}, ${to@Q})
if updated != text:
    path.write_text(updated, encoding="utf-8")
PY
}

if [[ ! -d "$RUNTIME/.venv" ]]; then
  echo "runtime not found at $RUNTIME — launch 灵犀 once first" >&2
  exit 1
fi

echo "==> sync source"
mkdir -p "$RUNTIME/src/media2text"
rsync -a --delete "$ROOT/src/media2text/" "$RUNTIME/src/media2text/"

echo "==> rewrite venv text paths"
for prefix in "$OLD" "$BUNDLED"; do
  rewrite_text_file "$RUNTIME/.venv/pyvenv.cfg" "$prefix" "$RUNTIME"
  rewrite_text_file "$RUNTIME/.venv/pyvenv.cfg" "$prefix/.venv" "$RUNTIME/.venv"
done
echo "$RUNTIME/src" > "$RUNTIME/.venv/lib/python3.12/site-packages/_editable_impl_media2text.pth"
for script in "$RUNTIME/.venv/bin/"*; do
  [[ -f "$script" ]] || continue
  head -1 "$script" | grep -q '^#!' || continue
  for prefix in "$OLD" "$BUNDLED"; do
    rewrite_text_file "$script" "$prefix" "$RUNTIME"
  done
done

echo "==> install python-socks"
"$RUNTIME/.venv/bin/python3" -m pip install -q 'python-socks[asyncio]>=2.0'

echo "==> verify"
"$RUNTIME/.venv/bin/python3" -c "import media2text.core.proxy_env; import python_socks; print('ok')"

echo "Done. Restart 灵犀 to apply."
