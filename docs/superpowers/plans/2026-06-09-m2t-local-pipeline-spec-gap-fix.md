# Local Pipeline Spec Gap Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps between [2026-06-08-m2t-local-pipeline-refactor-design.md](../specs/2026-06-08-m2t-local-pipeline-refactor-design.md) and current `main` code, without re-litigating already-shipped R1–R3a.

**Architecture:** Four small PRs, ordered by blast radius. Each PR is independently mergeable with tests green. Prefer moving side effects into existing abstractions (`TaskReconciler`, `StateWriter`, `NotifyEventRepo`) over new frameworks.

**Tech Stack:** Python 3.12+, threading, SQLite WAL, pytest, existing `MonitorScheduler` / `TaskSchedulerLoop` / `StateWriter`.

**Baseline (code audit 2026-06-09):** Daemon 主路径 Probe→Reconcile→Worker 已通；41 个闸门单测绿。Gap 在 Worker chain-enqueue、notify 未 outbox 化、SlowTick 共享 conn、Scheduler drain 顺序、死代码与非 daemon 旧路径。

**Spec refs:** I.0（Reconciler-only tasks）、I.2（tick 顺序）、I.3（probe_parallelism）、I.4/I.6（StateWriter + per-thread conn）、R4/L6（notify outbox）、附录 B（`outbox_only: true`）。

---

## PR 拆分（推荐顺序）

| PR | 主题 | 风险 | 阻塞 Client-Primary |
|----|------|------|---------------------|
| **GF-1** | Reconciler-only `monitor_tasks` + Scheduler 顺序 | 中 | 否 |
| **GF-2** | Notify outbox 闭环（含 CLI daemon drain） | 中 | 部分（L6） |
| **GF-3** | SlowTick 独立 conn + 死代码清理 | 低 | 否 |
| **GF-4** | StateWriter 收口 snapshot/events + probe_parallelism | 低 | 否（R3b 补完） |

---

## GF-1 — Reconciler-only tasks + Scheduler tick 顺序

### 问题（代码证据）

- `monitor_executor._run_sync_catalog` 在 Worker 内 `MonitorTaskRepo.enqueue(download)` — 违反 spec I.0。
- `TaskSchedulerLoop.tick_once` 顺序为 p0 → live → **content** → **post_process**；spec I.2 与 plan D4 均为 post_process **先于** content。

### Task 1: Reconciler ensure download（RC-04）

**Files:**
- Modify: `src/media2text/core/live/task_reconciler.py`
- Modify: `src/media2text/core/live/monitor_executor.py`
- Test: `tests/unit/test_task_reconciler.py`
- Test: `tests/unit/test_monitor_executor_sync.py`（新建，或扩展现有 worker 测试）

- [ ] **Step 1: Write failing test — sync 成功后 Reconciler ensure download**

```python
def test_reconcile_download_after_sync_catalog_success(tmp_path, monkeypatch):
    # creator 有 pending sync_catalog 刚 mark done 的语义：用 creators.sync_pending_download flag
    # 或：sync_catalog worker 只写 creators.last_sync_ok_at + sync_needs_download=1
    # Reconciler 读 flag → ensure_task(download:...)
    ...
    reconcile_content(cfg, conn)
    assert MonitorTaskRepo(conn).has_active_dedupe(f"download:{cid}")
```

**设计决策（锁）：** sync→download 链不能留在 Worker。两种等价实现，选 **A**（最小 schema）：

- **A（推荐）：** `sync_catalog` worker 成功时 `UPDATE creators SET sync_needs_download=1`（新列 INTEGER，默认 0）。`reconcile_content` 见 `sync_needs_download=1` → `ensure_task(download:...)` 并清 flag。无新 monitor_task 类型。
- **B：** Worker 写 `desktop_events` / 内部 event 表 — 过度设计，不采用。

- [ ] **Step 2: Migration `creators.sync_needs_download`**

`src/media2text/core/storage/db.py` 增加列；`CreatorRepo` 增 `mark_sync_needs_download(creator_id)` / `clear_sync_needs_download(creator_id)`。

- [ ] **Step 3: `_run_sync_catalog` 删 enqueue，改 mark flag**

```python
# monitor_executor.py — 删除 MonitorTaskRepo(conn).enqueue(download...)
if outcome.get("ok"):
    CreatorRepo(conn).mark_sync_needs_download(task.creator_id)
```

- [ ] **Step 4: `reconcile_content` 增 RC-04**

```python
if creator.sync_needs_download:
    if _maybe_ensure(tasks, ..., task_type="download", dedupe_key=f"download:{creator.id}", priority=10, ...):
        creators_repo.clear_sync_needs_download(creator.id)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_task_reconciler.py tests/unit/test_live_worker_tasks.py -v
```

- [ ] **Step 6: Guard — Worker 禁止 enqueue（reconciler_enabled 时）**

在 `MonitorTaskRepo.enqueue` 增加可选 strict 模式，或 Worker 路径统一改 `ensure_task` 且仅 Reconciler 调用 ensure。更简单：**删除 Worker 内唯一 enqueue 调用** 即可；API/agent 手动 enqueue 保留（用户意图）。

### Task 2: Scheduler drain 顺序对齐 spec + plan D4

**Files:**
- Modify: `src/media2text/core/live/task_scheduler.py`
- Modify: `tests/unit/test_task_scheduler.py`

- [ ] **Step 1: Write failing test**

```python
def test_scheduler_tick_order_post_process_before_content(tmp_path, monkeypatch):
    calls: list[str] = []
    # mock post_pool.drain_pending → append "post"
    # mock second drain_pending (p10+) → append "content"
    loop.tick_once(conn)
    assert calls.index("post") < calls.index("content")
```

- [ ] **Step 2: Reorder `tick_once`**

目标顺序（与 spec I.2 / plan D4 一致）：

```
reconcile_live → reconcile_content
→ claim p0 (finalize)
→ drain p1–9 (live workers)
→ post_process.drain_pending
→ drain p10+ (content)
```

- [ ] **Step 3: Run**

```bash
pytest tests/unit/test_task_scheduler.py -v
```

### Task 3: `reconciler_enabled=false` 行为文档化或删除

**Files:**
- Modify: `src/media2text/core/config.py`（注释 + 可选 deprecate）
- Modify: `config.example.yaml`
- Modify: `docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md` 附录 D（注明迁移窗口已结束）

**决策：** 默认已 `true`；代码中 **false 不再支持 live 自动建任务**。保留 flag 仅用于 `reconciler_log_only` shadow 联调；或移除 `reconciler_enabled` 布尔，只留 `reconciler_log_only`。最小改法：config 注释 + `load()` 时 `false` 打 warning log。

- [ ] **Step 1:** `reconciler_enabled=False` 时 log warning：`legacy probe enqueue removed; set true`
- [ ] **Step 2:** 删 issue 文档中「false 时 legacy poll」表述；更新 plan 主文档 Status 段

---

## GF-2 — Notify outbox 闭环（R4 补完）

### 问题（代码证据）

- 仅 `StateWriter.set_offline_since` → `notify_events`（`live_ended`）。
- `recording.py` / `monitor_executor.py` / `post_process.py` / `partial_notify.py` / `cloud/live_upload.py` 仍 `notify.emit`。
- `outbox_only` 默认 false；daemon 内 skip 不入队。
- Drain 仅在 `api/app.py` lifespan；纯 CLI daemon 不 delivery。

### Task 4: 统一 `NotifyService.emit` → outbox（daemon 路径）

**Files:**
- Modify: `src/media2text/core/notify/service.py`
- Modify: `src/media2text/core/notify/outbox.py`
- Test: `tests/unit/test_notify_outbox.py`

- [ ] **Step 1: Write failing test**

```python
def test_emit_in_daemon_enqueues_when_outbox_only(tmp_path, monkeypatch):
    cfg = AppConfig(..., notify=NotifyConfig(enabled=True, outbox_only=True))
    NotifyDaemonGuard.enter()
    conn = open_db(cfg)
    svc = NotifyService(cfg)
    svc.emit(NotifyEvent(kind=EventKind.RECORDING_COMPLETED, title="t", body="b"))
    assert NotifyEventRepo(conn).count_pending() == 1
```

- [ ] **Step 2: `emit` 在 `NotifyDaemonGuard.is_active()` 时走 enqueue**

```python
def emit(self, event: NotifyEvent) -> None:
    if not self._notify.enabled:
        return
    if self._notify.outbox_only and NotifyDaemonGuard.is_active():
        conn = open_db(self._cfg)  # 或要求 caller 传 conn — 优先 thread-local 当前 conn 不可行，用短连接 enqueue
        try:
            NotifyEventRepo(conn).enqueue(
                kind=event.kind.value,
                title=event.title,
                body=event.body,
                creator_id=event.creator_id,
                session_id=event.session_id,
                dedupe_key=event.dedupe_key,
            )
        finally:
            conn.close()
        return
    ...  # 现有 sync 路径（CLI 非 daemon / tests）
```

扩展 `NotifyEvent` dataclass：可选 `creator_id`, `session_id`, `dedupe_key`（已有则跳过）。

- [ ] **Step 3: 默认 `outbox_only: true` in `config.py` + `config.example.yaml`**

CLI 非 daemon 单次命令仍可 sync emit（Guard 未 active）。

### Task 5: CLI daemon 内嵌 notify drain loop

**Files:**
- Modify: `src/media2text/core/live/scheduler.py` 或 `src/media2text/core/notify/outbox.py`
- Modify: `src/media2text/core/monitor/watcher.py`
- Test: `tests/unit/test_notify_daemon_drain.py`（新建）

**设计：** 复用 `notify_event_drain.drain_once(cfg)`，在 `MonitorScheduler.start()` 起第四条 daemon 线程（或合入 TaskScheduler tick 末尾）。推荐 **Scheduler tick 末 drain_once(limit=20)** — 少一线程，1s 粒度足够。

- [ ] **Step 1: Failing test** — enqueue notify_event，`TaskSchedulerLoop.tick_once` 后 `delivered_at` 非空（mock `NotifyService.emit` 在 drain 内被调）。

- [ ] **Step 2: `TaskSchedulerLoop.tick_once` 末尾**

```python
from media2text.api.services.notify_event_drain import drain_once
drain_once(self._cfg, limit=20)
```

注意：`drain_once` 不应依赖 FastAPI；若 import 路径耦合，将 drain 逻辑下沉到 `core/notify/drain.py`，API 与 daemon 共用。

- [ ] **Step 3: 迁移 kind 冒烟清单**

优先覆盖 daemon 热路径（不必一次改 call site）：

| kind | 当前 emit 位置 |
|------|----------------|
| live_ended | StateWriter（已 outbox）→ 可改统一 emit |
| recording_completed | recording finalize |
| live_started / live_start_failed | recording start |
| new_aweme / new_archive / new_dynamic | monitor_executor |
| transcribe_completed | post_process / monitor_executor |
| transcribe_partial | partial_notify |

GF-2 完成标准：`outbox_only=true` + daemon 下上述 kind 均能在 `notify_events` 见到且 drain 交付；`test_notify_outbox_only` 扩展为多 kind。

### Task 6: StateWriter live_ended 改经 NotifyService.emit

**Files:**
- Modify: `src/media2text/core/live/state_writer.py`

避免双路径：删 `_enqueue_notify_outbox` 直接 SQL，改 `self._notify.emit(...)`（daemon 下 Task 4 自动入 outbox）。保留 `BEGIN IMMEDIATE` 事务内 desktop_events + session 更新；notify 可在 commit 后 emit（最终一致可接受）或同事务 enqueue helper。

---

## GF-3 — 连接模型 + 死代码

### Task 7: SlowTick 使用独立 `open_db()`

**Files:**
- Modify: `src/media2text/core/live/scheduler.py`（`SlowTickLoop._run`）
- Modify: `src/media2text/core/monitor/watcher.py`
- Test: `tests/unit/test_task_scheduler.py`（扩展现有 conn 测试）

- [ ] **Step 1: 将 `_run_vod_tick` / `_run_archive_tick` / `_run_dynamic_tick` 改为接受 `conn` 参数**

```python
# scheduler.py SlowTickLoop._run
conn = open_db(self._cfg)
try:
    self._watcher._run_vod_tick(conn=conn, creator_id=...)
    ...
finally:
    conn.close()
```

- [ ] **Step 2: `MonitorWatcher.__init__` 保留 `_conn` 仅只读/CLI `run_once` 兼容，或标记 deprecated**

Daemon 路径不再经 `self._creators` 写 due；SlowTick 用传入 conn 的 `CreatorRepo(conn)`。

- [ ] **Step 3: 跑 `test_conn_per_thread_no_shared_watcher_conn` + 新增 SlowTick 写 due 不触 watcher._conn**

### Task 8: 删除无调用方 legacy 代码

**Files:**
- Modify: `src/media2text/core/live/recording.py`
- Modify: `src/media2text/core/live/monitor_executor.py`
- Modify: `tests/` — 保留 `scan_and_start` 单测则移到 `tests/unit/test_legacy_scan_and_start.py` 或删测试若行为已废弃

删除（grep 确认零调用后）：

- `scan_and_start`
- `_handle_ffmpeg_exit`
- `_enqueue_finalize`
- `MonitorExecutor.drain_priority_zero`（inline sync drain）

- [ ] **Step 1:** `rg 'scan_and_start|_handle_ffmpeg_exit|drain_priority_zero' src/` 为空
- [ ] **Step 2:** `pytest tests/unit/ -v -k live` 全绿

### Task 9: 非 daemon `run_once` 路径对齐（可选，YAGNI 边界）

**Files:**
- Modify: `src/media2text/core/monitor/watcher.py`

`monitor watch`（无 `--daemon`）仍 `_drain_monitor_tasks_sync` on shared conn。选项：

- **A（推荐）：** 文档标注 debug-only；实现改为 spawn 单轮 TaskScheduler tick + probe（与 daemon 同语义）。
- **B：** 保持现状，README 说明单次模式不保证 Execution Engine 语义。

若选 A：`_run_daemon_locked` 抽 `run_scheduler_round()` 供 `run_once` 调用一次。

---

## GF-4 — StateWriter 补完 + 配置接线

### Task 10: StateWriter 收口 snapshot + pipeline_events

**Files:**
- Modify: `src/media2text/core/live/state_writer.py`
- Modify: `src/media2text/core/live/recording.py`
- Modify: `scripts/check_no_direct_live_repo.py`
- Test: `tests/unit/test_state_writer.py`

- [ ] **Step 1: 增 `StateWriter.update_snapshot(creator_id, live_info)`** — 包装 `upsert_live_snapshot` + `enqueue_creator_updated`
- [ ] **Step 2: 增 `StateWriter.record_pipeline_event(...)`** — 包装 `record_event`
- [ ] **Step 3: `probe_live` / `observe_live_state` / `poll_active_session` 改调 state writer**
- [ ] **Step 4: 扩展 CI grep** — 禁止 guarded 文件内 direct `upsert_live_snapshot` / `record_event` / `enqueue_creator_updated`

### Task 11: `probe_parallelism` 接线

**Files:**
- Modify: `src/media2text/core/live/recording.py`（`probe_live`）
- Modify: `src/media2text/core/live/probe.py`（可选 helper）
- Test: `tests/unit/test_task_scheduler.py` 或新建

```python
def _probe_workers(cfg: AppConfig, n_targets: int) -> int:
    n = cfg.monitor.probe_parallelism or cfg.live.scan_concurrency
    return min(max(1, n), n_targets)
```

`config.example.yaml` 注释：`probe_parallelism` 优先于 `live.scan_concurrency`。

### Task 12: Probe guard strict 模式（dev only）

**Files:**
- Modify: `src/media2text/core/live/probe.py`
- Modify: `src/media2text/core/config.py` — `monitor.probe_guard_strict: bool = False`

```python
ProbeExecutionGuard.exit_probe_tick(
    strict=cfg.monitor.probe_guard_strict,
)
```

默认 false（prod log）；dev `config.yaml` 可 true。

---

## 验收与文档

### Task 13: 更新 Epic 验收表 + 主 plan Status

**Files:**
- Modify: `docs/superpowers/verification/2026-06-09-m2t-local-pipeline-refactor-acceptance.md`
- Modify: `docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md`（Status →「主干已交付，GF-1..4 补 gap」）

### 全量验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_probe_guard.py tests/unit/test_poll_active_obs.py \
  tests/unit/test_task_reconciler.py tests/unit/test_task_scheduler.py \
  tests/unit/test_live_worker_tasks.py tests/unit/test_pipeline_phase.py \
  tests/unit/test_notify_outbox.py tests/e2e/test_live_pipeline_reconciler.py -v
python scripts/check_no_direct_live_repo.py
ruff check src/media2text/core/live/ src/media2text/core/notify/
```

可选 Epic：

```bash
python scripts/epic_verify.py local-pipeline-refactor
```

---

## Self-Review（plan vs spec）

| Spec 条款 | 覆盖 Task |
|-----------|-----------|
| I.0 Reconciler-only monitor_tasks | GF-1 Task 1, 3 |
| I.2 tick 顺序 post_process before content | GF-1 Task 2 |
| I.3 probe_parallelism | GF-4 Task 11 |
| I.4 StateWriter 单写口 | GF-2 Task 6, GF-4 Task 10 |
| I.6 每线程 open_db | GF-3 Task 7 |
| R4 / L6 notify outbox | GF-2 Task 4–6 |
| 附录 B outbox_only default true | GF-2 Task 4 |
| G1′ 开录 P95 | **未纳入**（需生产 pipeline_events；单独 issue） |

**刻意不做（YAGNI）：**

- G1′ 自动化基准（需 live 环境或长时间 mock）
- Desktop Vitest pipeline_phase UI
- 删除 `reconciler_enabled` 字段（仅 warning）
- API/agent 手动 enqueue 改 Reconciler（用户操作，spec 硬约束针对 daemon 自动路径）

---

## Eng Review 增补（2026-06-09 `/plan-eng-review`）

### Decisions to confirm

| ID | 问题 | 推荐 |
|----|------|------|
| **1A** | `NotifyService.emit` 入 outbox 后，`drain_once` 不能再调 `emit`（会重入 outbox）。需 `deliver()` 或 `emit(..., force_sync=True)` | **1A** ✅ 已确认：拆 `enqueue()` + `deliver()`；drain 只调 `deliver` |
| **2A** | `PostProcessExecutor` worker 未 `NotifyDaemonGuard.enter()`，`outbox_only=true` 时 post_process 通知会走 sync 旁路 | **2A** 与 `MonitorExecutor.submit` 对称，worker 入口 `Guard.enter()` |
| **3A** | `sync_needs_download=1` 但 download dedupe 已存在时，RC-04 应清 flag 避免永久重试 | **3A** `has_active_dedupe` 时也 `clear_sync_needs_download` |
| **4B** | Task 9 `run_once` 对齐 daemon 语义 | **4B** 保持 debug-only 文档（YAGNI），不抽 `run_scheduler_round` |

### GF-2 Task 4b（新增，阻塞 Task 5）

**Files:** `core/notify/service.py`, `core/notify/drain.py`（从 api 下沉）, `tests/unit/test_notify_outbox.py`

- [ ] **Step 1:** 新增 `NotifyService.deliver(event)` — 仅 sound/feishu，永不写 outbox
- [ ] **Step 2:** `emit()` — daemon+outbox_only → `NotifyEventRepo.enqueue`；否则 `deliver()`
- [ ] **Step 3:** `drain_once` 改调 `deliver()`，禁止经 `emit()`
- [ ] **Step 4:** 更新 `test_notify_drain_emits_pending` mock `deliver` 而非 `emit`
- [ ] **Step 5:** 新增 `test_emit_in_daemon_enqueues_when_outbox_only`（Task 4 Step 1）

### GF-1 Task 1 增补（RC-04 edge）

- [ ] **Step 4b:** 若 `sync_needs_download` 且 `has_active_dedupe(f"download:{id}")`，仍 `clear_sync_needs_download`（download 已在途）

### GF-2 Task 5 增补

- [ ] **PostProcessExecutor.submit:** worker 内 `NotifyDaemonGuard.enter()`（与 monitor worker 一致）

### 测试缺口（plan 须覆盖）

| 测试 | 文件 | 断言 |
|------|------|------|
| drain 不 re-enqueue | `test_notify_outbox.py` | outbox_only + pending row → deliver 一次，pending=0，无二次 INSERT |
| post_process outbox | `test_notify_outbox.py` | Guard + outbox_only + post_process emit → pending+1 |
| RC-04 dedupe 已存在 | `test_task_reconciler.py` | flag=1 + active download → reconcile 后 flag=0 |
| scheduler tick 顺序 | `test_task_scheduler.py` | post 在 content 前（Task 2 已有） |
| TaskScheduler drain 集成 | `test_notify_daemon_drain.py` | tick_once 末 → mark_done |

---

## 执行选项

Plan 已保存至 `docs/superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md`。

1. **Subagent-Driven（推荐）** — 按 GF-1 → GF-2 → GF-3 → GF-4 分 PR，每 PR 一个 subagent + review
2. **Inline Execution** — 本会话按 Task 顺序直接改代码，每 PR 边界 checkpoint

---

## Eng Review 增补 — GF-5 / #266（2026-06-09）

针对 Issue [#266](https://github.com/oychao1988/media2text/issues/266) 与 main 上未提交 WIP diff。

### Step 0 — Scope Challenge

| 项 | 结论 |
|----|------|
| 已有能力 | `NotifyService.emit` + outbox、`TaskReconciler` finalize、`start_streaming_stt`/`reconnect_streaming_stt`、`_mark_streaming_degraded` 均已存在 |
| 最小改动 | Task 1 重排 emit 顺序；Task 2 改 STT fail 分支；Task 3 增 stall 计数 — **不** 拆 LW-01 为双 task |
| 复杂度 | 4 文件、0 新类 — 通过 smell 检查 |
| 完整性 | 缺 Task 2 + 2 条单测时不能关单；Task 4 文档可同 PR |

### 已确认决策

| ID | 选择 | 说明 |
|----|------|------|
| **D1** | **1A** | STT 失败 → `_mark_streaming_degraded`，保持 `recording`，不 stop ffmpeg，不发 `LIVE_START_FAILED` |
| **D2** | **2A** | `offline_flv_stall_polls=3`（默认），与 Issue 一致 |

### WIP 与 Spec 对齐度

| Task | WIP 状态 | 缺口 |
|------|----------|------|
| Task 1 | ✅ grace 后 emit `LIVE_STARTED` + `recording\|started`，再 `stt.start()` | ❌ 缺 `test_live_started_emitted_before_streaming_stt_blocks` |
| Task 2 | ❌ 仍 `stop_process` + `status=failed` + `LIVE_START_FAILED` | 按 **D1** 重写 `stt_failed` 分支 |
| Task 3 | ✅ `_flv_stall_polls` + config + `test_profile_offline_after_flv_stall_ignores_reflow` | — |
| Task 4 | ❌ 未做 | config 注释 + 验收表 GF-5 行 |

### 数据流（目标态，Task 1+2 完成后）

```
start_recording worker
  → spawn ffmpeg
  → grace OK?
       no → failed + LIVE_START_FAILED
       yes → pipeline recording|started + LIVE_STARTED (outbox)
            → stt.start() [async-ish, 可慢/可 fail]
                 fail → degraded (recording 继续, Reconciler 重试 STT)
                 ok  → streaming_stt|started

LiveTick poll (offline_trust_recording_signals)
  → profile offline?
       → FLV 增长? reset stall
       → FLV 不增长? stall++
       → stall >= N → obs_still_live=0 → offline_since → finalize
```

### GF-5 测试缺口（implementer checklist）

| 测试 | 文件 | 优先级 |
|------|------|--------|
| `test_live_started_emitted_before_streaming_stt_blocks` | `test_live_recording_core.py` | P0 CRITICAL |
| ffmpeg 已录 + STT fail → status=recording | `test_live_recording_core.py` | P0 CRITICAL |
| `test_profile_offline_after_flv_stall_ignores_reflow` | `test_offline_recording_signals.py` | ✅ 已有 |

### NOT in scope（GF-5）

- LW-01 拆成 ffmpeg/STT 双 task（后续 Issue）
- `offline_confirm_sec` 默认值调整
- B 站 reflow 语义重写
- 历史 stuck `monitor_tasks` 自动清理（运维 recover-stale）

### What already exists

- Outbox / R4：`NotifyService.emit` 已 daemon-safe
- STT 重连：`reconnect_streaming_stt` task + `_handle_stt_disconnect`
- Degraded 路径：`_mark_streaming_degraded` + `_streaming_legacy_finalize`
- GF-3 probe 并行：`78e8736` 已合（每线程 `open_db`）

### Failure modes（GF-5 相关）

| 场景 | 测试 | 处理 | 用户可见 |
|------|------|------|----------|
| STT 阻塞开录 | GAP | Task 1 已修 emit 顺序 | 飞书及时 |
| STT fail 杀录制 | GAP | Task 2 / D1 | 曾：开播后又失败 |
| reflow+僵尸 ffmpeg | ★★★ 单测 | Task 3 stall | Desktop 卡住 |
| daemon 重启丢 stall 计数 | 无 | 下轮 poll 重计 | 可能多等 N poll |

### 并行化

Sequential — 全在 `core/live/recording.py` + 测试 + config，单 PR `issue-266-local-pipeline-gap-fix-gf5`。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | issues_open (GF-1–4) / **GF-5 pending impl** | GF-1–4: 8 issues; GF-5: 2 P0 test gaps + Task 2 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **UNRESOLVED:** GF-1–4 表内 4 项（GF-2 notify deliver）仍 open；GF-5 D1/D2 已确认，待 implement
- **VERDICT:** GF-5 方案 **可实施** — 在 `issue-266-*` 分支补 Task 2 + 2 条单测 + Task 4 文档后跑 issue 验证命令
