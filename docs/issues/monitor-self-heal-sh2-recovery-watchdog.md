# Monitor 自愈 SH-2：孤儿场次恢复与 Self-heal Watchdog

GitHub Issue: [#314](https://github.com/oychao1988/media2text/issues/314)  
**Depends on:** [#313](https://github.com/oychao1988/media2text/issues/313)（SH-1 合并后）  
规格：[2026-06-16-monitor-self-heal-design.md](../superpowers/specs/2026-06-16-monitor-self-heal-design.md)  
计划：[2026-06-16-monitor-self-heal-implementation.md](../superpowers/plans/2026-06-16-monitor-self-heal-implementation.md)（Task 5–8）  
系列：SH-1 → **SH-2** → SH-3

## 背景

SH-1 交付可信锁与 `monitor_effectively_running()` 后，本 Issue 落实 **Layer 2（Watchdog）** 与 **孤儿场次恢复**：

1. daemon 死后 `recording` + 已 offline 的场次无人 enqueue `finalize`
2. `serve` lifespan 遇假锁 defer，且 `runtime_health_loop` 仅推 WS、不修复 stopped/degraded

**2026-06-16 实例**：session `42459606-df1c-4afd-9493-16162f1ce764` 卡在 `offline_pending`，`ffmpeg_pid` 已不存在。

## 验收标准

### Task 5 — `recover_orphan_sessions`

- [x] 新建 `src/media2text/core/live/session_recovery.py`
- [x] ffmpeg 已死 → 补写 `obs_ffmpeg_alive=0`
- [x] offline 已确认 → `reconcile_live` enqueue finalize（SH4）
- [x] ffmpeg 已死 + 无 offline + `started_at` age > 7200s → `status=failed`, `error=stale_recording`
- [x] `watcher._run_daemon_locked` 启动时调用并打 structlog
- [x] `tests/unit/test_session_recovery.py` 全绿（含 finalize 与 7200s 分支）

### Task 6 — `monitor_self_heal` 服务

- [x] `DesktopConfig`：`monitor_self_heal`、`monitor_self_heal_cooldown_sec`（120）、`monitor_self_heal_max_per_hour`（3）、`monitor_self_heal_check_every_sec`（30）
- [x] `config.example.yaml` 文档化上述字段
- [x] `maybe_self_heal_monitor`：cooldown + **1 小时滑动窗口**（SH6）；超限 `monitor_self_heal_gave_up`
- [x] TOCTOU：`clear_invalid_monitor_lock` 后二次 `is_monitor_watch_pid` → `skipped=external_started`
- [x] takeover 失败且 `lock_pid_mismatch` 时重试一次清锁
- [x] `tests/unit/test_monitor_self_heal.py`：takeover / **cooldown** / hourly_limit / external_started

### Task 7 — Lifespan + health loop

- [x] `api/app.py` lifespan：假锁时清锁后 `supervisor.start`（SH2：60s 内 embedded running）
- [x] `runtime_health_loop` 每 `monitor_self_heal_check_every_sec` 调 `maybe_self_heal_monitor`
- [x] `tests/unit/test_api_runtime.py` lifespan 假锁场景通过（`-m desktop`）
- [x] health loop：mock monotonic 时间推进，证明 cooldown 外周期自愈会触发（单元或集成测）

### Task 8 — 扩展 `recover-stale` API

- [x] `recover_stale_work` 调用 `recover_orphan_sessions`，响应含 `orphan_sessions_recovered`
- [x] `POST /api/runtime/recover-stale` 单测或集成测覆盖新字段

### 成功指标（SH2 / SH4 / SH6）

- [x] SH2：`desktop.auto_start_monitor=true` + 假锁 → serve 启动后 60s 内 `GET /api/runtime` 显示 embedded running
- [x] SH4：daemon 重启后 offline 已确认场次一轮内 enqueue finalize
- [x] SH6：冷却 120s + 每小时最多 3 次成功自愈

### 迁移说明

- [x] `CLAUDE.md` 说明：`auto_start_monitor` 在假锁场景下会清锁并自启 embedded（不再误判 `already_running_external`）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"

pytest tests/unit/test_session_recovery.py tests/unit/test_monitor_self_heal.py tests/unit/test_api_runtime.py -v -m desktop

ruff check src/media2text/core/live/session_recovery.py src/media2text/api/services/monitor_self_heal.py
pyright src/media2text/core/live/session_recovery.py src/media2text/api/services/monitor_self_heal.py
```

**手动验收（SH2）**

```bash
echo 581 > data/.monitor-watch.lock   # 或写入非 monitor 进程 PID
media2text serve --port 8765 &
sleep 5
curl -s http://127.0.0.1:8765/api/runtime | jq '.daemon.running, .daemon.lock_valid'
# 预期：running=true（或 lock 已清且 embedded 启动），lock_valid 语义正确
```

## 非目标范围

- `monitor_lock` / heartbeat 模块本体（→ SH-1，本 Issue 仅 import 使用）
- `bin/monitor-watch-daemon.sh`（→ SH-3）
- 纯 CLI 无 serve 的周期自愈（仅启动时 recovery；文档说明即可）
- Desktop UI 横幅
- LaunchAgent plist 模板
- 自动清理 DLQ

## 依赖与顺序

- **硬依赖**：SH-1 合并（`monitor_lock.py`、`monitor_effectively_running`）
- **建议分支**：`issue-314-monitor-self-heal-sh2`
- **阻塞**：SH-3 可与本 Issue 并行（仅依赖 SH-1 的 Python 清锁 API）
