# Monitor 自愈 SH-1：可信锁与运行态判定

GitHub Issue: [#313](https://github.com/oychao1988/media2text/issues/313)  
规格：[2026-06-16-monitor-self-heal-design.md](../superpowers/specs/2026-06-16-monitor-self-heal-design.md)  
计划：[2026-06-16-monitor-self-heal-implementation.md](../superpowers/plans/2026-06-16-monitor-self-heal-implementation.md)（Task 0–4）  
系列：**SH-1** → SH-2 → SH-3

## 背景

生产环境（2026-06-16）出现：`monitor watch` 崩溃后 `.monitor-watch.lock` 残留 PID `581`，被 macOS 复用给 `audioaccessoryd`；`os.kill(pid, 0)` 误判存活 → `serve` 的 `auto_start_monitor` defer → 无 LiveTick / reconcile → 场次卡在 `offline_pending`。

本 Issue 落实 **Layer 1（可信锁）**：PID 命令行校验 + heartbeat 联合判定 `monitor_effectively_running()`，并统一 `GET /api/runtime`、`live status --json`、`doctor` 的锁有效性字段。**不含** self-heal watchdog 与孤儿场次恢复（→ SH-2）。

**故障链摘要**

| 步骤 | 现象 |
|------|------|
| 假锁 PID 存活但非 monitor | `daemon_lock_pid: 581`，`running` 误判 true |
| serve 不自启 | `already_running_external` |
| 僵尸录制 | `offline_pending` 永不 finalize |

## 验收标准

### Task 0 — `heartbeat.py` 抽出

- [x] 新建 `src/media2text/core/runtime/heartbeat.py`：`read_heartbeat`、`write_heartbeat`、`_age_sec`、`heartbeat_stale_sec`（`max(90, 2×poll)`）
- [x] `scheduler` / `supervisor` 从 `heartbeat` 导入，无 `monitor_lock` ↔ `status` 循环 import
- [x] `tests/unit/test_heartbeat.py::test_heartbeat_stale_sec_floor_at_90` 通过

### Task 1 — `monitor_lock.py`

- [x] `read_lock_pid` 兼容 legacy 纯数字与 JSON v2；单测覆盖**空锁文件**、**非法 JSON**（`{}`）、legacy 纯数字
- [x] `is_monitor_watch_pid` 校验 cmdline 含 `media2text` + `monitor` + `watch`
- [x] `clear_invalid_monitor_lock` 清除 PID 不匹配 / 已死进程
- [x] `monitor_effectively_running`：embedded **不**因 `thread_alive` 掩盖 `heartbeat_stale`
- [x] **回归**：锁 PID=581（假进程）→ `running=False`, `reason=lock_pid_mismatch`
- [x] `tests/unit/test_monitor_lock.py` 全绿

### Task 2 — `process_lock` + JSON 写锁

- [x] `.monitor-watch.lock` 的 stale 清理委托 `clear_invalid_monitor_lock`（其他 workspace 锁保留原 `_pid_alive` 逻辑）
- [x] `acquire_workspace_lock` 对 `.monitor-watch.lock` 写入 JSON v2（SH5）
- [x] `tests/unit/test_process_lock.py` 含假锁清理 + JSON 写锁用例

### Task 3 — `build_runtime_status` / `build_live_status` / doctor

- [x] `daemon.lock_valid`、`daemon.lock_reason`；`running` 仅来自 `monitor_effectively_running`
- [x] `read_daemon_pid()` 委托 `read_lock_pid()`，不再单独 `int(strip)` 读锁
- [x] `compute_health()` 使用 `heartbeat_stale_sec()`；embedded + heartbeat_stale → `health=degraded`（且 `running=False`）
- [x] `live status --json` 增 `daemon_lock_valid`、`daemon_lock_reason`
- [x] `archive/health.py`：`monitor_lock_pid` 委托 `read_lock_pid`；`monitor_lock_valid` 复用 `is_monitor_watch_pid`
- [x] `doctor --json` 假锁时 `warnings` 含 `monitor_lock_pid_mismatch`（`test_doctor_legacy_pipeline.py` 或专用 `test_doctor_monitor_lock.py`）
- [x] embedded + heartbeat_stale → `running=False`（单测覆盖）
- [x] `tests/unit/test_runtime_status.py`、`tests/unit/test_api_sessions.py` 全绿

### Task 4 — Supervisor / external_spawn

- [x] `supervisor.start` / `external_spawn` 启动前 `clear_invalid_monitor_lock`；真 external lock 仍阻塞
- [x] 假锁场景 `supervisor.start` 成功
- [x] `tests/unit/test_monitor_supervisor.py`、`tests/unit/test_external_spawn.py` 全绿

### 成功指标（SH1 / SH3 / SH5 子集）

- [x] SH1：`doctor` + `GET /api/runtime` 对假锁报告 `lock_valid=false`、`running=false`
- [x] SH3：`heartbeat_stale_sec` 下限 90s；embedded stale 可触发自愈路径（判定层就绪，执行在 SH-2）
- [x] SH5：legacy 锁可读；新 daemon 写 JSON

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"

pytest tests/unit/test_heartbeat.py tests/unit/test_monitor_lock.py tests/unit/test_process_lock.py tests/unit/test_runtime_status.py tests/unit/test_monitor_supervisor.py tests/unit/test_external_spawn.py tests/unit/test_api_sessions.py tests/unit/test_doctor_legacy_pipeline.py -v

ruff check src/media2text/core/runtime/heartbeat.py src/media2text/core/runtime/monitor_lock.py src/media2text/core/process_lock.py
pyright src/media2text/core/runtime/heartbeat.py src/media2text/core/runtime/monitor_lock.py
```

## 非目标范围

- `monitor_self_heal` / `runtime_health_loop` takeover（→ SH-2）
- `recover_orphan_sessions`（→ SH-2）
- `bin/monitor-watch-daemon.sh` 改造（→ SH-3）
- Desktop UI 横幅 / 一键修复
- Windows / Linux `ps` 专项验证
- 清理 DLQ failed monitor tasks
- 磁盘满与录制失败联动

## 依赖与顺序

- **依赖**：Desktop Runtime（#158–#161）、Live Pipeline v2（#81–#87）已交付
- **建议分支**：`issue-313-monitor-self-heal-sh1`
- **阻塞**：SH-2、SH-3（SH-2 依赖本 Issue 的 `monitor_lock`）
