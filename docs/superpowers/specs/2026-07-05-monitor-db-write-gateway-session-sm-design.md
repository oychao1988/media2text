# Monitor DB Write Gateway + Session State Machine — 统一写路径 & 去 MH-3 长连接

**日期:** 2026-07-05  
**状态:** 已定稿（Eng Review 2026-07-05；用户决策：Writer 线程 + 全量 StateMachine）  
**前置:** [Monitor DB Lock DL-1–DL-3](../../issues/README.md#monitor-db-lock-write-path-2026-06-30)（#356–#358）、[MH-3 hybrid conn](../../issues/monitor-hardening-mh3-prepare-playwright-conn.md)（#347）、[Monitor Daemon v3](./2026-06-05-monitor-daemon-observe-execute-design.md)  
**动机:** 2026-07-03 事故 — 僵尸 `live_sessions` + 多线程裸 `commit()` + `watcher._conn` 长连接 → `database is locked` → `live_tick` 停转 → Desktop 显示离线/无反应。

---

## 0. 已锁定决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | **单 Writer 线程 + 单写连接**；所有 SQLite 写经 `DbWriteGateway` | 进程内写者收敛为 1；消除 `_sqlite_write_lock` 与裸 `commit()` 分裂 |
| D2 | **全量 `SessionStateMachine`** 替换 `LiveRecordingCore` 内 poll/offline/finalize 状态逻辑 | 一次性去掉 MH-3；副作用与 DB 生命周期彻底分离 |
| D3 | **长生命周期仅保留 `SessionRuntime`**（ffmpeg Popen、STT session、stream URL 缓存） | MH-3 误把 DB conn 与副作用绑定；Runtime 才是正确边界 |
| D4 | **删除** `MonitorWatcher._conn`、`DouyinLiveWatcher._conn`、`BilibiliLiveWatcher._conn` | 7/3 `lsof` 10+ FD 根因之一 |
| D5 | 读路径：**短连接只读** 或 `gateway.read()`；写路径：**禁止**在 `gateway.write()` 的 fn 内做 HTTP/Playwright/LLM/ffmpeg wait | 延续 DL-1/DL-2 原则 |
| D6 | **deprecate** `_sqlite_write_lock` +  scattered `with_db_lock_retry(open_db…)`；统一为 gateway API | 避免双轨 |
| D7 | recovery：`offline_since_at` 已设 + ffmpeg 死 → **下一 reconcile 立即 finalize**（修 #78） | 7/3 万战寻道僵尸 session 直接原因 |
| D8 | 跨进程（external daemon + serve）**不在本 spec 消灭**；保留 DL-3 external drain 降频 | 单进程内一劳永逸；双进程靠锁文件 + 产品模式 |

未选方案（备查）：

- **仅扩 RLock、不建 Writer 线程** — 用户明确选 Writer 线程  
- **分阶段 hotfix-only MH-4** — 用户明确选全量 StateMachine  
- **Hermes 拆库 / PostgreSQL** — 独立 Epic  

---

## 1. 问题陈述

### 1.1 2026-07-03 事故链

```
万战寻道 session 下播后未 finalize（obs_ffmpeg_alive=0 跳过 mark_stale）
  → live lane 占用（post_process_deferred × 3000+）
  → task_scheduler 与 watcher._conn 抢 SQLite 写锁
  → task_scheduler_db_locked × 47
  → live_tick 停止（最后 tick 15:05，此后 40+ min 无 probe）
  → 老班长在播但 snapshot 冻结在 06:11
```

### 1.2 结构性根因

| 层 | 现状 | 问题 |
|----|------|------|
| 写路径 | ~12 模块 `with_db_lock_retry`；repos **80+** 裸 `commit()` | 进程内写未真正串行 |
| 连接 | Watcher + 2× LiveWatcher 长连接 + scheduler/worker/API 短连接 | 连接数多、持锁时间长 |
| MH-3 | worker claim 用短 conn；core 用 `watcher._conn` | 双连接写同 session；finalize 与 poll 碰撞 |
| recovery | `mark_stale` 要求 `obs_ffmpeg_alive==1`；orphan 2h 阈值 | 下播已确认仍卡住 hours |

DL-1–DL-3 已缓解 probe burst、summarize 长占、external takeover；**未**解决 writer 统一与长连接。

---

## 2. Success Criteria

| ID | 指标 | 目标 | 验收 |
|----|------|------|------|
| W1 | 进程内 `database is locked` | embedded monitor 30min **0** sustained `task_scheduler_db_locked` | `monitor-watch.log` + 压测脚本 |
| W2 | 写连接数 | daemon 运行时 **≤2** 写 FD（gateway + 偶发 migration） | `lsof media2text.db` |
| W3 | live_tick 连续性 | `tick_age_sec` P95 ≤ **2× live_poll** | `GET /api/runtime` |
| W4 | 僵尸 recovery | offline 确认 + dead ffmpeg → finalize 入队 **≤1** scheduler tick | 单测 + 7/3 回归 |
| W5 | 直播全流程 | streaming HLS + STT + segment upload + finalize 不退化 | `pytest tests/unit/test_streaming_*` + `-m live` 抽检 |
| W6 | API 响应 | `GET /api/creators` P95 **<5s**（monitor 负载下） | 手工 / 压测 |
| W7 | 写 fn 禁 I/O | `gateway.write` 内 Playwright 触发 `WriteGuardViolation` | 单测 |
| W8 | shutdown | serve/monitor 退出 **不丢**已 enqueue 写（drain ≤5s） | 单测 |

**非目标（W 不保证）：** external + embedded **两进程**同时写时零 busy（见 §8）。

---

## 3. 目标架构

### 3.1 进程内组件

```
┌──────────────────────────────────────────────────────────────────┐
│ serve 进程 / monitor watch --daemon（单实例 lock）                  │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ LiveTick    │  │ TaskScheduler│  │ Worker pools            │ │
│  │ SlowTick    │  │ SegmentWatch │  │ monexec/postproc/segproc│ │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬─────────────┘ │
│         │                │                      │               │
│         ▼                ▼                      ▼               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ SessionStateMachineRegistry（每 active session 一台）     │   │
│  │  - poll_obs / offline / finalize 编排                     │   │
│  │  - 只调 SessionRuntime 做 ffmpeg/STT                      │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │ gateway.write / read              │
│  ┌──────────────────────────▼───────────────────────────────┐   │
│  │ DbWriteGateway（Writer 线程 + 单 sqlite3.Connection）       │   │
│  │  Queue[WriteOp] → worker thread → commit                   │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐   │
│  │ SessionRuntime（内存，跨 platform 共享）                    │   │
│  │  processes{session_id→Popen}  stt_sessions{…}  stream_urls│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  API routes（读）──── open_db 短连接 SELECT only                 │
│  API routes（写）──── gateway.write only                         │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
                        media2text.db (WAL)
```

### 3.2 与 MH-3 / v3 观测-执行模型关系

- **观测**（probe、poll_obs）：HTTP/Playwright **无 DB**；结果 `gateway.write(snapshot|obs)`  
- **状态**（SessionStateMachine）：唯一 session 生命周期权威（内存 + DB 同步）  
- **执行**（monitor_tasks workers）：I/O 在 worker 线程；**状态变更** 回写 `gateway.write`  
- **快速路径**：开录仍可由 reconcile → `prepare_live_recording` task（G1）；不再 inline 于 poll 内阻塞 gateway  

---

## 4. DbWriteGateway（Writer 线程）

### 4.1 API

新模块：`src/media2text/core/storage/write_gateway.py`

```python
class DbWriteGateway:
    def start(self, db_path: Path) -> None: ...
    def shutdown(self, *, timeout_sec: float = 5.0) -> None: ...

    def write(
        self,
        fn: Callable[[sqlite3.Connection], T],
        *,
        label: str = "",
        timeout_sec: float = 60.0,
    ) -> T:
        """Block caller until fn completes on writer conn. Raises on timeout/error."""

    def read(
        self,
        fn: Callable[[sqlite3.Connection], T],
        *,
        timeout_sec: float = 30.0,
    ) -> T:
        """Opens short-lived read connection (not writer queue). WAL-safe."""

    def write_batch(
        self,
        fn: Callable[[sqlite3.Connection], None],
        *,
        label: str = "batch",
    ) -> None:
        """Single transaction for reconcile+claim (scheduler hot path)."""
```

进程 singleton：`get_write_gateway(cfg) -> DbWriteGateway`；`serve` lifespan 与 `MonitorWatcher` 启动时 `start()`，退出时 `shutdown()`。

### 4.2 Writer 线程语义

```
Caller threads                Writer thread ("db-writer")
     │                              │
     │  write(fn, label)            │
     ├──── enqueue WriteOp ─────────►│ dequeue
     │      (Future)                 │ fn(conn)  # conn 仅在此线程 touch
     │                               │ conn.commit() or rollback
     │◄──── Future.set_result ───────┤
     │                               │
```

- **单连接**：writer 线程持有 **一条** `sqlite3.connect`（`check_same_thread=False`），全程复用  
- **重试**：writer 内捕获 `database is locked`，指数退避（沿用 DL-3：max 6, base 0.2s）  
- **禁止重入**：`write()` 在 writer 线程内调用 → `RuntimeError`（防死锁）  
- **batch**：scheduler 每 tick 一次 `write_batch(reconcile_and_claim)`，减少 commit 次数  

### 4.3 WriteGuard

```python
class WriteGuard:
    """Thread-local: True while writer thread executing fn."""
    @staticmethod
    def assert_no_blocking_io(op: str) -> None: ...
```

在以下入口断言（strict 模式可配置 `monitor.write_guard_strict`）：

- `playwright_exclusive` enter  
- `httpx` / adapter live fetch（若 conn 参数存在则另说）  
- `time.sleep` > 0 in repos  

`ProbeExecutionGuard` 保留；WriteGuard 专注 **writer fn 内**禁止项。

### 4.4 迁移 `with_db_lock_retry`

| 阶段 | 动作 |
|------|------|
| 1 | 实现 gateway；`with_db_lock_retry` 委托 `get_write_gateway().write` |
| 2 | repos 全部 mutator 改 `gateway.write(lambda c: ...)` 或注入 `WriteAwareRepo` |
| 3 | 删除 `_sqlite_write_lock`；删除 scattered `open_db`+write in drains |

**Read 路径不变量：**

- `gateway.read()` = `open_db` + fn + close（只读）  
- 同一逻辑链 write 后需 read → 使用 `write` 返回值，或 `write_batch` 内同事务读  

### 4.5 Repo 层

```python
class WriteAwareRepo:
    def __init__(self, gateway: DbWriteGateway):
        self._gw = gateway

    def _mutate(self, label: str, fn: Callable[[sqlite3.Connection], T]) -> T:
        return self._gw.write(fn, label=label)
```

**P0 mutators（首批）：** `LiveSessionRepo`, `MonitorTaskRepo`, `StateWriter`, `LiveSnapshotRepo`  
**P1：** `PostProcessJobRepo`, `SegmentProcessJobRepo`, `SegmentManifestRepo`, `NotifyEventRepo`, `DesktopEventRepo`  
**P2：** `CreatorRepo`, `AwemeRepo`, Hermes `SessionDB`（同库，经 gateway）

---

## 5. SessionStateMachine（全量）

### 5.1 状态机

**DB 字段：** `live_sessions.status` + `offline_since_at` + obs_* 列  

```
                    prepare / start_ffmpeg
         ┌──────────────────────────────────────┐
         ▼                                      │
     [starting] ──recording──▶ [recording] ─────┤
         │                           │          │
         │ fail                      │ poll:     │ reconnect
         ▼                           │ still_live│
     [failed]              [offline_pending]◄─────┘
         ▲                           │
         │                           │ offline_confirm_sec
         │                           ▼
         │                    [finalizing]
         │                           │
         └───────────────────────────┴──▶ [completed] / [failed]
```

| 状态 | 含义 | DB status |
|------|------|-----------|
| starting | session 行已建，ffmpeg 启动中 | `recording`（兼容）或新值 `starting` |
| recording | ffmpeg 存活，STT 可选 | `recording` |
| offline_pending | 检测到下播，等待 confirm | `recording` + `offline_since_at` |
| finalizing | finalize task running | `remuxing` 或 `finalizing` |
| completed / failed | 终态 | `completed` / `failed` |

**兼容：** 对外 API/Desktop 仍映射 `recording|remuxing|completed|failed`；`starting`/`finalizing` 为新增可选值（migration v9）。

### 5.2 核心类型

新模块：`src/media2text/core/live/session_state.py`

```python
@dataclass(frozen=True)
class SessionHandle:
    session_id: str
    creator_id: str
    platform: str

class SessionStateMachine:
    def __init__(
        self,
        cfg: AppConfig,
        handle: SessionHandle,
        runtime: SessionRuntime,
        gateway: DbWriteGateway,
        adapter: LivePlatformAdapter,
        notify: NotifyService,
    ): ...

    # ── 观测（live_tick Phase1，无 blocking I/O inside gateway.write）──
    def poll_observation(self, row: LiveSessionRow) -> None: ...
    def fetch_still_live(self, creator) -> bool | None: ...  # HTTP, no DB

    # ── 迁移（gateway.write only）──
    def mark_offline_pending(self, offline_since: str) -> None: ...
    def clear_offline_pending(self) -> None: ...
    def transition_to_finalizing(self) -> None: ...
    def complete_finalize(self, *, local_path, ...) -> None: ...
    def fail(self, error: str) -> None: ...

    # ── 副作用（SessionRuntime only, no DB）──
    def start_recording(self, live_info) -> None: ...
    def stop_ffmpeg_and_stt(self) -> None: ...
    def reconnect_ffmpeg(self) -> None: ...
    def reconnect_stt(self) -> None: ...
```

`SessionStateMachineRegistry`（单例 per MonitorWatcher）：

- `get_or_create(session_id)` / `drop(session_id)` on terminal state  
- daemon 启动 `recover_all()` → 为每个 active session 重建 machine + bootstrap STT  

### 5.3 LiveRecordingCore 命运

| 现方法 | 迁移目标 |
|--------|----------|
| `poll_active_recordings` | `LiveObserveService.poll_active()` → registry machines |
| `run_prepare_live_recording` | `SessionStateMachine.start_recording` + gateway writes |
| `run_finalize` / `_finalize_recording_*` | `SessionStateMachine.run_finalize()` |
| `probe_live` | 保持 `LiveRecordingCore.probe_live` 或抽 `LiveProbeService`（无 conn） |
| streaming STT helpers | `SessionRuntime` + machine methods |

**删除：** `LiveRecordingCore.__init__(conn=…)` 长绑定；**保留** 薄 facade `LiveRecordingCore` 一版供 worker dispatch 签名稳定，内部只持 registry/gateway/runtime。

### 5.4 去掉 MH-3

```python
# Before (MH-3)
core = watcher.core_for_platform(watcher._conn, platform)

# After
machine = registry.get(session_id)
machine.run_finalize()  # worker 线程；DB 仅 gateway
```

`MonitorExecutor._core_for_task` **删除**；finalize/prepare/reconnect dispatch 改为 session_id → registry。

### 5.5 Recovery 规则（修 #78 + 7/3）

`recover_all()` on daemon start（经 `gateway.write_batch`）：

| 条件 | 动作 |
|------|------|
| `status=recording` + ffmpeg dead + `offline_since_at` set | enqueue `finalize` priority 0 |
| `status=recording` + ffmpeg dead + no offline + age > 60s + no temp | `failed` / `recording_never_started` |
| `status=recording` + ffmpeg dead + no offline + age > 2h | `failed` / `stale_recording` |
| `status=recording` + ffmpeg alive | bootstrap STT if streaming |

**删除** `mark_stale_recordings_failed` 对 `obs_ffmpeg_alive==0` 的 skip 逻辑。

### 5.6 Douyin/Bilibili LiveWatcher

- 删除 `_conn`、`_core` 长绑定  
- `run_poll_active` → `LiveObserveService.poll_active_recordings(gateway, registry)`  
- `run_probe_observe` → 无 DB；snapshot `gateway.write`  
- `run_finalize` → `registry.recover_stale()` + gateway  

`MonitorWatcher` 删除 `_conn`；VOD/archive/dynamic tick 改用 `gateway.read` + worker 内 `gateway.write`。

---

## 6. 线程与 Gateway 交互矩阵

| 线程 | 读 | 写 | 禁止 |
|------|----|----|------|
| live-probe | `gateway.read` list sessions | `poll_obs`, snapshot | Playwright 在 write fn 内 |
| task-scheduler | — | `write_batch(reconcile+claim)` | 整 tick 持 conn |
| monexec worker | `gateway.read` load task | mark_done, machine side effects via gateway | 长 conn |
| postproc/segproc | read job row | stage updates via gateway | LLM 在 write fn 内（DL-2 已 release） |
| segment-watcher | read parts | enqueue via gateway.write | — |
| API GET | short read conn | — | — |
| API POST | read | gateway.write | — |
| db-writer | — | **唯一** touch writer conn | — |
| STT feeder thread | — | **禁止** DB | 只写 transcript 文件 |

---

## 7. 配置

`config.example.yaml` 新增：

```yaml
monitor:
  write_gateway:
    queue_maxsize: 2000          # 0 = unbounded (dev only)
    write_timeout_sec: 60
    read_timeout_sec: 30
    shutdown_drain_sec: 5
    write_guard_strict: true     # prod true; tests may false
```

---

## 8. 跨进程与「一劳永逸」边界

| 场景 | 本 spec 后 |
|------|------------|
| embedded Desktop（单 serve 进程） | **目标：零 sustained db locked** |
| external `monitor watch` + Desktop UI | 两进程写同一 DB；DL-3 降频 + busy_timeout；**仍可能偶发 busy** |
| CLI 一次性命令 + daemon | 短写 burst；gateway 无关（CLI 独立进程） |

产品级「双进程零锁」需 **API 只读模式** 或 **Unix socket 代理写** — **不在本 spec**。

---

## 9. Issue 拆分与依赖

Epic：`monitor-db-write-path-phase2-2026-07-05`  

| Issue | 标题 | 依赖 | 交付 |
|-------|------|------|------|
| **DL-4a** | `DbWriteGateway` Writer 线程 + lifecycle + 单测 | — | gateway 模块、doctor 指标 |
| **DL-4b** | P0 repos + StateWriter + scheduler `write_batch` | DL-4a | task_scheduler 无 locked |
| **DL-4c** | P1 workers + drains + segment + notify | DL-4b | worker 路径统一 |
| **DL-4d** | P2 API/Hermes + 删除 `_sqlite_write_lock` + audit CI | DL-4c | `scripts/audit_db_writes.py` |
| **MH-4a** | `SessionStateMachine` + Registry + recovery 规则 | DL-4b | 7/3 回归单测 |
| **MH-4b** | 删除 watcher/LiveWatcher 长连接；LiveObserveService | MH-4a, DL-4b | 无 `_conn` |
| **MH-4c** | Worker dispatch 去 MH-3；finalize/prepare/reconnect | MH-4b | monitor_executor 改完 |
| **MH-4d** | `LiveRecordingCore` 瘦身为 facade；删旧 poll/finalize 路径 | MH-4c | recording.py 大幅删减 |
| **E2E-1** | 压测 + 11 博主 mock probe 30min | DL-4d, MH-4d | 验收 W1–W3 |

**推荐合并顺序：** DL-4a → DL-4b → MH-4a → MH-4b → MH-4c → DL-4c → MH-4d → DL-4d → E2E-1  

**不可并行：** `recording.py` 与 `repos.py` 在 MH-4c/DL-4b 后分叉。

---

## 10. 测试计划

### 10.1 单元测试（必须）

| 文件 | 覆盖 |
|------|------|
| `test_db_write_gateway.py` | 并发 write 无 locked；timeout；shutdown drain；writer 线程禁重入 |
| `test_write_guard.py` | Playwright in write fn → violation |
| `test_session_state_machine.py` | 全状态迁移；offline_pending → finalizing |
| `test_session_recovery_offline_finalize.py` | **CRITICAL** 7/3 回归 |
| `test_live_observe_no_long_conn.py` | poll 不持有 watcher._conn |
| `test_monitor_executor_no_mh3.py` | finalize 不取 watcher._conn |
| 扩展 `test_task_scheduler.py` | `write_batch` 单事务 |

### 10.2 压测

`scripts/db_lock_stress.py`（或 `pytest -m db_stress`）：

- embedded monitor mock 11 creators  
- 60s 内 assert `task_scheduler_db_locked == 0`  
- assert `live_tick` max gap < 2 × poll  

### 10.3 回归

```bash
pytest tests/unit/test_streaming_* tests/unit/test_live_worker_tasks.py \
  tests/unit/test_task_scheduler.py tests/unit/test_probe_live_parallel.py -v
pytest tests/unit/test_db_write_gateway.py tests/unit/test_session_state_machine.py -v
```

---

## 11. 迁移与回滚

1. **Feature flag** `monitor.write_gateway.enabled`（默认 false → 单测 true → 默认 true）  
2. Flag false：保留现 `with_db_lock_retry` 路径（仅 DL-4a  land 时）  
3. MH-4 与 gateway 同 flag 或 `monitor.session_state_machine.enabled`  
4. 回滚：flag false + revert MH-4 PR；gateway 线程 `shutdown` 在 supervisor stop  

---

## 12. 开放项（实现时确认）

| # | 项 | 建议 |
|---|-----|------|
| O1 | `starting` / `finalizing` 是否新 status 枚举 | migration v9 增加；Desktop 映射文档 |
| O2 | `gateway.read` 用独立 conn vs WAL 共享读 | 独立短 conn（简单） |
| O3 | Hermes 同进程是否强制 gateway | DL-4d 一并改 |
| O4 | queue_maxsize 满时 backpressure 策略 | block with timeout → log `write_gateway_saturation` |

---

## 13. 文档同步

- `CLAUDE.md`：monitor 线程模型 + gateway 约束  
- `docs/issues/README.md`：Epic manifest  
- 删除 MH-3 issue 中「hybrid conn 永久」描述，标注 superseded by MH-4  

---

## 14. Eng Review 裁决（2026-07-05）

| 项 | 结论 |
|----|------|
| 用户决策 | Writer 线程 + 全量 StateMachine |
| 一劳永逸 | **单进程内**是；跨进程需后续产品决策 |
| 风险 | 大改 `recording.py`；必须 E2E-1 压测 gate |
| Lake Score | 完整 Epic（9 issues），不做 shortcut |
