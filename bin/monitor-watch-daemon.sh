#!/bin/zsh
# Start monitor watch daemon (single instance). Douyin live reflow needs system Playwright cache.
set -euo pipefail

ROOT_DIR="${0:A:h:h}"
cd "$ROOT_DIR" || exit 1

LOCK_FILE="data/.monitor-watch.lock"

# Default: playwright install chromium cache (override by exporting before run)
: "${PLAYWRIGHT_BROWSERS_PATH:=$HOME/Library/Caches/ms-playwright}"
export PLAYWRIGHT_BROWSERS_PATH

# 清理残锁：PID 非 monitor watch 或进程已死
.venv/bin/python -c "
from pathlib import Path
from media2text.core.runtime.monitor_lock import clear_invalid_monitor_lock
clear_invalid_monitor_lock(Path('data/.monitor-watch.lock'))
"

exec .venv/bin/media2text monitor watch --daemon --json
