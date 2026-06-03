#!/bin/zsh
# Start monitor watch daemon (single instance). Douyin live reflow needs system Playwright cache.
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
cd "$ROOT_DIR" || exit 1

LOCK_FILE="data/.monitor-watch.lock"

# Default: playwright install chromium cache (override by exporting before run)
: "${PLAYWRIGHT_BROWSERS_PATH:=$HOME/Library/Caches/ms-playwright}"
export PLAYWRIGHT_BROWSERS_PATH

# 清理残锁：进程已死但锁仍在
if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
        rm -f "$LOCK_FILE"
    fi
fi

exec .venv/bin/media2text monitor watch --daemon --json
