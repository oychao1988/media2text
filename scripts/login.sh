#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  echo "Creating venv..."
  python3.12 -m venv .venv
fi

source .venv/bin/activate
pip install -q -e ".[dev,transcribe]"
playwright install chromium

media2text doctor --json || true

echo ""
echo "=========================================="
echo "  即将打开浏览器，请用抖音 App 扫码登录"
echo "  登录成功后回到终端按 Enter"
echo "=========================================="
echo ""

media2text auth login --platform douyin

media2text doctor --json
media2text auth status --json
