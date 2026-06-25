---
issue: 335
epic: monitor-db-contention-2026-06-25
github: 335
branch: issue-335-monitor-db-mp2-single-owner
depends_on: [334]
---

# MP-2：Monitor 单 owner 锁语义 + Desktop/CLI 共存策略

GitHub Issue: [#335](https://github.com/oychao1988/media2text/issues/335)  
Epic：**Monitor DB Contention**（2026-06-25）  
系列：MP-1 → **MP-2** → MP-3

## 背景

事故环境中 **Desktop `serve`（内嵌 supervisor）** 与 **外部 `monitor watch --daemon`** 同时运行，两进程各开多线程 `open_db()`，SQLite 写竞争翻倍。

此外（2026-06 后续修正）：

- `serve` 启动时若发现有效 external/embedded lock → **defer**，不 takeover（支持开机自启 CLI + 可选开 Desktop）
- `POST /api/runtime/restart`：`managed_by=external` 时 respawn CLI；embedded 时 restart embedded
- `clear_invalid_monitor_lock` 对 embedded lock（PID=`serve`）误判为 invalid（已修）
- CLI `live status --json` 对内嵌模式报 `lock_pid_mismatch`（已修）

本 Issue 交付：**锁文件 mode 语义** + **embedded lock 可信判定**；启动 defer 与 restart 分支见 2026-06 运维策略更新。

## 验收标准

### Task 1 — serve 启动 defer 已有 monitor

- [x] `api/app.py` lifespan：`auto_start_monitor=true` 且 lock 为有效 external monitor → log `monitor_auto_start_deferred_external`，不 start
- [x] 有效 embedded serve lock → log `monitor_auto_start_deferred_embedded`，不 start
- [x] 外部 PID 已死/假锁 → 清锁后 `supervisor.start`
- [x] `test_app_lifespan.py`：`test_lifespan_defers_external_monitor` / `test_lifespan_defers_embedded_monitor`

### Task 2 — API restart 按 managed_by 分支

- [x] `restart_runtime`：`managed_by=external` → `stop_external` + `spawn_cli_monitor_daemon`
- [x] `managed_by=embedded` → `stop` + `supervisor.start`
- [x] `handoff` / `takeover` 路由行为不变（显式切换）
- [x] `test_runtime_restart_respawns_external` / `test_runtime_restart_restarts_embedded`

### Task 3 — embedded lock 可信判定

- [x] 新增 `read_lock_record()`、`is_embedded_monitor_pid()`（cmdline 含 `media2text serve`）
- [x] `clear_invalid_monitor_lock`：**不**清除 `mode=embedded` 且 PID 为 live serve 的锁
- [x] `acquire_workspace_lock`：CLI 写 `mode=external`，serve 写 `mode=embedded`
- [x] `monitor_effectively_running`：无 supervisor 上下文时，embedded lock + heartbeat fresh → `running=True`
- [x] `test_clear_invalid_preserves_embedded_lock`、`test_monitor_effectively_running_embedded_without_supervisor` 通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_monitor_lock.py tests/unit/test_monitor_supervisor.py tests/unit/test_api_runtime.py tests/unit/test_runtime_status.py tests/unit/test_app_lifespan.py tests/unit/test_monitor_watcher.py -v
ruff check src/media2text/core/runtime/monitor_lock.py src/media2text/api/app.py src/media2text/api/services/runtime.py src/media2text/core/monitor/watcher.py
```

## 非目标范围

- 删除 `handoff` / 外部 CLI 能力（仍支持显式 handoff）
- `bin/monitor-watch-daemon.sh` 文档大改（MP-3 或 ops follow-up）
- Tauri UI 文案

## 依赖与顺序

- **建议依赖**：#334 已合并（降低 post_process 干扰）
- **分支**：`issue-335-monitor-db-mp2-single-owner`
