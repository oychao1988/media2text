# Desktop Runtime PR1：MonitorSupervisor + `/api/runtime`

## 背景

Desktop 通过 `POST /api/daemon/start` 用 `subprocess.Popen` 拉起独立 `monitor watch --daemon` 进程，导致：

- `running` 仅表示锁 PID 存活，无法判断 LiveTick 是否在 poll
- `DaemonCard`（5s）与 `useDaemonRunning`（8s）重复轮询 `/api/daemon`，sidecar 日志噪音大
- Agent / UI 与 CLI 双轨，状态字段分散在 `/api/daemon` 与 `/api/live/status`

本 Issue 落地 **PR1**：core 层 `MonitorSupervisor`、重构 `run_daemon` 供 CLI 与 embedded 共用、`GET/POST /api/runtime`、heartbeat 文件、lifespan `auto_start_monitor`。**不含** WS 推送与前端改造（→ PR2）。

**参考**

- 设计：[2026-06-05-desktop-runtime-design.md](../superpowers/specs/2026-06-05-desktop-runtime-design.md) §3.3–3.4、§4、§6 M1、§8 PR1、§12 eng fixes 1–3
- 代码锚点：`core/monitor/watcher.py`、`api/services/daemon.py`、`core/live/status.py`

## 验收标准

### Task 1 — `MonitorSupervisor`（core）

- [ ] 新增 `src/media2text/core/runtime/supervisor.py`：`start` / `stop` / `status` / `record_tick`
- [ ] `stop()` 必须 `scheduler.stop()` + 释放 `workspace_lock`（embedded 无独立 PID；禁止仅 SIGTERM 自身）
- [ ] `start()` 检测 external lock：alive 外部 PID → `already_running_external`，不重复 start
- [ ] LiveTick 每轮结束调用 `record_tick()`；可选写入 `data/.runtime-heartbeat` JSON（`last_tick_at`）
- [ ] core 层 **不得** `import media2text.api`
- [ ] `tests/unit/test_monitor_supervisor.py`：start/stop 幂等、external lock、record_tick

### Task 2 — 重构 `MonitorWatcher.run_daemon`

- [ ] 抽出 `_run_daemon_locked(...)` 供 supervisor 后台线程与 CLI `monitor watch --daemon` 共用
- [ ] CLI 行为不变：`media2text monitor watch --daemon` 仍持锁、三线程调度
- [ ] 既有 `test_process_lock`、`test_live_scheduler` 回归全绿

### Task 3 — `build_runtime_status` + DRY

- [ ] 新增 `src/media2text/core/runtime/status.py`（或 `api/services/runtime.py` 调 core）：`build_runtime_status(cfg)`
- [ ] 从 `build_live_status` / 现有 daemon 逻辑 **抽共享** queue/recordings 计数，避免三处 SQL 分叉
- [ ] `compute_health(running, tick_age_sec, live_poll_sec, snapshots_stale, failed_recent_24h, ...)` → `stopped | degraded | healthy` + `health_reasons[]`
- [ ] `failed_recent_24h`：`monitor_tasks.finished_at WHERE status='failed' AND finished_at >= now-24h`（单测 fixture 覆盖）
- [ ] `tests/unit/test_runtime_status.py`

### Task 4 — API 路由 + lifespan

- [ ] `GET /api/runtime`：完整 §4 契约（`health`、`managed_by`、`daemon`、`recordings`、`queues`、`observability`、`log_path`）
- [ ] `POST /api/runtime/start` | `stop` | `restart`：embedded supervisor；external 时 stop 返回 `not_owner`
- [ ] `GET /api/runtime/logs?tail=N`：读 `monitor-watch.log`（可复用现有 daemon logs 逻辑）
- [ ] `/api/daemon` **保留**：响应为 runtime 子集 + `Deprecated: true` header（或 JSON `deprecated: true`）
- [ ] `api/app.py` lifespan：`app.state.supervisor`；`cfg.desktop.auto_start_monitor` 为 true 时 start
- [ ] `DesktopConfig` + `config.example.yaml`：`auto_start_monitor`、`runtime_failed_recent_threshold`（WS 间隔字段可先占位）
- [ ] `tests/unit/test_api_runtime.py`（自 `test_api_daemon.py` 迁移/扩展）

### Task 5 — 质量

- [ ] `ruff check` / `pyright` 新模块无新增错误
- [ ] `test_api_daemon.py` 仍绿（deprecated alias）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"

pytest tests/unit/test_monitor_supervisor.py \
  tests/unit/test_runtime_status.py \
  tests/unit/test_api_runtime.py \
  tests/unit/test_api_daemon.py \
  tests/unit/test_process_lock.py \
  tests/unit/test_live_scheduler.py \
  -v -m desktop

ruff check src/media2text/core/runtime src/media2text/api/services/runtime.py \
  src/media2text/api/routes/runtime.py
pyright src/media2text/core/runtime
```

**手动验收**

```bash
media2text serve --port 8765
curl -s http://127.0.0.1:8765/api/runtime | jq '.health,.managed_by,.daemon.last_tick_at'
# 预期：auto_start 后 managed_by=embedded，LiveTick 后 last_tick_at 刷新
```

## 非目标范围

- WS `runtime.health` / `RuntimeProvider` / 删前端 poll（→ PR2）
- Daemon UI 三态颜色、`failed_recent_24h` 展示文案（→ PR3）
- `POST /api/post-process/*`、`pipeline/run`、Agent tools（→ PR4）
- 移除 `/api/daemon`（→ PR4 后）
- 改 Tauri spawn 命令（仍为 `media2text serve`）
- v3 Observe/Execute 独立进程拆分

## 依赖与顺序

- **依赖**：Monitor Daemon v3 Phase 1–3（#145–#149）、m2t-desktop P3 events（#128）已交付
- **建议分支**：`issue-<N>-desktop-runtime-pr1`
- **阻塞**：Desktop Runtime PR2

## 实现备注

- GitHub Issue: [#158](https://github.com/oychao1988/media2text/issues/158)
- 分支：`issue-158-desktop-runtime-pr1`
- eng review §12 fix #1–#3 必须在 PR1 完成
