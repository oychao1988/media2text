# Monitor 自愈与可信锁 — 设计规格

**日期:** 2026-06-16  
**状态:** Draft（SH-1 实施中）  
**修订:** 2026-06-16 — 采纳 Eng Review 推荐：SH6 滑动窗口、`heartbeat.py` 拆分、`live status` 字段、embedded heartbeat_stale、`stale_sec` 下限、JSON 写锁、TOCTOU 说明  
**动机:** 生产环境反复出现「锁文件 PID 被系统复用 → 误判监控在跑 → serve 放弃自启 → 僵尸录制未 finalize」；严重影响直播监控可用性。  
**实现计划:** [2026-06-16-monitor-self-heal-implementation.md](../plans/2026-06-16-monitor-self-heal-implementation.md)  
**Issues:** [#313 SH-1](https://github.com/oychao1988/media2text/issues/313) · [#314 SH-2](https://github.com/oychao1988/media2text/issues/314) · [#315 SH-3](https://github.com/oychao1988/media2text/issues/315)  
**相关:** [2026-06-05-monitor-daemon-observe-execute-design.md](./2026-06-05-monitor-daemon-observe-execute-design.md)、[2026-06-05-desktop-runtime-design.md](./2026-06-05-desktop-runtime-design.md)

---

## 1. 问题陈述

### 1.1 故障链（2026-06-16 实例）

| 步骤 | 现象 | 根因 |
|------|------|------|
| 1 | `monitor watch` 进程退出，`.monitor-watch.lock` 残留 PID `581` | 崩溃 / kill 未清锁 |
| 2 | macOS 将 PID `581` 分配给 `audioaccessoryd` | PID 复用 |
| 3 | `clear_stale_workspace_lock` / `_pid_alive` 返回 true | **仅检查进程存在，不校验命令行** |
| 4 | `media2text serve` lifespan：`already_running_external` → defer | 不自启 embedded supervisor |
| 5 | 无 LiveTick → 无 reconcile → 无 finalize | 场次卡在 `offline_pending` |
| 6 | `live status` 显示 `daemon_lock_pid: 581`、`active_recordings: 1` | 用户以为在监控，实际未运行 |

### 1.2 现有能力缺口

| 能力 | 现状 | 缺口 |
|------|------|------|
| 锁校验 | `os.kill(pid, 0)` | 无进程身份校验 |
| 运行判定 | lock PID alive **或** embedded thread | 无 heartbeat 联合判定 |
| 健康循环 | `runtime_health_loop` 只推 WS | **不修复** stopped/degraded |
| serve 自启 | 遇 external lock 即 defer | 假锁不清理 |
| 场次恢复 | `reconcile_live` 仅 daemon 运行时 | daemon 死后 orphan session 无人 enqueue finalize |
| 启动脚本 | `bin/monitor-watch-daemon.sh` 用 `kill -0` | 与 core 同缺陷 |

---

## 2. 目标（Success Criteria）

| ID | 指标 | 验收 |
|----|------|------|
| SH1 | **假锁识别** | 锁 PID 非 `media2text monitor watch` 时，`doctor` / `GET /api/runtime` 报告 `lock_invalid` 且 `running=false` |
| SH2 | **自启可靠** | `desktop.auto_start_monitor=true` 且假锁存在时，serve 启动后 **60s 内** embedded supervisor running |
| SH3 | **心跳失效** | lock 有效但 `.runtime-heartbeat` 超过 `heartbeat_stale_sec` 未更新 → `running=false` / `health=degraded`，self-heal 触发 restart；**embedded 不因 `thread_alive` 掩盖 stale** |
| SH4 | **孤儿场次** | daemon 重启后，已 `offline_confirm` 的 `recording` 场次 **一轮 reconcile 内** enqueue `finalize` |
| SH5 | **向后兼容** | 纯数字锁文件（legacy）仍可被新代码读取；新 daemon 写入 JSON 锁（可选字段） |
| SH6 | **无重启风暴** | 单次冷却默认 120s（`monitor_self_heal_cooldown_sec`）；**滑动窗口** 1 小时内成功自愈最多 3 次（`monitor_self_heal_max_per_hour`），超限后本小时仅打 `monitor_self_heal_gave_up` 日志、不再 takeover |

---

## 3. 架构

### 3.1 三层保障

```
┌─────────────────────────────────────────────────────────┐
│ Layer 3: 运维 — LaunchAgent / monitor-watch-daemon.sh   │
│           调用 core.monitor_lock 校验后启动                │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Watchdog — runtime_health_loop + self_heal     │
│           degraded/stopped → clear lock → takeover      │
├─────────────────────────────────────────────────────────┤
│ Layer 1: 可信锁 — monitor_lock.py                       │
│           PID + cmdline + heartbeat 联合判定 running     │
└─────────────────────────────────────────────────────────┘
```

### 3.2 新增 / 调整模块

| 模块 | 职责 |
|------|------|
| `core/runtime/heartbeat.py` | **从 `status.py` 抽出** — `read_heartbeat` / `write_heartbeat` / `_age_sec` / `heartbeat_stale_sec()`；打破 `monitor_lock` ↔ `status` 循环依赖 |
| `core/runtime/monitor_lock.py` | 锁读写、PID 命令行校验、`monitor_effectively_running()`；**仅依赖** `heartbeat.py` |
| `core/live/session_recovery.py` | `recover_orphan_sessions()` — daemon 启动时 enqueue finalize + 超长 orphan `mark_stale` |
| `api/services/monitor_self_heal.py` | 冷却 + **小时滑动窗口**、takeover 编排（含 TOCTOU 二次校验），供 health loop 调用 |

### 3.3 锁文件格式（向后兼容）

**Legacy（保留读取）：**

```
581
```

**V2（新写入，单行 JSON）：**

```json
{"pid":12345,"mode":"external","started_at":"2026-06-16T03:42:44+00:00","argv":"media2text monitor watch --daemon"}
```

读取逻辑：若内容以 `{` 开头则 JSON 解析；否则 `int(strip)`。

### 3.4 心跳过期阈值

```python
def heartbeat_stale_sec(live_poll_sec: int) -> float:
    # 避免 poll=10s 时 2×poll=20s 与 health loop 30s 同频边界抖动
    return max(90.0, 2 * live_poll_sec)
```

`compute_health` 与 `monitor_effectively_running` **统一**使用此阈值（替代裸 `2 * live_poll_sec`）。

### 3.5 `monitor_effectively_running` 判定

```python
def monitor_effectively_running(
    workspace, cfg, *, supervisor_status, live_poll_sec
) -> tuple[bool, str | None]:
    # reason: None | "lock_missing" | "lock_pid_mismatch" | "heartbeat_stale" | "embedded_thread_dead"
```

`stale_sec = heartbeat_stale_sec(live_poll_sec)`

1. **Embedded：** `thread_alive` 且 `lock_pid == os.getpid()` 时，仍检查 heartbeat；`tick_age > stale_sec` → False (`heartbeat_stale`)，**不得**因 `thread_alive` 强制 `running=True`  
2. **Embedded：** `thread_alive` 但锁非本进程 → False (`embedded_thread_dead`)  
3. **External / legacy：** `lock_pid is None` → False (`lock_missing`)  
4. **External：** `is_monitor_watch_pid(lock_pid)` 为 False → False (`lock_pid_mismatch`)  
5. **External：** heartbeat `tick_age > stale_sec` → False (`heartbeat_stale`)  
6. 否则 → True  

`build_runtime_status.running` 与 `build_live_status` 的 `daemon_lock_valid` **均**调用此函数；不再单独 `lock_pid and _pid_alive(lock_pid)`。

### 3.6 Self-heal 触发（`desktop.monitor_self_heal: true`）

在 `runtime_health_loop` 每 `monitor_self_heal_check_every_sec`（默认 30s）检查：

| 条件 | 动作 |
|------|------|
| `monitor_effectively_running()` 为 True | 跳过 |
| 距上次成功自愈 `< monitor_self_heal_cooldown_sec` | 跳过（`skipped=cooldown`） |
| 本小时成功自愈次数 ≥ `monitor_self_heal_max_per_hour`（默认 3） | 打 `monitor_self_heal_gave_up`，本小时不再重试 |
| 否则 | `clear_invalid_monitor_lock()` → **二次** `read_lock_pid` + `is_monitor_watch_pid`（TOCTOU：外部 CLI 刚启动则 `skipped=external_started`）→ `supervisor.takeover(cfg)` → `recover_stale_work()` |
| takeover 失败且 `lock_pid_mismatch` | 再 `clear_invalid_monitor_lock` 后重试 takeover **一次** |

**纯 CLI 无 serve：** self-heal 不跑；依赖 daemon 启动时 `recover_orphan_sessions` + `bin/monitor-watch-daemon.sh` 清假锁（见 §1.2）。

### 3.7 孤儿场次恢复

`recover_orphan_sessions(cfg, conn)` 在 `_run_daemon_locked()` 开头调用（与 `bootstrap_streaming_stt` 并列）：

| 条件 | 动作 |
|------|------|
| `status=recording` + `ffmpeg_pid` 死 | 补写 `obs_ffmpeg_alive=0` |
| `status=recording` + `offline_since_at` 已过 `offline_confirm_sec` | `reconcile_live` enqueue finalize |
| `status=recording` + `ffmpeg_pid` 死 + **无** `offline_since_at` + `started_at` age > 7200s | `LiveSessionRepo.update_status(failed, error=stale_recording, ended=True)` |
| 其余 active recording | 最后统一 `reconcile_live(cfg, conn)` |

返回值：`(touched_ffmpeg, stale_marked, reconcile_ensured)` 或合计整数（实现计划约定单测字段）。

### 3.8 写锁（SH5 完整）

- `acquire_workspace_lock` 在 `lock_path.name == ".monitor-watch.lock"` 时调用 `write_lock_record` 写 JSON v2；其它锁文件仍写纯 PID。  
- `supervisor.start` / `watcher._run_daemon_locked` 经 `acquire_workspace_lock` 获得锁，**不**再裸 `write_text(pid)`。

### 3.9 配置

```yaml
desktop:
  auto_start_monitor: true
  monitor_self_heal: true                    # 新增，默认 true（example）
  monitor_self_heal_cooldown_sec: 120        # 两次成功自愈最小间隔
  monitor_self_heal_max_per_hour: 3          # 滑动窗口上限（SH6）
  monitor_self_heal_check_every_sec: 30      # health loop 内节流
```

### 3.10 API / CLI 变更

| 面 | 变更 |
|----|------|
| `GET /api/runtime` | `daemon.lock_valid: bool`、`daemon.lock_reason: str \| null`；`running` 来自 `monitor_effectively_running` |
| `doctor --json` | `monitor_lock_valid`；假锁时 `warnings: ["monitor_lock_pid_mismatch"]` |
| `live status --json` | 新增 `daemon_lock_valid: bool`、`daemon_lock_reason: str \| null`（与 runtime 语义一致） |
| `POST /api/runtime/recover-stale` | 扩展：含 `orphan_sessions_recovered` 计数 |

---

## 4. 非目标

- 拆 monitor 为多进程（见 v3 spec 备查）
- Desktop UI 横幅 / 一键修复按钮（可 follow-up issue）
- macOS LaunchAgent plist 模板（文档提及即可）
- 修改 `live.offline_confirm_sec` 语义

---

## 5. 测试策略

| 层 | 文件 |
|----|------|
| unit | `tests/unit/test_heartbeat.py`（或合入 `test_runtime_status.py`） |
| unit | `tests/unit/test_monitor_lock.py` — **含回归** 假锁 PID=581 → `running=False` |
| unit | `tests/unit/test_session_recovery.py` — 含 `age>7200` → `stale_recording` |
| unit | `tests/unit/test_monitor_self_heal.py` — cooldown + **滑动窗口 3/小时** + TOCTOU skip |
| unit | 更新 `test_process_lock.py`（JSON 写锁）、`test_runtime_status.py`、`test_monitor_supervisor.py`、`test_api_sessions.py`（`daemon_lock_valid`） |
| unit | `test_api_runtime.py` — lifespan 假锁自启 |
| desktop | `pytest tests/unit/test_*monitor* tests/unit/test_api_runtime* -m desktop` |

---

## 6. 迁移

- 无需 DB migration  
- 旧纯数字锁：继续可读；下次 daemon 成功启动后覆写为 JSON（可选，不强制）  
- `auto_start_monitor` 行为变更：假锁时改为清理并启动（**修复性变更**，需在 CHANGELOG 注明）
