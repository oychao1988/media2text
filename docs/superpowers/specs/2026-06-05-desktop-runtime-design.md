# Desktop Runtime — 内嵌监控 + 统一状态 + 事件推送

**日期:** 2026-06-05  
**状态:** eng review 通过（2026-06-05；见 §12、GSTACK REVIEW REPORT）  
**Supersedes:** 无（与 [Monitor Daemon v3](./2026-06-05-monitor-daemon-observe-execute-design.md) 互补；本 spec 聚焦 Desktop/sidecar 运行时）  
**前置:** [m2t-desktop-design](./2026-06-04-m2t-desktop-design.md)、[Monitor Daemon v3](./2026-06-05-monitor-daemon-observe-execute-design.md)

---

## 0. 已锁定决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| Desktop 监控进程模型 | **Embedded MonitorSupervisor 于 `media2text serve` 进程** | 消除 API spawn CLI 子进程；WS 与 heartbeat 同进程；Tauri 仅维护一个 Python 子进程 |
| 状态对外契约 | **`GET /api/runtime` 单一快照** | 合并 daemon + live status 碎片字段；Agent / UI / 测试一处对齐 |
| Desktop 状态更新 | **WS 推送为主，HTTP 快照为辅** | 根治 `/api/daemon` 多组件重复轮询与 sidecar 日志噪音 |
| 健康语义 | **`health: stopped \| degraded \| healthy`** | `running=true` 仅表示 PID/线程存活，不足以回答「是否在 poll」 |
| Desktop 写操作 | **禁止 subprocess 调 `media2text monitor/post-process/pipeline` CLI** | 全部 `POST /api/...` 直调 core；CLI 保留给终端用户 |
| CLI daemon 兼容 | **保留锁文件语义；检测 external daemon** | 用户仍可 `monitor watch --daemon`；Desktop 显示 `managed_by: external` 且不重复 start |
| v3 观测层 | **本 spec 消费 v3 已有 `desktop_events` drain** | 不重复造轮询桥；embedded 后 daemon 写 outbox → 同进程 drain 更快 |

未选方案（备查）：

- **独立 daemon 进程 + Python import 启动（不经 CLI）** — 仍双进程，WS/heartbeat 需 IPC；Desktop 收益不足  
- **Tauri 直接 spawn `monitor watch`** — 三进程（Tauri / serve / monitor），运维更复杂  
- **仅合并前端 poll 间隔** — 不解决 health 语义与 CLI spawn 根因  

---

## 1. 问题陈述

### 1.1 症状

| 现象 | 根因 |
|------|------|
| sidecar 日志大量 `GET /api/daemon`（不同 ephemeral 端口） | `DaemonCard` 5s + `useDaemonRunning` 8s 独立轮询；日志展开时另打 `/logs` |
| Daemon 卡绿点但用户不确定「是否在 poll」 | `running` = 锁 PID 存活，无 `last_tick_at` |
| `failed 50` 吓人 | `monitor_tasks` 全表历史计数，非近期失败 |
| Agent/Desktop 与 CLI 双轨 | `start_daemon` 用 `Popen(monitor watch --daemon)`；管道操作无统一 API |
| v3 已设计 outbox，但 external daemon 仍跨进程 | embedded 后可同进程 publish（仍经 outbox 以保持 core 不 import api） |

### 1.2 目标用户问题

> 「后台监控是否在**正常工作**？」

需同时回答：进程在不在、LiveTick 是否在跑、有没有在录、队列是否积压、状态灯是否新鲜。

---

## 2. Success Criteria

| ID | 指标 | 目标 | 验收 |
|----|------|------|------|
| R1 | HTTP 轮询量 | Desktop 常态 **0 req/s** 对 runtime（WS 连接时） | sidecar stdout 无密集 `/api/daemon` |
| R2 | 首屏状态 | App 打开 **≤1s** 拿到 runtime 快照 | `GET /api/runtime` 单次 |
| R3 | 健康判定 | `healthy` 当且仅当 tick_age ≤ 2×poll 且 snapshots 不 stale | 单元测试 + 手工停 LiveTick 变 degraded |
| R4 | 启停 | embedded start/stop **≤3s** 反映到 UI | WS `runtime.health` |
| R5 | 兼容 | 外部 CLI daemon 占用锁时 UI 不误启第二个 | integration test |
| R6 | 管道 | Desktop/Agent 调 post-process/pipeline **不经 CLI** | grep api 层无 `Popen.*media2text`（auth login 除外） |
| R7 | G1 不退化 | 自动开录 P95 ≤ 30s | 沿用 v3 O5 验收 |

---

## 3. 架构

### 3.1 进程图（Desktop 目标态）

```
┌──────────────── Tauri m2t-desktop ────────────────┐
│  React UI                                          │
│    RuntimeProvider ──WS──► /api/events             │
│    DaemonCard / LeftRail / Manage ──► RuntimeContext │
└────────────────────────┬──────────────────────────┘
                         │ 127.0.0.1:8765
┌────────────────────────▼──────────────────────────┐
│  media2text serve (唯一 Python 子进程)              │
│  ┌─────────────────────────────────────────────┐  │
│  │ FastAPI lifespan                             │  │
│  │  MonitorSupervisor (embedded)                │  │
│  │    └─ MonitorScheduler (现有三线程)           │  │
│  │  RuntimeHealthLoop (async, 1–2s)             │  │
│  │  StateEventDrain (已有, desktop_events)      │  │
│  │  EventsHub → WS /api/events                  │  │
│  └─────────────────────────────────────────────┘  │
└────────────────────────┬──────────────────────────┘
                         │
              ./data/media2text.db + .monitor-watch.lock
                         │
              ffmpeg / Playwright 子进程（不变）
```

### 3.2 数据流：状态贡献

```
LiveTick / SlowTick / Executor
        │ upsert snapshots, sessions, queues
        ▼
   SQLite (WAL)
        │ INSERT desktop_events (变更时)
        ▼
 StateEventDrain ──► EventsHub ──► WS creator.updated
        │
 RuntimeHealthLoop ──► EventsHub ──► WS runtime.health
        │
 GET /api/runtime ◄── 读 DB + supervisor 内存 heartbeat
```

### 3.3 `MonitorSupervisor`（core 层）

**路径:** `src/media2text/core/runtime/supervisor.py`

```python
class MonitorSupervisor:
    """Thread-hosted monitor watch; safe to run inside serve process."""

    def start(self, cfg: AppConfig, *, creator_id: str | None = None) -> StartResult: ...
    def stop(self, *, timeout_sec: float = 10.0) -> StopResult: ...
    def status(self, cfg: AppConfig) -> SupervisorStatus: ...
    # SupervisorStatus: running, managed_by, thread_alive, started_at, last_tick_at
```

**实现要点:**

1. 在**后台 daemon 线程**内调用现有 `MonitorWatcher.run_daemon()` 逻辑，但将 `workspace_lock` 持有与 `MonitorScheduler` 生命周期绑定到 supervisor，而非 CLI 主线程 sleep。
2. **重构** `MonitorWatcher.run_daemon()`：抽出 `_run_daemon_locked(scheduler_factory)` 供 supervisor 与 CLI 共用；CLI `monitor watch --daemon` 仍可用（终端用户）。
3. LiveTick 每轮结束调用 `supervisor.record_tick()` 更新 `last_tick_at`（内存 + 可选写入 `data/.runtime-heartbeat` JSON，供 external 场景只读）。
4. `start()` 前检查锁：
   - 无锁 / stale → embedded start
   -  alive 外部 PID → 返回 `already_running_external`，不 start
5. `stop()` 仅当 `managed_by == embedded` 时 SIGTERM 外部 PID 或 stop 线程；external 时返回 `not_owner`。

**禁止:** `media2text.api` import；supervisor 纯 core。

### 3.4 API 层

#### 路由

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/runtime` | 完整快照（§4） |
| POST | `/api/runtime/start` | embedded start |
| POST | `/api/runtime/stop` | embedded stop |
| POST | `/api/runtime/restart` | stop + start |
| GET | `/api/runtime/logs?tail=N` | 读 `monitor-watch.log` |
| POST | `/api/post-process/run` | 包装 `drain_pending_jobs` |
| POST | `/api/post-process/retry/{job_id}` | 包装 repo retry |
| POST | `/api/monitor-tasks/retry/{task_id}` | Phase 3 repo |
| POST | `/api/creators/{id}/pipeline/run` | 异步入队（sync+download+transcribe 任务链） |

**兼容:** `/api/daemon` 保留 1 个 minor 版本，响应为 `runtime` 子集 + `deprecated: true` header；Agent tools 迁移后删除。

#### Lifespan（`api/app.py`）

```python
@asynccontextmanager
async def lifespan(app):
    cfg = AppConfig.load()
    supervisor = MonitorSupervisor()
    app.state.supervisor = supervisor
    app.state.runtime_health = RuntimeHealthState()

    if cfg.desktop.auto_start_monitor:
        supervisor.start(cfg)

    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(run_drain_loop(cfg, stop)),
        asyncio.create_task(run_runtime_health_loop(app, cfg, stop)),
    ]
    yield
    stop.set()
    supervisor.stop()
    await asyncio.gather(*tasks)
```

### 3.5 WebSocket 事件

扩展 `EventType`:

| 类型 | payload | 触发 |
|------|---------|------|
| `runtime.health` | 完整 §4 快照或 `{ health, tick_age_sec, active_recordings, queues }` diff | health 档位变化；或每 `desktop.runtime_ws_interval_sec` 心跳 |
| `queue.updated` | `{ post_process, monitor_tasks }` | 队列计数变化 |
| `runtime.log` | `{ lines: string[] }` | 可选；日志 tail 变化且 UI 订阅时 |

保留：`daemon.started/stopped` 映射到 `runtime.health` 内字段，避免双事件（迁移期可双发 1 版本）。

### 3.6 前端

#### `RuntimeProvider`（新）

- mount：`GET /api/runtime` 一次
- `useEventsWs`：合并现有 CreatorsProvider 的 WS 连接为**单连接多 handler**，或 RuntimeProvider 统一订阅并 dispatch
- 更新：`runtime.health` / `queue.updated` / `creator.updated`
- reconnect：`GET /api/runtime` + refresh creators
- fallback：WS 断开时 **60s** 一次 GET（非 5s）

#### 组件改造

| 组件 | 变更 |
|------|------|
| `DaemonCard` | 消费 `useRuntime()`；三行 UI + health 颜色；删 5s poll |
| `LeftRail` | 读 `runtime.health !== 'stopped'`；删 `useDaemonRunning` poll |
| `useLiveStatus` | active_recordings 从 runtime 上下文取，删重复 `/api/live/status` poll（session 细节按需 lazy GET） |
| `ConfigForm` restart | `POST /api/runtime/restart` |

#### Health UI 映射

| health | 点颜色 | 标题 |
|--------|--------|------|
| healthy | 绿 | 监控正常 |
| degraded | 黄 | 监控降级 |
| stopped | 灰 | 监控未运行 |

`health_reasons[]` 展示首条（如「LiveTick 45s 无心跳」）。

---

## 4. `GET /api/runtime` 响应契约

```json
{
  "ok": true,
  "health": "healthy",
  "health_reasons": [],
  "managed_by": "embedded",
  "daemon": {
    "running": true,
    "pid": 61166,
    "lock_pid": 61166,
    "started_at": "2026-06-05T04:00:00+00:00",
    "last_tick_at": "2026-06-05T04:05:18+00:00",
    "tick_age_sec": 3.2,
    "live_poll_interval_sec": 20
  },
  "recordings": {
    "active_count": 1,
    "items": []
  },
  "queues": {
    "post_process": { "pending": 0, "running": 0, "max_workers": 2 },
    "monitor_tasks": {
      "pending": 0,
      "running": 11,
      "failed_total": 50,
      "failed_recent_24h": 2,
      "dlq": 50
    }
  },
  "observability": {
    "snapshots_stale_count": 0,
    "monitored_creators": 12
  },
  "log_path": "data/monitor-watch.log"
}
```

### health 计算（`build_runtime_status`）

```python
def compute_health(*, running, tick_age_sec, live_poll_sec, snapshots_stale, failed_recent_24h, threshold_failed=10):
    if not running:
        return "stopped", ["monitor not running"]
    reasons = []
    if tick_age_sec is None or tick_age_sec > 2 * live_poll_sec:
        reasons.append("live tick stale")
    if snapshots_stale > 0:
        reasons.append(f"{snapshots_stale} creator snapshots stale")
    if failed_recent_24h > threshold_failed:
        reasons.append(f"{failed_recent_24h} monitor task failures in 24h")
    return ("degraded", reasons) if reasons else ("healthy", [])
```

**external daemon:** `managed_by=external`，`last_tick_at` 从 heartbeat 文件读；若无 heartbeat 文件则仅凭 snapshots_stale 判 degraded。

---

## 5. 配置

`config.example.yaml` / `DesktopConfig` 新增：

```yaml
desktop:
  auto_start_monitor: true
  runtime_ws_interval_sec: 30
  runtime_http_fallback_sec: 60
  runtime_failed_recent_threshold: 10
```

---

## 6. 迁移与兼容

| 阶段 | 行为 |
|------|------|
| M1 | 落地 supervisor + `/api/runtime`；`/api/daemon` alias；Desktop 切 RuntimeProvider |
| M2 | 删 `daemon.py` 内 CLI spawn；WS health loop |
| M3 | post-process / pipeline API；Agent tools 迁移 |
| M4 | 移除 `/api/daemon`；文档更新 |

**CLI 用户：** `media2text monitor watch --daemon` 不变；与 Desktop embedded 互斥（锁）。

**日志:** embedded 仍写 `data/monitor-watch.log`（supervisor 线程 tee 或 structlog handler）。

---

## 7. 测试计划

| 层 | 范围 |
|----|------|
| unit | `compute_health` 边界；supervisor start/stop 幂等；external lock 检测 |
| unit | `build_runtime_status` fixture DB；`failed_recent_24h` SQL |
| unit | `test_api_runtime.py`；deprecated `/api/daemon` 字段子集 |
| unit | LiveTick 调用 `record_tick` mock |
| desktop | `RuntimeProvider` 测试：WS message 更新 state |
| manual | 开 App → 无密集 daemon GET；录一场 → health healthy；kill LiveTick 线程 → degraded |

---

## 8. 实施顺序（4 PR）

```
PR1  core/runtime/supervisor.py + refactor run_daemon
     GET/POST /api/runtime + lifespan auto_start
     tests

PR2  RuntimeHealthLoop + WS runtime.health
     apps: RuntimeProvider, DaemonCard, LeftRail
     remove dual /api/daemon poll

PR3  Daemon UI 三态 + health_reasons + logs refresh
     failed_recent_24h in repo

PR4  POST /api/post-process/*, /api/monitor-tasks/retry, pipeline/run
     m2t-tools migration; remove CLI spawn from daemon service
```

**并行:** PR1 必须先于 PR2；PR3/PR4 可在 PR2 后并行。

---

## 9. NOT in scope

- 拆 Observe / Execute 为独立进程（v3 Phase 2 后续）
- Desktop 一键 retry 50 条 failed UI（仅 API + 管理页后续）
- 合并 `post_process_jobs` 与 `monitor_tasks` 表
- 改 Tauri  spawn 命令（仍为 `media2text serve`）
- auth login 交互式 CLI spawn（仍保留）

---

## 10. What already exists（复用）

| 已有 | 复用方式 |
|------|----------|
| `MonitorScheduler` / `MonitorWatcher` | supervisor 线程内直接启动 |
| `build_live_status` | 拆 queue/recordings 进 `build_runtime_status` |
| `desktop_events` + `run_drain_loop` | 不变；embedded 后延迟更低 |
| `EventsHub` + `/api/events` | 扩展 event types |
| `daemon.py` PID/lock 逻辑 | 迁入 supervisor + runtime service |
| Agent `m2t_get_live_status` | 改指向 `/api/runtime` |

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| serve 重启中断监控 | Desktop 默认 `auto_start_monitor`；Config 改 poll 间隔提示 restart |
| serve 阻塞影响 API | Monitor 已在独立线程；LiveTick 不阻塞 FastAPI event loop |
| external + embedded 争锁 | 明确 `managed_by`；UI 禁止双 start |
| WS 丢事件 | reconnect 全量 GET；60s fallback |
| 大 runtime payload | WS 发 diff；HTTP 全量 |

---

## 12. Eng review 锁定项（2026-06-05）

| 项 | 决策 |
|----|------|
| 实施范围 | **完整 epic PR1–PR4 一次规划**（非 MVP 拆分 ship） |
| external CLI daemon | **支持**；LiveTick 写 `data/.runtime-heartbeat`；`managed_by: external` 时 UI 只读 + 不重复 start |
| 前端 WS | **单连接** `EventsProvider` dispatch → runtime + creators（合并现有 `useEventsWs`） |
| `run_daemon` 重构 | CLI 与 embedded **共用 `MonitorSupervisor`** |
| `useLiveStatus` | **保留** `GET /api/live/status?creator=` 作 per-creator lazy load；`active_recordings` 摘要来自 runtime context |
| `pipeline/run` | **202 异步** + `job_id`；不入队阻塞 HTTP |

### Eng review 需修复项（写入 PR1 前）

1. **`MonitorWatcher.run_daemon` 停线程**：supervisor `stop()` 必须 `scheduler.stop()` + 释放锁；禁止仅 SIGTERM 自身（embedded 无独立 PID 语义）。
2. **`build_runtime_status` DRY**：从 `build_live_status` / `daemon_status` 抽共享 queue 计数，避免三处 SQL 分叉。
3. **`failed_recent_24h`**：用 `monitor_tasks.finished_at WHERE status='failed'`（已有列）；单测 fixture 覆盖。
4. **WS payload**：`runtime.health` 默认发 **diff**（health 档位 / queues / tick_age）；HTTP `/api/runtime` 全量。
5. **serve 重启**：Config PATCH 若 `requires_daemon_restart`，UI 调 `POST /api/runtime/restart`（已有 ConfigForm 钩子）。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 5 fixes in §12; test gaps 8 |
| CEO Review | — | — | 0 | — | — |
| Design Review | — | — | 0 | — | — |
| Outside Voice | — | — | 0 | skipped | — |

- **UNRESOLVED:** 0（scope / external / ws 已确认）
- **VERDICT:** ENG CLEARED WITH FIXES — 按 §12 修复项落地后可 implement
