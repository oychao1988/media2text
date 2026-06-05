# Monitor Daemon v3 — 观测 / 状态 / 执行分离

**日期:** 2026-06-05  
**状态:** 已评审（2026-06-05 eng review，开放项见 §12）  
**前置:** [Live Pipeline v2](./2026-06-03-live-pipeline-v2-design.md)、[m2t-desktop](./2026-06-04-m2t-desktop-design.md)  
**动机:** Desktop 左侧栏状态与 daemon 实际行为脱节；架构讨论中提出的「三层模型」需落成可演进设计，而非一次性大重构。

---

## 0. 已锁定决策（本 spec 范围）

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 总体方向 | **观测与执行分离**，状态为唯一对外契约 | Desktop / CLI / Agent 只读「贡献出来的状态」，不耦合 poll 实现 |
| 任务触发 | **检测 → 写状态 + 入队 → Executor 消费** | 避免 Executor 再轮询状态表（重复 poll、竞态） |
| 直播开录 | **保留 LiveTick 内低延迟快速路径** | G1（检测→开录 P95 ≤30s）不宜完全等下一轮队列 |
| 执行资源 | **有界 worker 池 + 子进程**（ffmpeg / Playwright） | 禁止「每博主一线程」无界模型 |
| 迁移策略 | **两阶段**：先状态写全 + Desktop 推送，再迁执行逻辑 | 小步可验收，不阻塞当前 hotfix |
| 单实例 | 仍用 `data/.monitor-watch.lock` + stale PID 清理 | 与 v2、Desktop daemon API 一致 |
| Desktop 推送 | **`desktop_events` outbox 表 + API drain 协程** | daemon 为独立子进程，**不能** 直调 API 进程内 `EventsHub`；core 层 **禁止** `import media2text.api` |
| API 探测失败 | 仍更新 `checked_at`；可选 `probe_error` | 避免 `live_info is None` 时 snapshot 冻结导致灯长期错误 |

未选方案（备查）：

- **每博主常驻线程** — 博主数增长后线程与连接数不可控  
- **Executor 轮询 `creator_live_snapshots` 再决定开录** — 与 LiveTick 双写、延迟叠加  
- **拆成多进程 daemon** — 个人 CLI 场景收益不足，运维成本上升  

---

## 1. 问题陈述

### 1.1 现状（v2 已交付）

`monitor watch --daemon` 在单进程内运行 **三线程**（见 `MonitorScheduler`）：

```
Main（持锁 idle）
  ├─ LiveTickLoop      ~10–20s：douyin/bilibili run_once + post_process claim/submit
  ├─ SlowTickLoop      各自间隔：VOD / B 站 archive / dynamic
  └─ PostProcessExecutor  线程池：transcribe / summarize / upload
```

录制使用 **ffmpeg 子进程**，不是每博主一个 Python 线程。`run_once` 内部仍 **耦合**：

| 阶段 | 当前位置 | 问题 |
|------|----------|------|
| 平台 live 检测 | LiveTick `run_once` | 与开录、finalize 同函数 |
| 写 `creator_live_snapshots` | LiveTick 内 | daemon 更新后 **未** 稳定推送 Desktop |
| 自动开录 | LiveTick 内 `_start_recording` | 合理保留快速路径，但与「纯观测」未分层 |
| VOD sync + 下载 | SlowTick `_run_vod_tick` | 检测与 Playwright 同步/下载同 tick |
| 后处理 | PostProcessPool | 仅消费 `post_process_jobs`，模型清晰 |

### 1.2 Desktop 侧症状（2026-06-05 排查）

| 现象 | 根因 |
|------|------|
| 主播在播但左侧 🔴/⚫ 不准 | `creator_live_snapshots` 过期或为空；daemon 未跑时依赖 API 按需 refresh（限流） |
| Daemon 显示未运行 / 启动失败 | **Stale lock**（死 PID 占锁）；子进程秒退 |
| 列表不随 daemon poll 刷新 | daemon 子进程写 DB 后 **无跨进程桥**；API `EventsHub` 仅在同进程路由里 publish，`creator.updated` 未触发 |
| 轮询兜底 | 前端已加 20s `GET /api/creators`；API 在 daemon idle 时 `refresh_stale_snapshots`（每次最多 2 博主） |

结论：**执行层（v2）已基本隔离**，缺的是 **状态贡献契约** 与 **观测/执行边界在代码层的显式化**。

---

## 2. 目标（Success Criteria）

| ID | 指标 | 目标 | 验收 |
|----|------|------|------|
| O1 | 状态新鲜度 | daemon 运行时，`creator_live_snapshots.checked_at` 距现在 ≤ **2× live_poll** | `GET /api/creators` + DB 抽查 |
| O2 | Desktop 实时性 | snapshot / session 变更后 **≤3s** 左侧灯更新 | WS `creator.updated` 或等效推送 |
| O3 | 观测无副作用 | 「仅检测」代码路径 **不** 启动 ffmpeg / Playwright 长任务 | 单元测试 + 日志无 `recording_started` |
| O4 | 执行可追踪 | 每种任务类型有 queue 行 + `live_pipeline_events` | `live timeline` / job 表 |
| O5 | G1 不退化 | 自动开录 P95 ≤ **30s**（相对 v2） | `live stats` / events |
| O6 | 单实例可靠 | stale lock 自动清理；Desktop 启动 daemon 有明确错误码 | `test_process_lock` / `test_api_daemon` |

---

## 3. 概念模型：三层 + 两通道

用户提出的三层模型，精炼为 **观测层 → 状态层 → 执行层**，并区分 **快速通道** 与 **队列通道**。

```
                    ┌─────────────────────────────────────┐
                    │           状态层（SQLite）            │
                    │  creator_live_snapshots               │
                    │  live_sessions (+ 状态机字段)          │
                    │  catalog / dynamics 游标（已有）       │
                    │  desktop_events（Phase 1，见 §6.2）    │
                    │  monitor_tasks（Phase 2，见 §6.3）     │
                    └──────────────▲────────────────────────┘
                                   │ upsert / transition
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
   ┌─────┴──────┐           ┌──────┴──────┐          ┌──────┴──────┐
   │ 直播观测    │           │ 内容观测     │          │ 执行器       │
   │ LiveObserve│           │ContentObserve│          │ Executor    │
   │ Tick       │           │ Tick         │          │ Pool        │
   └─────┬──────┘           └──────┬──────┘          └──────┬──────┘
         │                         │                         │
    get_live_room              新 aweme /               ffmpeg / remux
    poll_active                archive /                Playwright sync
                               dynamic                  post_process_jobs
```

### 3.1 直播观测（LiveObserveTick）

**职责：** 轮询平台 live API；更新 snapshot；驱动 `live_sessions` 状态机 **检测边**（不含 remux）。

**输出：**

- `creator_live_snapshots`：`is_live`, `room_id`, `title`, `checked_at`, `platform`
- `live_sessions`：`offline_since_at`、事件 `detected_live` / `offline_pending`
- **任务建议**（非直接执行）：
  - `live_unrecorded` → 入队 `start_recording`（或快速通道立即消费，见 §4.2）
  - `offline_confirmed` → 入队 `finalize_recording`

**禁止：** Playwright 作品同步、VOD 下载、阻塞式 post-process。

### 3.2 内容观测（ContentObserveTick）

**职责：** 发现新作品 / 投稿 / 动态；写 catalog 或 dynamic 表；发通知；**仅入队**后续重任务。

**输出：**

- DB：`videos` / `archives` / `dynamics` 行或 `last_*_cursor`
- 通知：`new_aweme` / `new_archive` / `new_dynamic`
- 任务：`sync_catalog`、`download_video`、`sync_dynamic_body` 等

**禁止：** 在 tick 内跑完整 Playwright 同步（>30s）——应 submit 到 Executor。

### 3.3 执行层（ExecutorPool）

**职责：** 消费 **显式任务队列**（`monitor_tasks` + 既有 `post_process_jobs`），有界并行。

| 队列 | 消费者 | 说明 |
|------|--------|------|
| `monitor_tasks` | `MonitorExecutor`（新） | 开录、finalize、VOD sync、下载、dynamic 拉正文 |
| `post_process_jobs` | `PostProcessExecutor`（现有） | transcribe、summarize、upload |

**禁止：** 轮询 `is_live` 决定是否开录（避免与 LiveObserve 重复）；修改逻辑应基于 **任务 payload** 与 **session 行锁**。

---

## 4. 方案对比

### 方案 A — 逻辑分层、物理不变（推荐 Phase 1）

- LiveTick / SlowTick **线程名与间隔不变**
- 将 `run_once` 拆成 `observe_live_state()` + `maybe_start_recording()`；开录仍由后者在 LiveTick **同步**快速路径
- 观测后写 `desktop_events` outbox（仅状态 **变更** 时 INSERT）；API sidecar drain → WS
- **优点：** 改动小、O1/O2 快速见效  
- **缺点：** 执行仍部分挂在 LiveTick，G5 依赖纪律而非结构  

### 方案 B — 统一 `monitor_tasks` 队列（推荐 Phase 2）

- 所有 mutating 操作仅通过 `monitor_tasks` + Executor
- LiveObserve 只写状态 + `enqueue(start_recording | finalize)`
- Executor 内复用 `LiveRecordingCore`、`catalog` 现有函数
- **优点：** 边界清晰、易测、易扩展优先级  
- **缺点：** 开录多一跳，需 **高优先级队列** 或 LiveTick 内 **inline 消费 start_recording**  

### 方案 C — 多进程 Observe / Execute

- Observe 进程只写 DB；Execute 进程 watch 队列  
- **优点：** 崩溃隔离最强  
- **缺点：** 部署、锁、Playwright 会话共享复杂；**本 spec 不采用**

**推荐路径：** **A → B**。Phase 1 解决 Desktop 与状态契约；Phase 2 把 SlowTick 重任务与 LiveTick finalize 迁入 Executor。

---

## 5. 选定架构（目标态）

### 5.1 进程 / 线程图（Phase 2 末态）

```
┌──────────────────────────────────────────────────────────────┐
│  monitor watch --daemon（单进程，workspace lock）              │
├──────────────────────────────────────────────────────────────┤
│  Main          信号、锁、优雅退出                              │
│  LiveObserve   live poll → snapshot + session 检测边           │
│                → enqueue(start|finalize) 或 inline 高优消费   │
│  ContentObserve  vod/archive/dynamic 检测 → enqueue 重任务    │
│  MonitorExecutor ThreadPoolExecutor（默认 1，见 §8 P2.4）      │
│                start_recording / finalize / sync / download   │
│  PostProcessExecutor（现有，独立池）                          │
│                post_process_jobs only                         │
└──────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   ffmpeg / ffprobe 子进程        Playwright（短会话 per job）
```

与 v2 差异：**SlowTick 改名为 ContentObserve**；**LiveTick 拆观测/执行**；新增 **MonitorExecutor** 与 **`monitor_tasks`**。PostProcess 保持独立，避免长转写占满开录 worker。

### 5.2 快速通道（保留 G1）

当 `effective_auto_record(creator, config) == true` 且 snapshot 从 offline→live：

1. LiveObserve **同步** 调用 `start_recording`（与 today 相同），**或**
2. `enqueue(start_recording, priority=0)` 后 LiveObserve **同 tick 内** `executor.try_claim_high_priority()`  

禁止：仅入队、等 ContentObserve 或 PostProcess 下一轮才开录。

手动录制（Desktop `POST .../recording/start`）走 API → `LiveRecordingCore`，仍要求 daemon 运行以 `poll_active` / finalize。

---

## 6. 数据模型

### 6.1 直播状态机（`live_sessions` + snapshot）

Desktop 灯由 `compute_status_light()` 计算（已有）。观测层应保证输入一致：

| 逻辑状态 | snapshot | session | 灯 |
|----------|----------|---------|-----|
| offline | `is_live=0` | 无 active | ⚫ gray |
| live_unrecorded | `is_live=1` | 无 recording | 🔴 red |
| recording | `is_live=1` | `status=recording`, ffmpeg 存活 | 🟢 green |
| finalizing | 任意 | `offline_since_at` 已设或 remux 中 | 🟡 yellow |
| degraded | 任意 | `transcribe_status=degraded` | 🟡 yellow |

**新增（可选，Phase 1 可用派生字段代替）：** `creator_live_snapshots.live_phase` ENUM：`offline | live | unknown`，便于 Agent 读表；**非必须**，灯仍以 `compute_status_light` 为准。

**API 探测失败（Phase 1，已锁定）：** 当 `get_live_room` 抛错或返回不可解析结果时，**不得** 静默跳过 upsert（今日 `upsert_live_snapshot` 在 `live_info is None` 时直接 return）。应至少：

- 更新 `creator_live_snapshots.checked_at`（表示「刚探过」）  
- 可选写入 `probe_error`（TEXT，迁移新增列）供 API / Agent 展示  
- 不修改 `is_live`（保留上次已知值）；`compute_status_light` 行为不变，但 O1 仍可通过 `checked_at` 验收  

### 6.2 `desktop_events`（新表，Phase 1）

daemon 与 API sidecar 为 **两个进程**，状态贡献经 SQLite outbox 解耦：

```sql
CREATE TABLE IF NOT EXISTS desktop_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,   -- creator.updated
  creator_id TEXT,
  payload_json TEXT,          -- 可选扩展字段
  created_at TEXT NOT NULL,
  delivered_at TEXT           -- NULL = 待 drain
);
CREATE INDEX IF NOT EXISTS idx_desktop_events_pending
  ON desktop_events(delivered_at, created_at)
  WHERE delivered_at IS NULL;
```

**写入（daemon / core）：**

- 在 `creator_live_snapshots` 或 `live_sessions` 相关列 **实际变更** 并 commit 后，`INSERT` 一行 `creator.updated`  
- 同一 creator 同一 tick 多次变更可合并为一条（实现时 compare-and-skip 或 tick 末批量写）  
- **禁止** core 调用 `events_hub.publish`  

**消费（API sidecar）：**

- FastAPI 启动时注册后台协程 `StateEventDrain`（默认间隔 **1–2s**）  
- `SELECT … WHERE delivered_at IS NULL ORDER BY created_at LIMIT N` → `events_hub.publish` → `UPDATE delivered_at`  
- drain 失败不丢事件（`delivered_at` 仍 NULL，下轮重试）；WS 订阅方已有 20s 轮询兜底  

```
┌─────────────┐   INSERT (WAL)   ┌─────────────────┐
│ daemon      │ ───────────────► │ desktop_events  │
│ LiveObserve │                  └────────┬────────┘
└─────────────┘                           │ drain 1–2s
                                 ┌────────▼────────┐
                                 │ API StateEvent  │
                                 │ Drain → EventsHub│
                                 └────────┬────────┘
                                          │ WS creator.updated
                                 ┌────────▼────────┐
                                 │ m2t-desktop     │
                                 └─────────────────┘
```

### 6.3 `monitor_tasks`（新表，Phase 2）

```sql
CREATE TABLE IF NOT EXISTS monitor_tasks (
  id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  task_type TEXT NOT NULL,  -- start_recording | finalize | sync_catalog | download | sync_dynamic | ...
  payload_json TEXT,        -- room_id, aweme_id, session_id, ...
  priority INTEGER NOT NULL DEFAULT 10,  -- 0 = 最高（开录）
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
  dedupe_key TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_monitor_tasks_status_prio
  ON monitor_tasks(status, priority, created_at);
-- 防重复入队：仅 pending/running 参与唯一约束
CREATE UNIQUE INDEX IF NOT EXISTS idx_monitor_tasks_dedupe_active
  ON monitor_tasks(dedupe_key)
  WHERE dedupe_key IS NOT NULL AND status IN ('pending', 'running');
```

**入队规则：**

- `dedupe_key` 示例：`start_recording:{creator_id}`、`sync_catalog:{creator_id}`、`finalize:{session_id}`  
- 检测 tick **只 enqueue**；Executor `claim` 后执行  
- `finalize` 在 `offline_confirm_sec` 满足后 enqueue 一次（见 §8 P2.3）  

**Repo 语义（对齐 `PostProcessJobRepo`）：**

- `claim_pending(limit)`：`UPDATE … WHERE status='pending'` 原子认领，短事务 commit  
- `reset_stale_running(older_than_sec)`：worker 崩溃后回收 `running` → `pending`  
- 每个 worker 独立 `open_db()`（D1）  

### 6.4 既有表（不变更语义）

- `post_process_jobs`：仍仅在 finalize 后 enqueue；Executor **不得** 改 `ffmpeg_pid`（D2，v2 已锁定）  
- `creator_live_snapshots`：观测层 upsert；`checked_at` 每次 poll 更新  
- `live_pipeline_events`：观测写 `detected_*`，执行写 `recording` / `remux`  

---

## 7. 状态贡献与 Desktop 集成

### 7.1 契约

**凡改变以下字段，必须贡献状态：**

- `creator_live_snapshots` 任意列  
- `live_sessions.status` / `ffmpeg_pid` / `offline_since_at`  
- 博主 `monitor_enabled` / `auto_record_override`  

**贡献动作（Phase 1 必做）：**

1. daemon：DB commit 成功后 `INSERT INTO desktop_events (event_type='creator.updated', creator_id=…)`（见 §6.2）  
2. API：`StateEventDrain` 协程 drain outbox → `events_hub.publish({ "type": "creator.updated", "creator_id": "..." })`  
3. `GET /api/creators` 返回最新 `status_light` 字段（已有）；WS 延迟目标 ≤ **2s**（drain 间隔）+ 网络，满足 O2  

**观测 / 开录函数边界（Phase 1）：**

```python
# 伪代码 — scan_and_start 内
live_info = observe_live_state(creator)   # 检测 + upsert + outbox；O3 单测只测此函数
if effective_auto_record(creator, cfg) and live_info and live_info.is_live:
    maybe_start_recording(creator, live_info)  # 快速通道；可 mock
```

### 7.2 Daemon 未运行

- 保持 `refresh_stale_snapshots_when_daemon_idle()`（限流）  
- Desktop 保留 20s 轮询兜底  
- Daemon 卡片：stale lock 清理 + 启动后 8s 健康检查（已实现，纳入验收）  

### 7.3 与 m2t-desktop spec 对齐

| m2t-desktop §4.4 | 本 spec |
|------------------|---------|
| 四色灯语义 | 不变，由 `compute_status_light` 统一 |
| snapshot 由 LiveTick upsert | 改为 **LiveObserve** 职责，并 **必推送** |
| 手动录制 | 不变，依赖 daemon `poll_active` |

---

## 8. 分阶段迁移

### Phase 1 — 状态贡献 + 观测抽函数（1–2 PR）

| 项 | 内容 |
|----|------|
| P1.1 | `scan_and_start` 拆为 `observe_live_state()` + `maybe_start_recording()`；前者满足 O3 |
| P1.2 | 迁移 `desktop_events` + `DesktopEventRepo`；观测/session 变更后 INSERT outbox |
| P1.3 | API `StateEventDrain` 后台协程（1–2s）drain → `events_hub.publish(creator.updated)` |
| P1.4 | API 探测失败：更新 `checked_at`（+ 可选 `probe_error`），修复 snapshot 冻结 |
| P1.5 | 快速通道不变：自动开录仍在 LiveTick 同线程 `_start_recording` |
| P1.6 | 验收 O1/O2/O6；集成测 outbox → WS；Desktop 左侧栏随 poll 更新 |

**不做的：** `monitor_tasks`、SlowTick 搬迁、finalize 入队。

### Phase 2 — 统一任务队列（2–3 PR）

| 项 | 内容 |
|----|------|
| P2.1 | 迁移 `monitor_tasks` 表 + `MonitorTaskRepo`（claim + dedupe UNIQUE + `reset_stale_running`） |
| P2.2 | VOD/archive/dynamic：ContentObserve 只检测 + enqueue；Executor 跑 Playwright |
| P2.3 | **finalize 单入口**：`poll_active` 仅 ffmpeg 存活 / STT / 写 snapshot / 设 `offline_since_at`；**禁止** 在 observe 路径直接 `_finalize_recording`；满 `offline_confirm_sec` 后 `enqueue(finalize)`，LiveObserve tick 末 **同 tick inline drain** `priority=0`（保 G4） |
| P2.4 | 配置：`monitor.executor_max_parallel`（默认 **1**；Playwright job 进程级信号量 ≤1，防多 Chromium OOM） |
| P2.5 | CLI `live status --json` 展示 `monitor_tasks` pending/running |

### Phase 3 — 可选增强

- 任务优先级与公平性（单博主饥饿）  
- `monitor_tasks` 失败重试 / DLQ  
- Desktop 展示队列积压条  

---

## 9. 非目标

- 多机 / Redis 队列  
- 平台 Webhook 推送  
- 改动 `compute_status_light` 四色语义  
- 替换 PostProcess 为通用 Executor（转写仍独立池）  
- 本 spec 内实现 Agent sidecar 变更  

---

## 10. 测试与可观测性

| 层级 | 手段 |
|------|------|
| 单元 | `observe_live_state` mock API 不写 ffmpeg；outbox 仅变更写入；`monitor_tasks` dedupe；stale lock |
| 集成 | daemon upsert → `desktop_events` 行 → API drain → WS `creator.updated`；探测失败更新 `checked_at` |
| 手动 | 主播开播 → 30s 内 🔴/🟢；停 daemon → API refresh；`live timeline` 完整 |

**日志关键字：** `live_observed`, `snapshot_upserted`, `desktop_event_enqueued`, `desktop_event_drained`, `monitor_task_enqueued`.

---

## 11. 与 v2 / Desktop 文档关系

| 文档 | 关系 |
|------|------|
| [Live Pipeline v2](./2026-06-03-live-pipeline-v2-design.md) | v3 **继承** 三线程、D1/D2、G1–G8；**演进** 观测/执行边界与任务表 |
| [m2t-desktop](./2026-06-04-m2t-desktop-design.md) | §4.4 状态灯与 snapshot **实现义务** 在本文 §7 落地 |
| [streaming STT](./2026-06-03-live-streaming-stt-design.md) | finalize / post_process 顺序不变 |

---

## 12. 开放问题与评审决议

| # | 议题 | 决议 |
|---|------|------|
| 1 | Desktop 跨进程推送 | **已锁定：** `desktop_events` outbox + API drain（§6.2、§7.1） |
| 2 | `monitor_tasks` 与 `post_process_jobs` 合并？ | **不合并**（D2 边界、生命周期不同） |
| 3 | Phase 2 开录路径 | **Phase 1–2 保留同步快速通道**；Phase 2 可选 `priority=0` + 同 tick drain，**上线前 benchmark G1** |
| 4 | finalize 所有权 | **已锁定：** 仅 enqueue + 单入口 drain（§8 P2.3），消除与 `poll_active` 双路径 finalize |
| 5 | B 站 / 抖音 Observe 拆分 | **暂缓**；现顺序 `run_once`；若单平台超时拖累另一平台再拆（Phase 3） |

---

## 附录 A：当前代码锚点

| 模块 | 路径 |
|------|------|
| 调度器 | `src/media2text/core/live/scheduler.py` |
| PostProcess 池 | `src/media2text/core/live/post_process_pool.py` |
| 状态灯 | `src/media2text/core/desktop/status_lights.py` |
| Daemon API | `src/media2text/api/services/daemon.py` |
| Stale snapshot API | `src/media2text/api/services/live_snapshot.py` |
| WS 广播 | `src/media2text/api/services/events_hub.py` |
| 进程锁 | `src/media2text/core/process_lock.py` |
| snapshot upsert | `src/media2text/core/live/snapshot.py` |

## 附录 B：名词对照

| 用户表述 | 本 spec 术语 |
|----------|--------------|
| 直播观测 | LiveObserveTick |
| 内容观测 | ContentObserveTick |
| PostProcessPool 执行 | PostProcessExecutor +（Phase 2）MonitorExecutor |
| 状态贡献 | upsert DB + `desktop_events` outbox → API drain → `creator.updated` WS |
