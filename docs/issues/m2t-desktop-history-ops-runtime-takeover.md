# m2t-desktop：历史手动摘要/重试 + 外部守护进程接管

## 背景

桌面端在使用历史列表与转写面板时出现三类问题：

1. **作品（VOD）同步/下载失败后无法重试**：`sync_status=failed` 的条目不会自动回到下载队列，历史列表缺少重试入口。
2. **后台摘要失败或无摘要时无法手动补跑**：转写已有但 `.summary.md` 缺失时，UI 无「生成摘要」；旧 sidecar 缺路由时按钮报 404。
3. **监控显示「外部 CLI 守护进程」**：用户曾在终端运行 `media2text monitor watch --daemon`，Desktop 内嵌 `MonitorSupervisor` 无法启停；需一键切回 Desktop 管理，并与 sidecar 同步启停。

**参考**

- Desktop Runtime：[desktop-runtime-design](../superpowers/specs/2026-06-05-desktop-runtime-design.md)
- 历史媒体操作：[m2t-desktop-history-media-ops.md](./m2t-desktop-history-media-ops.md)（#164）

## 验收标准

### API — 历史操作

- [ ] `POST /api/creators/{id}/history/{live|vod}/{item_id}/summarize` — 对已有转写的 live/VOD 手动跑 `summarize run` 语义；返回 `summarized` / `summary_path`；`summarize.enabled=false` 时明确错误
- [ ] `POST /api/creators/{id}/history/vod/{aweme_id}/retry-download` — 将 `failed` 作品重置为 `listed` 并触发下载队列
- [ ] `AwemeRepo.reset_failed_to_listed(creator_id)` 仅影响该博主 `failed` 行
- [ ] `GET /api/sessions/{id}/summary` — 无摘要文件时 **200 + 空 text**（非 404），避免 UI 误判为 API 缺失
- [ ] `/api/health` 的 `api_features` 含 `history_summarize`、`history_retry_download`，供 sidecar 版本探测

### API — Runtime 接管

- [ ] `MonitorSupervisor.stop_external()` — SIGTERM/SIGKILL 终止锁文件中的外部 CLI PID，并清理 `.monitor-watch.lock`
- [ ] `POST /api/runtime/takeover` — 停外部 → 启动 embedded；成功后 `managed_by=embedded`
- [ ] `start_runtime` / `takeover_runtime` 启动后调用 `recover_stale_work` 重置卡死的 `monitor_tasks`
- [ ] embedded serve 日志写 devnull，避免 Tauri 管道 Broken pipe

### 前端

- [ ] **HistoryPanel**：VOD `failed` 显示「重试」→ `retry-download`
- [ ] **TranscriptPane**：有转写、无摘要（或 force）时显示「生成摘要 / 重新摘要」；sidecar 过旧时提示重启 Desktop
- [ ] **DaemonCard**：`managed_by=external` 时显示「改用 Desktop 管理」→ `POST /api/runtime/takeover`；文案「终端独立进程（非 Desktop）」
- [ ] **RuntimeContext**：暴露 `takeoverRuntime`；外部运行时 start 返回 409 含可读提示
- [ ] **python_sidecar**：health `api_features` 不匹配时强制重启 sidecar（dev 可 `force_restart`）

### 测试

- [ ] `pytest tests/unit/test_api_history_media.py tests/unit/test_api_runtime.py tests/unit/test_api_sessions.py tests/unit/test_monitor_supervisor.py tests/unit/test_logging_embedded.py -v -m desktop`
- [ ] `pnpm --filter m2t-desktop test`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_api_history_media.py tests/unit/test_api_runtime.py \
  tests/unit/test_api_sessions.py tests/unit/test_monitor_supervisor.py \
  tests/unit/test_logging_embedded.py -v -m desktop
pnpm --filter m2t-desktop test

# 手工
media2text serve --port 8765
# 1) 选一 failed VOD → 历史「重试」
# 2) 有转写无摘要 → 转写面板「生成摘要」
# 3) 若曾 nohup monitor watch --daemon → DaemonCard「改用 Desktop 管理」
# config.yaml: desktop.auto_start_monitor: true  → 随 Desktop 自动启停
```

## 非目标范围

- 批量重试全部 failed VOD
- VOD 下载完成后自动摘要（仍走现有 post-process / 手动）
- 删除或禁止 CLI `monitor watch --daemon`（仅 Desktop 可接管）
- 修改 `summarize` CLI 子命令行为

## 实现备注

- GitHub Issue: [#166](https://github.com/oychao1988/media2text/issues/166)
- 分支：`issue-166-desktop-history-ops-runtime`
