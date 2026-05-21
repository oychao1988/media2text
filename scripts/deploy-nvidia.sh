#!/bin/bash
# nvidia 服务器 media2text 部署与启动脚本
set -e

export PATH="$HOME/miniforge3/envs/media2text/bin:$PATH"
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium-browser

cd ~/media2text

case "${1:-help}" in
  doctor)
    media2text doctor --json
    ;;
  login)
    media2text auth login --platform douyin
    ;;
  status)
    media2text auth status --json
    ;;
  watch)
    shift
    media2text monitor watch "$@"
    ;;
  shell)
    echo "media2text env activated. Use 'media2text <command>'"
    exec $SHELL
    ;;
  help|*)
    echo "用法: $0 <command>"
    echo "  doctor   - 环境自检"
    echo "  login    - 抖音登录"
    echo "  status   - 登录状态"
    echo "  watch    - 启动监控 (media2text monitor watch)"
    echo "  shell    - 进入 conda 环境"
    media2text --help
    ;;
esac
