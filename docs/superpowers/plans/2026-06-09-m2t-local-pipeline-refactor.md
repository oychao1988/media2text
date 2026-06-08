# Local Pipeline Refactor (Execution Engine v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `monitor watch --daemon` into Probe / TaskScheduler / TaskReconciler / Worker layers so live polling never blocks on finalize/remux, tasks are created only by Reconciler, and all session state flows through `StateWriter`.

**Architecture:** Three threads — `LiveProbeThread` (LP-01/02/03 + content poll clocks, DB writes only), `TaskSchedulerThread` (1s tick: reconcile → drain live p0+ → post_process → content), `MonitorExecutor` workers (each job `open_db()`). Migration R1→R4 with `monitor.reconciler_enabled` flag for R2c cutover.

**Tech Stack:** Python 3.12+, threading, SQLite WAL, existing `LiveRecordingCore` / `PostProcessExecutor`, pytest, optional Vitest for Desktop R3a.

**Spec:** [2026-06-08-m2t-local-pipeline-refactor-design.md](../specs/2026-06-08-m2t-local-pipeline-refactor-design.md)

**Status:** 主干已交付（#236 PR5/PR8）；GF-1..4 gap fix（#246–#249）补完 Reconciler 路由、notify outbox、SlowTick conn、StateWriter 收口与 `probe_parallelism`。

**Depends on:** Live Pipeline v2（已交付）、Monitor Daemon v3 Phase 1（`desktop_events` / `observe_live_state` 已部分落地）。

**Blocks:** [Client-Primary 控制面](../specs/2026-06-08-m2t-client-primary-control-plane-design.md) Phase 1 出口需 R2c-3 + R3a + R3b。

### Eng Review 已锁定决策（2026-06-09）

| ID | 决策 |
|----|------|
| D1 | **`SessionRuntime` 单例**挂在 `MonitorWatcher`：共享 `_processes` / `_stt_sessions`；Worker 每任务 `open_db()` 新建 `LiveRecordingCore`，注入同一 runtime |
| D2 | **R1 与 R2a 捆绑同一 PR**：禁止单独合并 R1（否则 finalize 无 drain 会积压） |
| D3 | **Content due 存 DB**：`creators` 表加 `vod_due_at` / `archive_due_at` / `dynamic_due_at`（TEXT ISO）；SlowTick 只 UPDATE due，Reconciler 读 due → `ensure_task` |
| D4 | **R2c 后 Scheduler tick 顺序固定**：`reconcile_live` → `reconcile_content` → drain p0 → live workers → post_process → content |
| D5 | **`live_worker_max_parallel`** 驱动 `MonitorExecutor` pool 大小；`executor_max_parallel` 仅 content lane（p10+）或文档 deprecate |

---

## File map

| File | Phase | Responsibility |
|------|-------|----------------|
| `src/media2text/core/live/scheduler.py` | R1,R2a,R2c | `LiveProbeThread`；移除 sync drain；`MonitorScheduler` 三线程编排 |
| `src/media2text/core/live/task_scheduler.py` | R2a | 1s reconcile+drain 循环 |
| `src/media2text/core/live/task_reconciler.py` | R2c | RR-01..05、RC-01..03 |
| `src/media2text/core/live/state_writer.py` | R2c,R3b | 单写口：snapshot、obs、offline、outbox |
| `src/media2text/core/live/probe_guard.py` | R2c | `ProbeExecutionGuard` |
| `src/media2text/core/live/monitor_executor.py` | R2b,R2a | LW-01..05 handlers；async p0 drain |
| `src/media2text/core/live/session_runtime.py` | R2a | SR-01/02 sidecar：`_processes`、`_stt_sessions`（跨 Worker 线程共享） |
| `src/media2text/core/live/recording.py` | R2a,R2b,R2c | `LiveRecordingCore(..., runtime=...)`；`poll_active_session`（纯 obs）；handler 边界 |
| `src/media2text/core/monitor/watcher.py` | R2a,R2c | 持 `SessionRuntime`；`core_for_conn(conn)`；ContentProbe clock；deprecate 共享 `_conn` 写 |
| `src/media2text/core/live/pipeline_phase.py` | R3a | `pipeline_phase` 投影 |
| `src/media2text/core/live/probe.py` | R2a,R2c | LP-01/02/03 编排 + budget/parallel |
| `src/media2text/core/platform/douyin/live.py` | R2c | `run_once` → probe only |
| `src/media2text/core/platform/bilibili/live.py` | R2c | 同上 |
| `src/media2text/core/storage/db.py` | R2c,R4 | `obs_*` 列；creators `*_due_at`；`notify_events` 表 |
| `src/media2text/core/storage/models.py` | R2c,R3a | `LiveSessionRow.obs_*`；phase 字段 |
| `src/media2text/core/storage/repos.py` | R2c,R4 | `ensure_task`、`cancel_pending`、`NotifyEventRepo` |
| `src/media2text/core/config.py` | R2a,R2c,R4 | `MonitorConfig` 新字段 |
| `src/media2text/core/notify/outbox.py` | R4 | notify outbox enqueue/drain |
| `src/media2text/api/services/notify_event_drain.py` | R4 | sidecar drain → `NotifyService` |
| `config.example.yaml` | R2a–R4 | 文档化新配置 |
| `tests/unit/test_live_scheduler.py` | R1,R2a | 更新/新增闸门测试 |
| `tests/unit/test_task_scheduler.py` | R2a | 新建 |
| `tests/unit/test_task_reconciler.py` | R2c | 新建 |
| `tests/unit/test_state_writer.py` | R2c,R3b | 新建 |
| `tests/unit/test_probe_guard.py` | R2c | 新建 |
| `tests/unit/test_session_runtime.py` | R2a | 新建 |
| `tests/unit/test_live_worker_tasks.py` | R2b | 新建 |
| `tests/unit/test_pipeline_phase.py` | R3a | 新建 |
| `tests/unit/test_notify_outbox.py` | R4 | 新建 |
| `.github/workflows/ci.yml` | R3b | grep 禁 Probe direct repo |
| `docs/superpowers/verification/2026-06-09-m2t-local-pipeline-refactor-acceptance.md` | R2c-3 | Epic 验收表（最后填） |

---

## R0 — 基线

- [ ] **Step 1: 确认环境**

```bash
source .venv/bin/activate
media2text doctor --json
pytest tests/unit/test_live_scheduler.py tests/unit/test_offline_wall_clock.py -v
```

Expected: exit 0；现有 live scheduler 测试全绿。

---

# R1+R2a — 捆绑 PR（Eng Review D2）

**禁止单独合并 R1。** 本 PR 同时交付：删 sync finalize + TaskScheduler drain + 每线程 conn + SessionRuntime + LiveProbe budget。

验收：
- `test_live_tick_not_blocked_by_slow_finalize`
- `test_task_scheduler_drains_priority_zero_async`
- `test_conn_per_thread_no_shared_watcher_conn`（含 100-tick stress）
- `test_session_runtime_shared_across_worker_threads`

---

### Task 1: 移除 LiveTick 内联 finalize drain

**Files:**
- Modify: `src/media2text/core/live/scheduler.py`
- Modify: `tests/unit/test_live_scheduler.py`
- Test: `tests/unit/test_live_scheduler.py`

- [ ] **Step 1: Write failing test**

在 `tests/unit/test_live_scheduler.py` 追加：

```python
def test_live_tick_not_blocked_by_slow_finalize(tmp_path, monkeypatch) -> None:
    """LiveTick must not call sync drain_priority_zero (finalize runs on Scheduler)."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1, post_process_poll_interval_sec=60),
    )
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    post_pool = MagicMock()
    monitor_pool = MagicMock()

    def slow_run_once(**_kwargs) -> dict:
        time.sleep(0.3)
        return {}

    with (
        patch.object(watcher._douyin_live, "run_once", side_effect=slow_run_once),
        patch.object(watcher._bilibili_live, "run_once", return_value={}),
    ):
        live_loop = LiveTickLoop(
            watcher, cfg, post_pool, monitor_pool,
            creator_id=None, stop=stop,
        )
        t0 = time.monotonic()
        live_loop.start()
        time.sleep(0.15)
        stop.set()
        live_loop.join(timeout=2)

    assert time.monotonic() - t0 < 1.0
    monitor_pool.drain_priority_zero.assert_not_called()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/unit/test_live_scheduler.py::test_live_tick_not_blocked_by_slow_finalize -v`

Expected: FAIL — `drain_priority_zero` still called.

- [ ] **Step 3: Remove sync finalize from LiveTickLoop._run**

删除 `scheduler.py` 中 `LiveTickLoop._run` 的这段：

```python
            finalized = self._monitor_pool.drain_priority_zero(
                self._cfg,
                self._watcher._conn,
                notify=self._watcher._notify,
                watcher=self._watcher,
            )
            if finalized:
                log.info("monitor_finalize_drained", count=len(finalized))
```

保留 post_process `drain_pending`（R2a 会迁到 TaskScheduler）。

- [ ] **Step 4: Update test_finalize_enqueued_once_and_drained_inline**

该测试验证 poll enqueue + inline drain；改为仅断言 enqueue（drain 由 R2a TaskScheduler 负责）：

```python
    core.poll_active_recordings()
    tasks = MonitorTaskRepo(conn).count_by_status()
    assert tasks.get("pending", 0) == 1
    assert finalize_calls == []
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_live_scheduler.py -v`

Expected: PASS

- [ ] **Step 6: Run tests（暂不单独 commit — 见 R1+R2a 末尾统一 commit）**

Run: `pytest tests/unit/test_live_scheduler.py -v`

Expected: PASS

---

### Task 2: MonitorConfig 新字段

**Files:**
- Modify: `src/media2text/core/config.py`
- Modify: `config.example.yaml`
- Test: `tests/unit/test_task_scheduler.py`（新建）

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_task_scheduler.py
from media2text.core.config import AppConfig, MonitorConfig

def test_monitor_scheduler_config_defaults() -> None:
    cfg = AppConfig()
    assert cfg.monitor.scheduler_interval_sec == 1
    assert cfg.monitor.live_lane_min_claim_per_tick == 1
    assert cfg.monitor.probe_parallelism == 4
    assert cfg.monitor.reconciler_enabled is False
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_task_scheduler.py::test_monitor_scheduler_config_defaults -v`

- [ ] **Step 3: Extend MonitorConfig**

```python
class MonitorConfig(BaseModel):
    live_poll_interval_sec: int = 60
    vod_poll_interval_sec: int = 300
    max_creators_per_vod_tick: int = 0
    profile_stale_days: int = 7
    executor_max_parallel: int = 1
    stale_running_sec: int = 3600
    task_max_retries: int = 3
    scheduler_interval_sec: int = 1
    reconciler_enabled: bool = False
    live_worker_max_parallel: int = 1
    live_lane_min_claim_per_tick: int = 1
    probe_tick_budget_sec: int = 0  # 0 => 2 * live_poll_interval_sec
    probe_parallelism: int = 4
    probe_http_timeout_sec: int = 5
```

`config.example.yaml` 的 `monitor:` 段追加 spec 附录 B 字段。

- [ ] **Step 4: Run test — PASS**

- [ ] **Step 5: Run test — PASS（随 R1+R2a 统一 commit）**

---

### Task 3: TaskSchedulerThread

**Files:**
- Create: `src/media2text/core/live/task_scheduler.py`
- Modify: `src/media2text/core/live/scheduler.py`
- Modify: `src/media2text/core/live/monitor_executor.py`
- Test: `tests/unit/test_task_scheduler.py`

- [ ] **Step 1: Write failing test — p0 min claim per tick**

```python
def test_task_scheduler_drains_priority_zero_async(tmp_path, monkeypatch) -> None:
    from media2text.core.live.task_scheduler import TaskSchedulerLoop
    from media2text.core.storage.repos import CreatorRepo, MonitorTaskRepo
    from media2text.core.workspace import open_db

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAx", profile_url="https://x", monitor_enabled=True
    )
    MonitorTaskRepo(conn).enqueue(
        creator_id=cid,
        task_type="finalize",
        dedupe_key="finalize:s1",
        priority=0,
        payload_json='{"session_id":"s1"}',
    )
    watcher = MonitorWatcher(cfg)
    stop = threading.Event()
    pool = MagicMock()
    submitted: list[str] = []

    def capture_submit(cfg, *, task_id, notify, watcher=None):
        submitted.append(task_id)

    pool.claim_and_submit_priority_zero = MagicMock(side_effect=capture_submit)

    loop = TaskSchedulerLoop(
        cfg, watcher, pool, post_pool=MagicMock(), stop=stop,
    )
    loop.tick_once(conn)
    assert len(submitted) >= 1
    pool.claim_and_submit_priority_zero.assert_called()
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Add MonitorExecutor.claim_and_submit_priority_zero**

```python
    def claim_and_submit_priority_zero(
        self,
        cfg: AppConfig,
        conn,
        *,
        notify: NotifyService,
        watcher: MonitorWatcher | None = None,
        limit: int = 1,
    ) -> int:
        repo = MonitorTaskRepo(conn)
        repo.reset_stale_running(older_than_sec=cfg.monitor.stale_running_sec)
        claimed = repo.claim_pending(
            limit=limit, max_priority=0, min_priority=0
        )
        for task in claimed:
            self.submit(cfg, task_id=task.id, notify=notify, watcher=watcher)
        return len(claimed)
```

保留 `drain_priority_zero` 但标记 deprecated（R2c-3 删除）。

- [ ] **Step 4: Implement TaskSchedulerLoop**

```python
# src/media2text/core/live/task_scheduler.py
class TaskSchedulerLoop:
    """1s tick (R2a): p0 drain → live workers → post_process.
    R2c+ (reconciler_enabled): reconcile_live → reconcile_content → then drains (D4)."""

    def __init__(self, cfg, watcher, monitor_pool, post_pool, *, stop: threading.Event) -> None:
        ...

    def tick_once(self, conn) -> None:
        # R2c Task 10 adds reconcile_* block here when reconciler_enabled
        min_claim = max(1, self._cfg.monitor.live_lane_min_claim_per_tick)
        self._monitor_pool.claim_and_submit_priority_zero(
            self._cfg, conn,
            notify=self._watcher._notify,
            watcher=self._watcher,
            limit=min_claim,
        )
        self._monitor_pool.drain_pending(
            self._cfg, conn,
            notify=self._watcher._notify,
            watcher=self._watcher,
            limit=self._cfg.monitor.live_worker_max_parallel,
        )
        self._post_pool.drain_pending(
            self._cfg, conn,
            notify=self._watcher._notify,
            limit=self._cfg.live.post_process_max_parallel,
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            conn = open_db(self._cfg)
            try:
                self.tick_once(conn)
            finally:
                conn.close()
            self._stop.wait(timeout=self._cfg.monitor.scheduler_interval_sec)
```

- [ ] **Step 5: Wire MonitorScheduler — 三线程 + pool  sizing（D5）**

`MonitorScheduler.start` 增加 `TaskSchedulerLoop`（线程名 `task-scheduler`）；`LiveTickLoop` 线程名改为 `live-probe`；移除 LiveTick 内 post_process drain、SlowTick 内 `monitor_pool.drain_pending`（迁到 Scheduler）。

`MonitorExecutor` 构造时使用 `max_workers=cfg.monitor.live_worker_max_parallel`（live lane）；content drain 仍受 `executor_max_parallel` 或后续统一。

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_task_scheduler.py tests/unit/test_live_scheduler.py -v`

---

### Task 4: 每线程 open_db（Probe + Scheduler）

**Files:**
- Modify: `src/media2text/core/live/scheduler.py`
- Modify: `src/media2text/core/live/probe.py`（新建，见 Task 5 可先 inline）
- Test: `tests/unit/test_task_scheduler.py`

- [ ] **Step 1: Write failing test**

```python
def test_conn_per_thread_no_shared_watcher_conn(tmp_path, monkeypatch) -> None:
    """Probe and Scheduler each open_db; no cross-thread writes on watcher._conn."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(live_poll_interval_sec=1),
        monitor=MonitorConfig(scheduler_interval_sec=1),
    )
    watcher = MonitorWatcher(cfg)
    shared_conn_ids: set[int] = {id(watcher._conn)}
    probe_conn_ids: list[int] = []
    scheduler_conn_ids: list[int] = []

    orig_open = open_db

    def tracking_open_db(c):
        conn = orig_open(c)
        tid = threading.current_thread().name
        if tid == "live-probe":
            probe_conn_ids.append(id(conn))
        elif tid == "task-scheduler":
            scheduler_conn_ids.append(id(conn))
        return conn

    monkeypatch.setattr("media2text.core.live.scheduler.open_db", tracking_open_db)
    monkeypatch.setattr(
        "media2text.core.live.probe.run_live_probe_tick",
        lambda *a, **k: {},
    )

    stop = threading.Event()
    sched = MonitorScheduler(cfg, watcher, creator_id=None, stop=stop)
    sched.start()
    time.sleep(2.5)
    stop.set()
    sched.join(timeout=5)

    assert probe_conn_ids, "live-probe thread should open_db"
    assert scheduler_conn_ids, "task-scheduler thread should open_db"
    assert shared_conn_ids.isdisjoint(set(probe_conn_ids))
    assert shared_conn_ids.isdisjoint(set(scheduler_conn_ids))
```

- [ ] **Step 2: Stress variant — 100 ticks without database is locked**

```python
def test_conn_per_thread_stress_no_sqlite_lock(tmp_path, monkeypatch) -> None:
    """100 parallel probe+scheduler ticks — no intermittent database is locked."""
    ...
    assert not lock_errors
```

- [ ] **Step 3–5: Refactor LiveTickLoop._run**

每 tick 开头 `conn = open_db(cfg)`，传入 platform `run_once(conn=...)` 或 probe 模块；**禁止** `LiveSessionRepo(self._watcher._conn)`。

`MonitorWatcher._conn` 保留只读 CLI 路径，daemon 写路径 deprecate（注释 + log warning 若 detect 跨线程写）。

- [ ] **Step 6: Run**

Run: `pytest tests/unit/test_task_scheduler.py::test_conn_per_thread_no_shared_watcher_conn -v`

---

### Task 5: LiveProbe 模块（LP-01 budget / parallel）

**Files:**
- Create: `src/media2text/core/live/probe.py`
- Modify: `src/media2text/core/platform/douyin/live.py`
- Modify: `src/media2text/core/platform/bilibili/live.py`

- [ ] **Step 1: Extract probe_live tick**

```python
# src/media2text/core/live/probe.py
def probe_budget_sec(cfg: AppConfig) -> float:
    if cfg.monitor.probe_tick_budget_sec > 0:
        return float(cfg.monitor.probe_tick_budget_sec)
    live_poll = cfg.live.live_poll_interval_sec or cfg.monitor.live_poll_interval_sec
    return 2.0 * live_poll

def run_live_probe_tick(cfg, conn, *, douyin, bilibili, creator_id=None) -> dict:
    deadline = time.monotonic() + probe_budget_sec(cfg)
    dy = douyin.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
    bi = bilibili.run_once(conn=conn, creator_id=creator_id, deadline=deadline)
    return {"douyin": dy, "bilibili": bi}
```

R2c 前 `run_once` 仍含 scan/poll legacy；R2a 仅保证 budget 截断与 parallel scan（复用 `scan_concurrency`）。

- [ ] **Step 2: Test probe respects budget**

```python
def test_probe_tick_respects_budget(tmp_path, monkeypatch):
    ...
    assert elapsed < cfg.monitor.probe_tick_budget_sec + 0.5
```

---

### Task 5b: SessionRuntime（Eng Review D1）

**Files:**
- Create: `src/media2text/core/live/session_runtime.py`
- Modify: `src/media2text/core/live/recording.py`
- Modify: `src/media2text/core/monitor/watcher.py`
- Create: `tests/unit/test_session_runtime.py`

- [ ] **Step 1: Write failing test**

```python
def test_session_runtime_shared_across_worker_threads(tmp_path, monkeypatch) -> None:
    """Two Worker threads with separate open_db cores share ffmpeg process map."""
    from media2text.core.live.session_runtime import SessionRuntime
    from media2text.core.live.recording import LiveRecordingCore

    runtime = SessionRuntime()
    cfg = AppConfig(workspace=tmp_path / "data")
    conn_a = open_db(cfg)
    conn_b = open_db(cfg)
    core_a = LiveRecordingCore(cfg, conn=conn_a, runtime=runtime, ...)
    core_b = LiveRecordingCore(cfg, conn=conn_b, runtime=runtime, ...)
    fake_proc = MagicMock()
    runtime.processes["s1"] = fake_proc
    assert core_b._process_alive("s1")  # reads shared runtime.processes
```

- [ ] **Step 2: Implement SessionRuntime**

```python
# src/media2text/core/live/session_runtime.py
@dataclass
class SessionRuntime:
    """SR-01/02: in-process sidecar state shared by all LiveRecordingCore instances."""
    processes: dict[str, Popen] = field(default_factory=dict)
    stt_sessions: dict[str, StreamingSttSession] = field(default_factory=dict)
```

从 `LiveRecordingCore.__init__` 移除 per-instance dict 绑定；改为 `self._runtime = runtime or SessionRuntime()`；`_processes` / `_stt_sessions` 属性委托 runtime。

- [ ] **Step 3: MonitorWatcher 持有 runtime + core_for_conn**

```python
class MonitorWatcher:
    def __init__(self, cfg: AppConfig) -> None:
        ...
        self._session_runtime = SessionRuntime()

    def core_for_conn(self, conn) -> LiveRecordingCore:
        return LiveRecordingCore(
            self._cfg,
            conn=conn,
            runtime=self._session_runtime,
            adapter=self._adapter,
            platform=self._platform,
            notify=self._notify,
        )
```

Worker `_dispatch_task` 经 `watcher.core_for_conn(conn)` 获取 core（R2b 沿用）。

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_session_runtime.py -v`

- [ ] **Step 5: R1+R2a 统一 commit**

```bash
git add src/media2text/core/live/scheduler.py \
  src/media2text/core/live/task_scheduler.py \
  src/media2text/core/live/monitor_executor.py \
  src/media2text/core/live/probe.py \
  src/media2text/core/live/session_runtime.py \
  src/media2text/core/live/recording.py \
  src/media2text/core/monitor/watcher.py \
  src/media2text/core/config.py \
  config.example.yaml \
  tests/unit/test_live_scheduler.py \
  tests/unit/test_task_scheduler.py \
  tests/unit/test_session_runtime.py
git commit -m "feat(monitor): R1+R2a async finalize drain, TaskScheduler, SessionRuntime"
```

---

# R2b — Live Worker 任务化（LW-01..04）

**Depends on:** Task 5b（SessionRuntime）已合并。

验收：`test_prepare_live_recording_task`、`test_reconnect_recording_task`、`test_reconnect_streaming_stt_task`、`test_start_streaming_stt_task`。

---

### Task 6: monitor_executor dispatch LW-01..04

**Files:**
- Modify: `src/media2text/core/live/monitor_executor.py`
- Modify: `src/media2text/core/live/recording.py`
- Create: `tests/unit/test_live_worker_tasks.py`

- [ ] **Step 1: Write failing tests (one per handler)**

```python
def test_prepare_live_recording_task(tmp_path, monkeypatch):
    """LW-01: prepare_live_recording spawns ffmpeg when snapshot has stream."""
    ...

def test_reconnect_recording_task(tmp_path, monkeypatch):
    """LW-03: reconnect_recording calls _reconnect_segment when obs says dead ffmpeg."""
    ...

def test_start_streaming_stt_task(tmp_path, monkeypatch):
    """LW-02: start_streaming_stt builds STT session on active recording."""
    ...

def test_reconnect_streaming_stt_task(tmp_path, monkeypatch):
    """LW-04: reconnect_streaming_stt wraps STT disconnect/reconnect path."""
    ...
```

- [ ] **Step 2: Add handler functions on LiveRecordingCore**

```python
    def run_prepare_live_recording(self, creator_id: str, *, live_info: LiveRoomInfo | None = None) -> dict:
        """LW-01: resolve stream if needed, create session, spawn ffmpeg."""
        ...

    def run_reconnect_recording(self, session_id: str) -> dict:
        """LW-03: ffmpeg reconnect — wraps _reconnect_segment."""
        ...

    def run_start_streaming_stt(self, session_id: str) -> dict:
        """LW-02: start STT sidecar."""
        ...

    def run_reconnect_streaming_stt(self, session_id: str) -> dict:
        """LW-04: STT reconnect — wraps _handle_stt_disconnect path."""
        ...
```

- [ ] **Step 3: Extend _dispatch_task**

```python
    if task.task_type == "prepare_live_recording":
        return _run_prepare_live_recording(cfg, conn, task, watcher=watcher)
    if task.task_type == "reconnect_recording":
        return _run_reconnect_recording(cfg, conn, task, watcher=watcher)
    if task.task_type == "start_streaming_stt":
        return _run_start_streaming_stt(cfg, conn, task, watcher=watcher)
    if task.task_type == "reconnect_streaming_stt":
        return _run_reconnect_streaming_stt(cfg, conn, task, watcher=watcher)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_live_worker_tasks.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(live): add LW-01..04 monitor task handlers (R2b)"
```

---

# R2c — 架构切流（2–3 PR）

**PR 顺序：** R2c-1 → R2c-2 → R2c-3。合并 R2c-3 前必须 `test_probe_never_enqueues` 绿。

---

## R2c-1 — Schema + Reconciler + StateWriter 最小集

### Task 7: obs_* migration

**Files:**
- Modify: `src/media2text/core/storage/db.py`
- Modify: `src/media2text/core/storage/models.py`
- Test: `tests/unit/test_live_db_migration.py`（或扩展现有 migration test）

- [ ] **Step 1: Failing test**

```python
def test_live_sessions_obs_columns(tmp_path):
    conn = connect(tmp_path / "media2text.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(live_sessions)").fetchall()}
    assert {"obs_ffmpeg_alive", "obs_stt_alive", "obs_still_live", "obs_polled_at"} <= cols
```

- [ ] **Step 2: Add `_migrate_live_sessions_v5`**

```python
_LIVE_SESSION_V5_COLUMNS = (
    ("obs_ffmpeg_alive", "INTEGER"),
    ("obs_stt_alive", "INTEGER"),
    ("obs_still_live", "INTEGER"),
    ("obs_polled_at", "TEXT"),
)
```

- [ ] **Step 3: Extend LiveSessionRow**

```python
    obs_ffmpeg_alive: int | None = None
    obs_stt_alive: int | None = None
    obs_still_live: int | None = None
    obs_polled_at: str | None = None
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(db): add live_sessions obs_* columns (R2c-1)"
```

---

### Task 8: MonitorTaskRepo.ensure_task + cancel_pending

**Files:**
- Modify: `src/media2text/core/storage/repos.py`
- Test: `tests/unit/test_monitor_task_repo.py`

- [ ] **Step 1: Tests**

```python
def test_ensure_task_idempotent(conn, creator_id):
    repo = MonitorTaskRepo(conn)
    k = "prepare:c1"
    id1 = repo.ensure_task(creator_id=creator_id, task_type="prepare_live_recording", dedupe_key=k, priority=1)
    id2 = repo.ensure_task(creator_id=creator_id, task_type="prepare_live_recording", dedupe_key=k, priority=1)
    assert id1
    assert id2 is None  # second call no-op

def test_cancel_pending_only_pending(conn, creator_id):
    repo = MonitorTaskRepo(conn)
    tid = repo.enqueue(creator_id=creator_id, task_type="finalize", dedupe_key="finalize:s1", priority=0)
    n = repo.cancel_pending(dedupe_key="finalize:s1")
    assert n == 1
    assert repo.get(tid).status == "cancelled"

def test_ensure_task_noop_when_running(conn, creator_id):
    """Dedupe index covers pending|running — ensure must not duplicate running task."""
    repo = MonitorTaskRepo(conn)
    k = "finalize:s1"
    tid = repo.enqueue(creator_id=creator_id, task_type="finalize", dedupe_key=k, priority=0)
    repo.mark_running(tid)
    assert repo.ensure_task(creator_id=creator_id, task_type="finalize", dedupe_key=k, priority=0) is None
```

- [ ] **Step 2: Implement**

```python
    def ensure_task(self, *, creator_id, task_type, dedupe_key, priority, payload_json=None) -> str | None:
        return self.enqueue(
            creator_id=creator_id,
            task_type=task_type,
            dedupe_key=dedupe_key,
            priority=priority,
            payload_json=payload_json,
        )

    def cancel_pending(self, *, dedupe_key: str) -> int:
        cur = self._conn.execute(
            """
            UPDATE monitor_tasks SET status = 'cancelled', finished_at = ?
            WHERE dedupe_key = ? AND status = 'pending'
            """,
            (datetime.now(timezone.utc).isoformat(), dedupe_key),
        )
        self._conn.commit()
        return cur.rowcount

    def has_active_dedupe(self, dedupe_key: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1 FROM monitor_tasks
            WHERE dedupe_key = ? AND status IN ('pending', 'running')
            LIMIT 1
            """,
            (dedupe_key,),
        ).fetchone()
        return row is not None
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(monitor): ensure_task and cancel_pending on monitor_tasks (R2c-1)"
```

---

### Task 9: StateWriter 最小集

**Files:**
- Create: `src/media2text/core/live/state_writer.py`
- Test: `tests/unit/test_state_writer.py`

- [ ] **Step 1: Failing tests**

```python
def test_set_offline_since_dual_writes_obs(conn, session_id):
    from media2text.core.live.state_writer import StateWriter
    sw = StateWriter(conn, cfg=AppConfig())
    iso = "2026-06-09T12:00:00+00:00"
    sw.set_offline_since(session_id, iso)
    row = LiveSessionRepo(conn).get(session_id)
    assert row.offline_since_at == iso
    assert row.obs_still_live == 0

def test_clear_offline_since_restores_obs(conn, session_id):
    ...
    sw.clear_offline_since(session_id)
    assert row.offline_since_at is None
    assert row.obs_still_live == 1
```

- [ ] **Step 2: Implement StateWriter**

```python
class StateWriter:
    def __init__(self, conn, *, cfg: AppConfig, notify: NotifyService | None = None) -> None:
        self._conn = conn
        self._cfg = cfg
        self._sessions = LiveSessionRepo(conn)
        self._notify = notify or NotifyService(cfg)

    def write_obs(
        self,
        session_id: str,
        *,
        ffmpeg_alive: bool | None,
        stt_alive: bool | None,
        still_live: bool | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE live_sessions SET
              obs_ffmpeg_alive = COALESCE(?, obs_ffmpeg_alive),
              obs_stt_alive = COALESCE(?, obs_stt_alive),
              obs_still_live = COALESCE(?, obs_still_live),
              obs_polled_at = ?
            WHERE id = ?
            """,
            (
                None if ffmpeg_alive is None else int(ffmpeg_alive),
                None if stt_alive is None else int(stt_alive),
                None if still_live is None else int(still_live),
                now,
                session_id,
            ),
        )
        self._conn.commit()

    def set_offline_since(self, session_id: str, iso: str, *, creator_id: str) -> None:
        self._sessions.set_offline_since(session_id, iso)
        self.write_obs(session_id, still_live=False, ffmpeg_alive=None, stt_alive=None)
        record_event(self._conn, session_id=session_id, stage="recording", status="offline_pending")
        self._emit_live_ended(creator_id, session_id)
        enqueue_creator_updated(self._conn, creator_id)

    def clear_offline_since(self, session_id: str, *, creator_id: str) -> None:
        self._sessions.clear_offline_since(session_id)
        self.write_obs(session_id, still_live=True, ffmpeg_alive=None, stt_alive=None)
        record_event(self._conn, session_id=session_id, stage="recording", status="offline_cancelled")
        enqueue_creator_updated(self._conn, creator_id)
```

`_emit_live_ended` 从 `recording.py` 迁入或委托（R4 改 outbox）。

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(live): StateWriter minimal set for obs and offline (R2c-1)"
```

---

### Task 10: TaskReconciler

**Files:**
- Create: `src/media2text/core/live/task_reconciler.py`
- Modify: `src/media2text/core/live/task_scheduler.py`
- Test: `tests/unit/test_task_reconciler.py`

- [ ] **Step 1: Failing tests**

```python
def test_scheduler_reconcile_prepare_when_live_no_session(conn, creator_live_snapshot):
    from media2text.core.live.task_reconciler import reconcile_live
    n = reconcile_live(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"prepare:{creator_id}")

def test_scheduler_reconcile_finalize_when_offline_confirmed(conn, session_offline_past_confirm):
    reconcile_live(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{session_id}")

def test_offline_flash_recovery_cancels_pending_finalize(conn, session_offline_then_live):
    reconcile_live(cfg, conn)  # creates finalize
    # simulate obs_still_live=true
    reconcile_live(cfg, conn)
    assert not MonitorTaskRepo(conn).has_active_dedupe(f"finalize:{session_id}")
```

- [ ] **Step 2: Implement reconcile_live**

```python
def reconcile_live(cfg: AppConfig, conn) -> int:
    ensured = 0
    creators = CreatorRepo(conn).list_monitored()
    snapshots = {s.creator_id: s for s in ...}
    sessions = LiveSessionRepo(conn)
    tasks = MonitorTaskRepo(conn)
    for creator in creators:
        snap = snapshots.get(creator.id)
        active = sessions.get_active_for_creator(creator.id)
        # RR-01
        if snap and snap.is_live and effective_auto_record(creator, cfg) and not active:
            if tasks.ensure_task(
                creator_id=creator.id,
                task_type="prepare_live_recording",
                dedupe_key=f"prepare:{creator.id}",
                priority=1,
            ):
                ensured += 1
        if not active:
            continue
        row = active
        # RR-02 inverse: flash recovery
        if row.obs_still_live and tasks.has_active_dedupe(f"finalize:{row.id}"):
            tasks.cancel_pending(dedupe_key=f"finalize:{row.id}")
        # RR-02 finalize
        if row.offline_since_at and _offline_confirmed(cfg, row):
            if tasks.ensure_task(..., task_type="finalize", dedupe_key=f"finalize:{row.id}", priority=0, ...):
                ensured += 1
        # RR-03..05 using obs_* columns
        ...
    return ensured
```

- [ ] **Step 3: Implement reconcile_content（D3）**

```python
def reconcile_content(cfg: AppConfig, conn) -> int:
    ensured = 0
    now = datetime.now(timezone.utc)
    for creator in CreatorRepo(conn).list_monitored():
        if creator.vod_due_at and _parse_iso(creator.vod_due_at) <= now:
            if MonitorTaskRepo(conn).ensure_task(
                creator_id=creator.id,
                task_type="sync_catalog",
                dedupe_key=f"sync_catalog:{creator.id}",
                priority=10,
            ):
                ensured += 1
        # RC-02 archive_due_at → sync_archive (bilibili)
        # RC-03 dynamic_due_at → sync_dynamic (bilibili)
    return ensured
```

- [ ] **Step 4: TaskSchedulerLoop.tick_once — reconcile 先于 drain（D4）**

```python
        if self._cfg.monitor.reconciler_enabled:
            reconcile_live(self._cfg, conn)
            reconcile_content(self._cfg, conn)
        elif self._cfg.monitor.reconciler_log_only:
            log.info("reconcile_shadow", **shadow_stats(reconcile_live(...)))
        # then existing drain block (p0 → live → post_process → content)
```

- [ ] **Step 5: test_scheduler_tick_order**

```python
def test_scheduler_tick_order_reconcile_before_drain(monkeypatch, conn):
    calls: list[str] = []
    monkeypatch.setattr(task_reconciler, "reconcile_live", lambda *a, **k: calls.append("live") or 0)
    monkeypatch.setattr(task_reconciler, "reconcile_content", lambda *a, **k: calls.append("content") or 0)
    monkeypatch.setattr(pool, "claim_and_submit_priority_zero", lambda *a, **k: calls.append("drain") or 0)
    loop.tick_once(conn)
    assert calls.index("live") < calls.index("drain")
    assert calls.index("content") < calls.index("drain")
```

`reconciler_log_only` 可选，R2c-2 shadow 用；默认 false。

- [ ] **Step 6: Commit — PR R2c-1**

```bash
git commit -m "feat(monitor): TaskReconciler and StateWriter wiring (R2c-1)"
# gh pr create — flag reconciler_enabled default false
```

---

## R2c-2 — Probe 纯传感 + Guard

### Task 11: poll_active_session 纯 obs

**Files:**
- Modify: `src/media2text/core/live/recording.py`
- Test: `tests/unit/test_poll_active_obs.py`

- [ ] **Step 1: Add poll_active_session (new method)**

从 `poll_active_recordings` 抽出 LP-02 逻辑：**只**检测进程存活 + API still_live + StateWriter offline 双写；**删除** `_enqueue_finalize`、`_reconnect_segment`、`_handle_stt_disconnect` 调用。

```python
    def poll_active_session(self, row, creator, *, state: StateWriter) -> None:
        ffmpeg_alive = self._process_alive(row.ffmpeg_pid or 0)
        stt_alive = None
        if self._use_streaming_pipeline(row.id):
            stt = self._stt_sessions.get(row.id)
            stt_alive = stt.is_alive() if stt else False
        still_live = self._recording_still_live(creator, row)
        state.write_obs(
            row.id,
            ffmpeg_alive=ffmpeg_alive,
            stt_alive=stt_alive,
            still_live=still_live,
        )
        # offline semantics via state.set_offline_since / clear_offline_since only
        ...
```

- [ ] **Step 2: test_poll_active_writes_obs_only**

```python
def test_poll_active_writes_obs_only(monkeypatch, conn, active_session):
    enqueue = MagicMock()
    monkeypatch.setattr(MonitorTaskRepo, "enqueue", enqueue)
    core.poll_active_session(...)
    enqueue.assert_not_called()
    row = LiveSessionRepo(conn).get(session_id)
    assert row.obs_polled_at is not None
```

- [ ] **Step 3: Legacy path gate**

`poll_active_recordings` 在 `reconciler_enabled=False` 时保留旧行为；`True` 时 delegate 到 `poll_active_session` only。

- [ ] **Step 4: Commit**

---

### Task 12: ProbeExecutionGuard

**Files:**
- Create: `src/media2text/core/live/probe_guard.py`
- Modify: `src/media2text/core/storage/repos.py`（enqueue hook）
- Test: `tests/unit/test_probe_guard.py`

- [ ] **Step 1: Implement guard**

```python
_probe_ctx = threading.local()

class ProbeExecutionGuard:
    @staticmethod
    def enter_probe_tick() -> None:
        _probe_ctx.active = True
        _probe_ctx.violations = []

    @staticmethod
    def exit_probe_tick(*, strict: bool = False) -> None:
        v = getattr(_probe_ctx, "violations", [])
        _probe_ctx.active = False
        if v and strict:
            raise ProbeViolationError(v)
        if v:
            log.error("probe_guard_violation", violations=v)

    @staticmethod
    def record_violation(name: str) -> None:
        if getattr(_probe_ctx, "active", False):
            _probe_ctx.violations.append(name)
```

Hook 点（spec I.3）：

| API | Hook |
|-----|------|
| `MonitorTaskRepo.enqueue` | `record_violation("enqueue")` |
| `MonitorTaskRepo.ensure_task` | `record_violation("ensure_task")` |
| `subprocess.Popen` | wrapper 在 probe tick 内 `record_violation("Popen")` |
| `LiveRecordingCore._start_recording` | `record_violation("_start_recording")` |

```python
    def ensure_task(self, ...):
        ProbeExecutionGuard.record_violation("ensure_task")
        return self.enqueue(...)
```

- [ ] **Step 2: test_probe_never_enqueues**

```python
def test_probe_never_enqueues(monkeypatch, cfg, conn):
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Popen in probe")))
    monkeypatch.setattr(MonitorTaskRepo, "enqueue", lambda *a, **k: (_ for _ in ()).throw(AssertionError("enqueue in probe")))
    with ProbeExecutionGuard.enter_probe_tick():
        run_live_probe_tick(cfg, conn, ...)
    ProbeExecutionGuard.exit_probe_tick(strict=True)
```

- [ ] **Step 3: creators content due migration（D3）**

**Files:** `src/media2text/core/storage/db.py`, `models.py`, `repos.py`

```python
_CREATOR_V6_COLUMNS = (
    ("vod_due_at", "TEXT"),
    ("archive_due_at", "TEXT"),
    ("dynamic_due_at", "TEXT"),
)
```

Test: `test_creators_content_due_columns`

- [ ] **Step 4: SlowTick 只写 `*_due_at`**

`SlowTickLoop` 删除 in-memory `last_vod`/`last_archive`/`last_dynamic`（`scheduler.py:147-160`）；到期时 `CreatorRepo.set_vod_due(creator_id, iso)` 等，**不** enqueue。

`watcher._run_pipeline_tick` / `_run_dynamic_tick`：删除 `MonitorTaskRepo.enqueue`；Reconciler（Task 10）读 due → `ensure_task`.

- [ ] **Step 5: Commit — PR R2c-2**

---

## R2c-3 — 删 legacy + 默认 reconciler_enabled

### Task 13: Platform run_once probe-only

**Files:**
- Modify: `src/media2text/core/platform/douyin/live.py`
- Modify: `src/media2text/core/platform/bilibili/live.py`

- [ ] **Step 1: Replace run_once body**

```python
    def run_once(self, *, conn, creator_id=None, deadline=None) -> dict:
        if not cfg.monitor.reconciler_enabled:
            return self._run_once_legacy(...)
        core = self._watcher.core_for_conn(conn)  # shared SessionRuntime
        finalized_meta = []
        for row in core._sessions.list_active():
            core.poll_active_session(row, creator, state=StateWriter(conn, cfg=self._cfg))
        started_obs = core.probe_live(creator_id=creator_id, deadline=deadline)  # LP-01
        stale = core._sessions.mark_stale_recordings_failed()
        return {"probe": True, "stale": stale, ...}
```

删除 `scan_and_start` 从 probe path（RR-01 → LW-01）。

- [ ] **Step 2: Default reconciler_enabled true**

`MonitorConfig.reconciler_enabled: bool = True`；删除 `_run_once_legacy` 与 `poll_active_recordings` enqueue 分支。

- [ ] **Step 3: Rename LiveTickLoop → LiveProbeThread**（可选，线程名 `live-probe`）

- [ ] **Step 4: Full test suite + E2E**

Run:

```bash
pytest tests/unit/test_probe_guard.py tests/unit/test_task_reconciler.py \
  tests/unit/test_poll_active_obs.py tests/unit/test_live_worker_tasks.py -v
pytest tests/unit/test_live_scheduler.py tests/unit/test_task_scheduler.py -v
```

- [ ] **Step 5: Commit — PR R2c-3**

```bash
git commit -m "feat(monitor): enable reconciler by default; probe-only architecture (R2c-3)"
```

---

# R3a — pipeline_phase + API/Desktop

### Task 14: pipeline_phase 投影

**Files:**
- Create: `src/media2text/core/live/pipeline_phase.py`
- Modify: `src/media2text/api/routes/creators.py`
- Test: `tests/unit/test_pipeline_phase.py`

- [ ] **Step 1: Tests for phase mapping**

```python
@pytest.mark.parametrize("session,post_jobs,expected", [
    (None, [], "offline"),
    (recording_no_offline, [], "recording"),
    (recording_offline_pending, [], "offline_pending"),
    ...
])
def test_pipeline_phase_derivation(session, post_jobs, expected):
    assert derive_pipeline_phase(session, post_jobs=post_jobs) == expected
```

Phase 链：`offline` → `live_unrecorded` → `recording` / `recording_stt_pending` → `offline_pending` → `finalizing` → `post_processing` → `completed` | `failed`

- [ ] **Step 2: Implement derive_pipeline_phase**

读 `live_sessions` + in-flight `monitor_tasks` + `post_process_jobs`。

- [ ] **Step 3: API `GET /api/creators` 增加 `pipeline_phase`**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(live): pipeline_phase projection for API and Desktop (R3a)"
```

---

# R3b — StateWriter 全量收口

### Task 15: 迁移 direct repo 写 + CI grep

**Files:**
- Modify: `src/media2text/core/live/recording.py`（session 更新经 StateWriter）
- Modify: `src/media2text/core/live/state_writer.py`
- Create: `scripts/check_no_direct_live_repo.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: test_no_direct_repo_outside_state_writer**

CI script 失败若 `recording.py` / `platform/*/live.py` 含 `LiveSessionRepo(...).set_offline_since` 等（allowlist `state_writer.py`）。

- [ ] **Step 2: 逐函数迁移** — `update_status`、`set_offline_since`、manifest refresh 等进 StateWriter。

R3b 收口：`set_offline_since` / `clear_offline_since` 用 `BEGIN IMMEDIATE` 单事务写 session + obs + event + outbox；加 `test_offline_since_atomic`。

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(live): route all session writes through StateWriter (R3b)"
```

---

# R4 — notify_events outbox

### Task 16: notify outbox DDL + drain

**Files:**
- Modify: `src/media2text/core/storage/db.py`
- Create: `src/media2text/core/notify/outbox.py`
- Create: `src/media2text/api/services/notify_event_drain.py`
- Modify: `src/media2text/api/app.py`
- Modify: `src/media2text/core/live/state_writer.py`
- Test: `tests/unit/test_notify_outbox.py`

- [ ] **Step 1: Migration notify_events**（spec 附录 A SQL）

- [ ] **Step 2: NotifyEventRepo + enqueue in StateWriter**

`set_offline_since` 写 `notify_events` kind=`live_ended` 而非 `notify.emit` sync。

- [ ] **Step 3: Sidecar drain loop**（mirror `state_event_drain.py`）

- [ ] **Step 4: test_notify_outbox_only**

```python
def test_notify_outbox_only(monkeypatch, conn):
    monkeypatch.setattr(NotifyService, "emit", lambda *a, **k: pytest.fail("sync emit"))
    sw.set_offline_since(...)
    assert NotifyEventRepo(conn).count_pending() == 1
```

- [ ] **Step 5: `notify.outbox_only: true` enforce** — `NotifyService.emit` 在 daemon 路径 raise 或 no-op+log。

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(notify): notify_events outbox with sidecar drain (R4)"
```

---

## Epic 验收

R2c-3 合并后创建并填写：

`docs/superpowers/verification/2026-06-09-m2t-local-pipeline-refactor-acceptance.md`

| ID | 验收项 | 命令/证据 |
|----|--------|-----------|
| G1 | Probe 零 enqueue/subprocess | `pytest tests/unit/test_probe_guard.py -v` |
| G1′ | 开录 P95 ≤30s | `media2text live stats --days 1 --json` + pipeline_events |
| G3/G4 | offline→live_ended；confirm+finalize ≤60s | unit + 一场真实直播 |
| G5 | Content 不拖 Probe | `test_live_tick_runs_while_slow_tick_blocks` |
| L6 | notify outbox | R4 完成后 `test_notify_outbox_only` |

E2E 脚本（`tests/e2e/test_live_pipeline_reconciler.py`，R2c-3 闸门）：mock is_live → prepare → STT → offline → finalize → notify drained。

---

## Self-review（spec coverage）

| Spec 章节 | Plan 任务 |
|-----------|-----------|
| I.0 硬约束 / reconciler flag | Task 2, 10, 13 |
| LP-01/02/03 | Task 5, 11, 13 |
| CP-01–03 | Task 12 Step 3–4 + Task 10 reconcile_content |
| RR-01..05 | Task 10 |
| RC-01..03 | Task 10 + Task 12 migration |
| LW-01..05 | Task 6, 11 |
| SR-01/02 SessionRuntime | Task 5b |
| ProbeExecutionGuard | Task 12 |
| obs_* + offline 双写 | Task 7, 9, 11 |
| cancel_pending | Task 8, 10 |
| 每线程 conn | Task 4 |
| Scheduler tick 顺序 | Task 3, 10 Step 5 |
| pipeline_phase | Task 14 |
| StateWriter 全量 | Task 15 |
| notify_events | Task 16 |
| R1 async finalize | Task 1+3（R1+R2a PR） |

**Gaps:** Epic 外 download/transcribe 拆分 — 故意不在本 plan。

---

## What already exists

| 已有 | Plan 复用 |
|------|-----------|
| `monitor_tasks` + dedupe partial UNIQUE | Task 8 `ensure_task` |
| `MonitorExecutor.submit` 每 worker `open_db` | R2a 沿用 |
| `observe_live_state` | R2c-3 接入 `run_once` |
| `desktop_events` + sidecar drain | R4 notify mirror |
| `pipeline_events` / `live stats` | Epic G1′ 验收 |
| `test_offline_wall_clock` | G3/G4 基础 |

---

## NOT in scope

| 项 | 理由 |
|----|------|
| download/transcribe 拆分 | Spec Epic 外 |
| asyncio 重写 | Spec 非目标 |
| Redis/Temporal | Spec 非目标 |
| Desktop Vitest 全量 | R3a optional |
| `reconciler_enabled=false` 长期共存 | ≤1 release 迁移窗 |
| reconcile_live 全表扫描优化 | 10+ 博主后再做（Perf P2） |

---

## Parallelization

| Step | Modules | Depends on |
|------|---------|------------|
| R1+R2a | `scheduler/`, `task_scheduler`, `session_runtime`, `watcher` | — |
| R2b | `monitor_executor`, `recording` | R1+R2a |
| R2c-1 | `db`, `task_reconciler`, `state_writer` | R2b |
| R2c-2 | `probe_guard`, `recording`, SlowTick | R2c-1 |
| R2c-3 | `platform/*/live` | R2c-2 |
| R3a/R3b/R4 | 相对独立 | R2c-3 |

**Lanes:** R1+R2a → R2b → R2c（顺序 3 PR）→ R3/R4 可并行。  
**Conflict:** R2b 与 R2c-2 都改 `recording.py` — 必须顺序合并。

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

---

## GSTACK REVIEW REPORT

| Review | Trigger | Runs | Status | Findings |
|--------|---------|------|--------|----------|
| Eng Review | `/plan-eng-review` | 2 | CLEAR (PLAN) | D1–D5 已写入 plan；Task 5b SessionRuntime；R1+R2a 捆绑；reconcile_content + due 列 |
| CEO Review | — | 0 | — | — |
| Design Review | — | 0 | — | — |
| Outside Voice | — | 0 | — | — |

- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED (PLAN) — 可开工 R1+R2a 捆绑 PR
