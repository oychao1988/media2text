---
issue: 335
epic: monitor-db-contention-2026-06-25
github: 335
branch: issue-335-monitor-db-mp2-single-owner
depends_on: [334]
---

# MP-2：Monitor 单 owner（Desktop embedded 优先于外部 CLI）

GitHub Issue: [#335](https://github.com/oychao1988/media2text/issues/335)  
Epic：**Monitor DB Contention**（2026-06-25）  
系列：MP-1 → **MP-2** → MP-3

## 背景

事故环境中 **Desktop `serve`（内嵌 supervisor）** 与 **外部 `monitor watch --daemon`** 同时运行，两进程各开多线程 `open_db()`，SQLite 写竞争翻倍。

此外：

- `serve` 启动时若发现外部 lock → `monitor_auto_start_deferred_external`，不接管
- `POST /api/runtime/restart` 在 `managed_by=external` 时 **spawn 新 CLI daemon**， perpetuate 双进程
- `clear_invalid_monitor_lock` 对 embedded lock（PID=`serve`）误判为 invalid（`is_monitor_watch_pid` 仅认 `monitor watch` cmdline）
- CLI `live status --json` 对内嵌模式报 `lock_pid_mismatch`

本 Issue：**serve 场景统一 embedded 单 owner**，并修正 embedded lock 判定。

## 验收标准

### Task 1 — serve 启动 takeover 外部 daemon

- [ ] `api/app.py` lifespan：`auto_start_monitor=true` 且 lock 为有效 external monitor → 调用 `supervisor.takeover(cfg)` 而非 defer
- [ ] 外部 PID 已死/假锁 → 仍 `supervisor.start`
- [ ] `test_serve_lifespan_takeover_external_monitor` 通过

### Task 2 — API restart 始终 restart embedded

- [ ] `restart_runtime`：无论当前 `managed_by`，先 `stop_external`，再 `supervisor.start`（**不再** `spawn_cli_monitor_daemon`）
- [ ] `handoff` 路由行为不变（显式切外部仍可用）
- [ ] `test_restart_runtime_always_embedded` 通过

### Task 3 — embedded lock 可信判定

- [ ] 新增 `read_lock_record()`、`is_embedded_monitor_pid()`（cmdline 含 `media2text serve`）
- [ ] `clear_invalid_monitor_lock`：**不**清除 `mode=embedded` 且 PID 为 live serve 的锁
- [ ] `monitor_effectively_running`：无 supervisor 上下文时，embedded lock + heartbeat fresh → `running=True`
- [ ] `test_clear_invalid_preserves_embedded_lock`、`test_monitor_effectively_running_embedded_without_supervisor` 通过

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_monitor_lock.py tests/unit/test_monitor_supervisor.py tests/unit/test_api_runtime.py tests/unit/test_runtime_status.py -v
ruff check src/media2text/core/runtime/monitor_lock.py src/media2text/api/app.py src/media2text/api/services/runtime.py
```

## 非目标范围

- 删除 `handoff` / 外部 CLI 能力（仍支持显式 handoff）
- `bin/monitor-watch-daemon.sh` 文档大改（MP-3 或 ops follow-up）
- Tauri UI 文案

## 依赖与顺序

- **建议依赖**：#334 已合并（降低 post_process 干扰）
- **分支**：`issue-335-monitor-db-mp2-single-owner`
