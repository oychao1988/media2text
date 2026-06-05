# Monitor Daemon v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1 修复 Desktop 左侧栏与 daemon 状态脱节（outbox 跨进程 WS + 观测/开录拆分 + 探测失败不冻结 snapshot）；Phase 2 将重任务迁入 `monitor_tasks` 队列且 finalize 单入口。

**Architecture:** daemon 子进程只写 SQLite（snapshot / session / `desktop_events`）；API sidecar `StateEventDrain` 协程 drain outbox → `events_hub` → WS。`LiveRecordingCore` 拆 `observe_live_state`（O3 可单测）与 `maybe_start_recording`（快速通道保留 G1）。

**Tech Stack:** Python 3.12+, FastAPI lifespan + asyncio, SQLite WAL, threading（v2 调度不变）, pytest, Vitest（Desktop 可选）。

**Spec:** [2026-06-05-monitor-daemon-observe-execute-design.md](../specs/2026-06-05-monitor-daemon-observe-execute-design.md)（eng review 2026-06-05）

**Status:** Phase 1 待实施；Phase 2 待 Phase 1 验收后开工。

---

## File map

### Phase 1

| File | Responsibility |
|------|----------------|
| `src/media2text/core/storage/db.py` | `_migrate_desktop_v2`: `desktop_events` 表 + `creator_live_snapshots.probe_error` |
| `src/media2text/core/storage/models.py` | `DesktopEventRow`, `CreatorLiveSnapshotRow.probe_error` |
| `src/media2text/core/storage/repos.py` | `DesktopEventRepo`（enqueue / claim_pending / mark_delivered） |
| `src/media2text/core/live/snapshot.py` | `upsert_live_snapshot` 返回 changed；`touch_snapshot_probe` 探测失败 |
| `src/media2text/core/desktop/state_events.py` | `enqueue_creator_updated(conn, creator_id)` — core 层 outbox 写入 |
| `src/media2text/core/live/recording.py` | `observe_live_state` / `maybe_start_recording`；poll_active 变更写 outbox |
| `src/media2text/api/services/state_event_drain.py` | `drain_once` + `run_drain_loop`（1–2s） |
| `src/media2text/api/app.py` | FastAPI `lifespan` 启动/停止 drain 协程 |
| `tests/unit/test_desktop_db_migration.py` | v2 表/列迁移 |
| `tests/unit/test_desktop_event_repo.py` | outbox CRUD + drain |
| `tests/unit/test_live_observe_state.py` | O3：observe 不写 ffmpeg |
| `tests/unit/test_snapshot_probe_failure.py` | 探测失败更新 `checked_at` |
| `tests/unit/test_api_state_event_drain.py` | drain → `events_hub` → WS |

### Phase 2（纲要，详见文末）

| File | Responsibility |
|------|----------------|
| `src/media2text/core/storage/db.py` | `monitor_tasks` 表 + dedupe 部分 UNIQUE |
| `src/media2text/core/storage/repos.py` | `MonitorTaskRepo` |
| `src/media2text/core/live/monitor_executor.py` | 有界 ThreadPoolExecutor |
| `src/media2text/core/live/scheduler.py` | ContentObserve enqueue；LiveObserve finalize drain |
| `src/media2text/core/config.py` | `monitor.executor_max_parallel` |
| `src/media2text/cli/live.py` | `live status --json` 展示 monitor_tasks |

---

# Phase 1 — 状态贡献 + 观测拆分

验收：O1、O2、O3、O6（见 spec §2）；手动：daemon 跑一轮后 Desktop ≤3s 灯变。

---

### Task 1: DB 迁移 `desktop_events` + `probe_error`

**Files:**
- Modify: `src/media2text/core/storage/db.py`
- Modify: `src/media2text/core/storage/models.py`
- Test: `tests/unit/test_desktop_db_migration.py`

- [ ] **Step 1: Write failing test**

```python
def test_desktop_v2_tables_and_probe_error(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "desktop_events" in tables
    cols = {
        r[1]
        for r in conn.execute("PRAGMA table_info(creator_live_snapshots)").fetchall()
    }
    assert "probe_error" in cols
    conn.close()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/unit/test_desktop_db_migration.py::test_desktop_v2_tables_and_probe_error -v`

- [ ] **Step 3: Add `_migrate_desktop_v2` in `db.py`**

在 `_migrate_desktop_v1` 之后新增，并在 `connect()` 中调用：

```python
def _migrate_desktop_v2(conn: sqlite3.Connection) -> None:
    snap_cols = {row[1] for row in conn.execute("PRAGMA table_info(creator_live_snapshots)").fetchall()}
    if "probe_error" not in snap_cols:
        conn.execute(
            "ALTER TABLE creator_live_snapshots ADD COLUMN probe_error TEXT"
        )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS desktop_events (
          id TEXT PRIMARY KEY,
          event_type TEXT NOT NULL,
          creator_id TEXT,
          payload_json TEXT,
          created_at TEXT NOT NULL,
          delivered_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_desktop_events_pending
          ON desktop_events(delivered_at, created_at)
          WHERE delivered_at IS NULL;
        """
    )
    conn.commit()
```

`connect()` 内追加：`_migrate_desktop_v2(conn)`

- [ ] **Step 4: Extend `CreatorLiveSnapshotRow`**

```python
@dataclass
class CreatorLiveSnapshotRow:
    creator_id: str
    is_live: int
    room_id: str | None
    title: str | None
    checked_at: str
    probe_error: str | None = None
```

- [ ] **Step 5: Run test — expect PASS**

Run: `pytest tests/unit/test_desktop_db_migration.py -v`

- [ ] **Step 6: Commit**（用户要求时）

```bash
git add src/media2text/core/storage/db.py src/media2text/core/storage/models.py tests/unit/test_desktop_db_migration.py
git commit -m "feat(desktop): migrate desktop_events outbox and snapshot probe_error"
```

---

### Task 2: `DesktopEventRepo`

**Files:**
- Modify: `src/media2text/core/storage/repos.py`
- Create: `tests/unit/test_desktop_event_repo.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from media2text.core.storage.db import connect
from media2text.core.storage.repos import DesktopEventRepo


def test_enqueue_and_claim_pending(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    repo = DesktopEventRepo(conn)
    eid = repo.enqueue_creator_updated("creator-1")
    pending = repo.claim_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].id == eid
    assert pending[0].creator_id == "creator-1"
    assert pending[0].event_type == "creator.updated"
    conn.close()


def test_mark_delivered_excludes_from_claim(tmp_path) -> None:
    conn = connect(tmp_path / "media2text.db")
    repo = DesktopEventRepo(conn)
    eid = repo.enqueue_creator_updated("creator-1")
    repo.mark_delivered(eid)
    assert repo.claim_pending(limit=10) == []
    conn.close()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_desktop_event_repo.py -v`

- [ ] **Step 3: Implement `DesktopEventRow` + `DesktopEventRepo`**

`models.py` 增加：

```python
@dataclass
class DesktopEventRow:
    id: str
    event_type: str
    creator_id: str | None
    payload_json: str | None
    created_at: str
    delivered_at: str | None
```

`repos.py` 增加（对齐 `PostProcessJobRepo.claim_pending` 原子语义）：

```python
class DesktopEventRepo:
    def enqueue_creator_updated(self, creator_id: str, *, payload: dict | None = None) -> str:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload) if payload else None
        self._conn.execute(
            """
            INSERT INTO desktop_events (id, event_type, creator_id, payload_json, created_at)
            VALUES (?, 'creator.updated', ?, ?, ?)
            """,
            (event_id, creator_id, payload_json, now),
        )
        self._conn.commit()
        return event_id

    def claim_pending(self, *, limit: int = 50) -> list[DesktopEventRow]:
        rows = self._conn.execute(
            """
            SELECT id FROM desktop_events
            WHERE delivered_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[DesktopEventRow] = []
        for row in rows:
            full = self.get(row["id"])
            if full:
                out.append(full)
        return out

    def mark_delivered(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE desktop_events SET delivered_at = ? WHERE id = ?",
            (now, event_id),
        )
        self._conn.commit()

    def get(self, event_id: str) -> DesktopEventRow | None:
        ...
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

---

### Task 3: `state_events` + snapshot 变更检测

**Files:**
- Create: `src/media2text/core/desktop/state_events.py`
- Modify: `src/media2text/core/live/snapshot.py`
- Modify: `src/media2text/core/storage/repos.py`（`LiveSnapshotRepo.upsert` 返回 `bool`）
- Create: `tests/unit/test_snapshot_probe_failure.py`

- [ ] **Step 1: Write failing test — probe failure touches `checked_at`**

```python
from media2text.core.live.snapshot import touch_snapshot_probe_failed, upsert_live_snapshot
from media2text.core.platform.douyin.models import LiveRoomInfo
from media2text.core.storage.repos import LiveSnapshotRepo


def test_touch_probe_failed_updates_checked_at_only(tmp_path, monkeypatch) -> None:
    # setup creator + initial snapshot is_live=1
    ...
    touch_snapshot_probe_failed(conn, cid, error="timeout")
    snap = LiveSnapshotRepo(conn).get(cid)
    assert snap.is_live == 1  # unchanged
    assert snap.probe_error == "timeout"
    assert snap.checked_at > old_checked_at


def test_upsert_returns_false_when_unchanged(tmp_path) -> None:
    live = LiveRoomInfo(room_id="r1", is_live=True, stream_flv_url="http://x/a.flv")
    upsert_live_snapshot(conn, cid, live)
    changed = upsert_live_snapshot(conn, cid, live)
    assert changed is False
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement snapshot + state_events**

`LiveSnapshotRepo.upsert`：先 `get`，比较 `is_live/room_id/title`，仅变更时 UPDATE；返回 `changed: bool`；成功 upsert 时 `probe_error=NULL`。

`upsert_live_snapshot`：

```python
def upsert_live_snapshot(conn, creator_id: str, live_info: LiveRoomInfo | None) -> bool:
    if live_info is None:
        return False
    return LiveSnapshotRepo(conn).upsert(
        creator_id,
        is_live=bool(live_info.is_live),
        room_id=live_info.room_id,
        title=live_info.title,
    )


def touch_snapshot_probe_failed(conn, creator_id: str, *, error: str) -> bool:
    return LiveSnapshotRepo(conn).touch_probe(creator_id, probe_error=error)
```

`state_events.py`：

```python
def enqueue_creator_updated(conn, creator_id: str) -> str | None:
    return DesktopEventRepo(conn).enqueue_creator_updated(creator_id)
```

- [ ] **Step 4: Run — expect PASS**

---

### Task 4: 拆分 `observe_live_state` / `maybe_start_recording`

**Files:**
- Modify: `src/media2text/core/live/recording.py`
- Create: `tests/unit/test_live_observe_state.py`
- Modify: `tests/unit/test_live_snapshot_upsert.py`（适配 `upsert` 返回值）

- [ ] **Step 1: Write failing O3 test**

```python
def test_observe_live_state_does_not_start_recording(tmp_path, monkeypatch) -> None:
    # setup core with auto_record=True, live adapter returns is_live
    with patch.object(core, "_start_recording") as mock_start:
        with patch.object(core, "maybe_start_recording") as mock_maybe:
            info, err = core.observe_live_state(creator)
    mock_start.assert_not_called()
    mock_maybe.assert_not_called()
    assert info is not None and info.is_live
    assert DesktopEventRepo(conn).claim_pending(limit=5)  # outbox row exists


def test_scan_and_start_calls_maybe_start_recording_when_auto_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(..., effective_auto_record, lambda *a, **k: True)
    with patch.object(core, "maybe_start_recording", return_value={"session_id": "s1"}) as mock_maybe:
        core.scan_and_start()
    mock_maybe.assert_called_once()
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Refactor `recording.py`**

提取方法（保持 `scan_and_start` 对外签名不变）：

```python
def observe_live_state(self, creator) -> tuple[LiveRoomInfo | None, dict | None]:
    """Fetch live, upsert snapshot, enqueue outbox on change or probe touch."""
    live_info, err = self._fetch_live_info(creator)
    if err is not None:
        kind, payload = err
        touch_snapshot_probe_failed(self._conn, creator.id, error=str(payload.get("error", kind)))
        enqueue_creator_updated(self._conn, creator.id)
        return None, payload
    if live_info is not None:
        if upsert_live_snapshot(self._conn, creator.id, live_info):
            enqueue_creator_updated(self._conn, creator.id)
    return live_info, None


def maybe_start_recording(self, creator, live_info: LiveRoomInfo) -> dict:
    return self._start_recording(
        creator.id, creator.sec_uid, live_info.room_id, live_info
    )
```

`scan_and_start` 循环改为：

```python
live_info, err_payload = self.observe_live_state(creator)
if err_payload is not None:
    ...  # 现有 errors 聚合逻辑
    continue
if live_info is None or not live_info.is_live or not live_info.room_id:
    continue
if not effective_auto_record(creator, self._cfg):
    continue
meta = self.maybe_start_recording(creator, live_info)
```

`poll_active_recordings` 内在 `set_offline_since` / `clear_offline_since` / `_finalize_recording` 成功后对对应 `creator_id` 调用 `enqueue_creator_updated`。

- [ ] **Step 4: Run live tests**

Run: `pytest tests/unit/test_live_observe_state.py tests/unit/test_live_snapshot_upsert.py tests/unit/test_live_recording_auto_record.py -v`

- [ ] **Step 5: Commit**

---

### Task 5: API `StateEventDrain` + lifespan

**Files:**
- Create: `src/media2text/api/services/state_event_drain.py`
- Modify: `src/media2text/api/app.py`
- Create: `tests/unit/test_api_state_event_drain.py`

- [ ] **Step 1: Write failing integration test**

```python
def test_drain_publishes_creator_updated_to_ws(api_client, workspace, monkeypatch) -> None:
    cfg = AppConfig.load()
    conn = open_db(cfg)
    DesktopEventRepo(conn).enqueue_creator_updated("creator-x")
    conn.close()

    monkeypatch.setattr("media2text.api.routes.events._PING_INTERVAL_SEC", 5.0)
    monkeypatch.setattr(
        "media2text.api.services.state_event_drain._DRAIN_INTERVAL_SEC",
        0.15,
    )

    # 需 app lifespan 启动 drain；TestClient 进入 context 后触发
    with api_client.websocket_connect("/api/events") as ws:
        deadline = time.time() + 3.0
        found = False
        while time.time() < deadline:
            msg = json.loads(ws.receive_text())
            if msg.get("type") == "creator.updated" and msg.get("creator_id") == "creator-x":
                found = True
                break
        assert found

    conn2 = open_db(cfg)
    pending = DesktopEventRepo(conn2).claim_pending(limit=10)
    assert pending == []  # delivered
    conn2.close()
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement drain**

`state_event_drain.py`：

```python
_DRAIN_INTERVAL_SEC = 1.5

def drain_once(cfg: AppConfig) -> int:
    conn = open_db(cfg)
    try:
        repo = DesktopEventRepo(conn)
        n = 0
        for row in repo.claim_pending(limit=50):
            events_hub.publish(
                event_payload(EventType.CREATOR_UPDATED, creator_id=row.creator_id)
            )
            repo.mark_delivered(row.id)
            n += 1
        return n
    finally:
        conn.close()


async def run_drain_loop(cfg: AppConfig, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            drain_once(cfg)
        except Exception:
            log.exception("desktop_event_drain_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=_DRAIN_INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass
```

`app.py` — 在 **内层** `api = FastAPI()` 上挂 lifespan：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = AppConfig.load()
    stop = asyncio.Event()
    task = asyncio.create_task(run_drain_loop(cfg, stop))
    yield
    stop.set()
    await task

def create_app() -> FastAPI:
    app = FastAPI(title="media2text-desktop-api", version="0.1.0")
    ...
    api = FastAPI(lifespan=lifespan)
    ...
```

注意：`AppConfig.load()` 在 lifespan 内读当前 `MEDIA2TEXT_CONFIG`；与 `get_cfg` override 测试兼容——测试可先 `enqueue` 再手动 `drain_once(cfg)` 测 WS（lifespan 与 TestClient 并用时以集成测为准）。

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/unit/test_api_state_event_drain.py tests/unit/test_api_events_ws.py -v -m desktop`

- [ ] **Step 5: Commit**

---

### Task 6: 全量回归 + 手动验收

- [ ] **Step 1: 单元/桌面标记测试**

```bash
source .venv/bin/activate
pytest tests/unit/test_desktop_db_migration.py \
  tests/unit/test_desktop_event_repo.py \
  tests/unit/test_snapshot_probe_failure.py \
  tests/unit/test_live_observe_state.py \
  tests/unit/test_api_state_event_drain.py \
  tests/unit/test_process_lock.py \
  tests/unit/test_api_daemon.py \
  -v -m desktop
```

- [ ] **Step 2: 静态检查**

```bash
ruff check src/media2text/core/desktop src/media2text/core/live/snapshot.py \
  src/media2text/api/services/state_event_drain.py tests/unit/test_desktop_event_repo.py
pyright src/media2text/core/desktop/state_events.py src/media2text/api/services/state_event_drain.py
```

- [ ] **Step 3: 手动验收（O1/O2）**

```bash
source .venv/bin/activate
media2text doctor --json
# 终端 A
media2text serve --port 8765
# 终端 B
media2text monitor watch --daemon
# 终端 C：观察在播博主
media2text creator list --json
# Desktop：pnpm --filter m2t-desktop tauri dev
# 预期：开播后 ≤3s 左侧灯变化；daemon 日志含 snapshot_upserted / desktop_event_enqueued
```

- [ ] **Step 4: 更新 spec 状态（可选）**

Phase 1 完成后将 spec 顶部状态改为「Phase 1 已交付」，并追加 verification 文档路径（若需要）。

---

## Phase 1 spec 覆盖自检

| Spec 条款 | Task |
|-----------|------|
| §6.2 desktop_events | Task 1–2 |
| §6.1 probe_error | Task 3 |
| §7.1 outbox + drain | Task 2, 5 |
| §7.1 observe / maybe_start | Task 4 |
| §8 P1.1–P1.6 | Task 4–6 |
| O3 观测无副作用 | Task 4 |
| O6 stale lock | 已有测试，Task 6 回归 |

---

# Phase 2 — 统一任务队列（纲要）

**前置：** Phase 1 已合并且手动验收通过。单独开 2–3 个 PR，不要与 Phase 1 混发。

### Task P2-1: `monitor_tasks` 迁移 + `MonitorTaskRepo`

- 迁移 SQL 见 spec §6.3（含 `idx_monitor_tasks_dedupe_active`）
- Repo：`enqueue(task_type, dedupe_key, priority)` / `claim_pending` / `reset_stale_running` / `mark_done` / `mark_failed`
- 测试：`tests/unit/test_monitor_task_repo.py`（参照 `tests/unit/test_post_process_repo.py`）

### Task P2-2: `MonitorExecutor`

- 新文件 `monitor_executor.py`，镜像 `PostProcessExecutor`：worker 内 `open_db()`，禁止共享 LiveTick conn（D1）
- 配置 `monitor.executor_max_parallel` 默认 **1**；`config.example.yaml` 注释 Playwright 内存风险
- Playwright 类 job 使用模块级 `threading.Semaphore(1)`

### Task P2-3: ContentObserve 只 enqueue

- `MonitorWatcher._run_pipeline_tick` 改为：检测新内容 → `enqueue(sync_catalog|download|…)`，不内联 `run_pipeline`
- SlowTick 保持间隔，仅缩短单次 tick 阻塞时间（G5）

### Task P2-4: finalize 单入口

- `poll_active_recordings`：删除直接 `_finalize_recording` 调用；offline 满足 `offline_confirm_sec` 后 `enqueue(finalize:{session_id})`
- `LiveTickLoop` tick 末：`MonitorExecutor.drain_priority_zero()` 同 tick 消费 finalize/start（保 G4/G1）
- 集成测：mock offline 时间线 → 仅一条 finalize 任务被执行

### Task P2-5: CLI `live status --json`

- 增加 `monitor_tasks: { pending, running, failed }` 计数
- 测试：`tests/unit/test_live_status_cli.py` 扩展断言

### Phase 2 验收

```bash
pytest tests/unit/test_monitor_task_repo.py tests/unit/test_live_scheduler.py -v
media2text live status --json
# G5：VOD drain 20min 模拟时 LiveTick 仍 ~10s（参照 test_live_scheduler.py）
```

---

## 并行化策略

| Lane | 任务 | 依赖 |
|------|------|------|
| A | Task 1 → 2 → 3 | 顺序（共享 `repos.py` / `db.py`） |
| B | Task 5（API drain） | Task 2 完成后可并行 |
| C | Task 4（recording 拆分） | Task 3 完成后 |

推荐：**Task 1→2→3→4→5→6** 单分支顺序实施，避免 `recording.py` 与 snapshot 接口冲突。

---

## NOT in scope（本计划）

- `monitor_tasks` 与 `post_process_jobs` 合并（spec §12 已否决）
- 多进程 observe/execute
- Desktop 队列积压 UI（Phase 3）
- 修改四色灯语义

---

## 失败模式与测试映射

| 失败模式 | Phase 1 覆盖 |
|----------|----------------|
| daemon 写 outbox 后 API 未 drain | `test_api_state_event_drain` + 手动 |
| `get_live_room` 超时 snapshot 冻结 | `test_snapshot_probe_failure` |
| observe 误调开录 | `test_live_observe_state` O3 |
| stale lock | 已有 `test_process_lock` |

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & reliability | 1 | CLEAR (PLAN) | 6 issues, outbox 方案已入 spec |
| CEO Review | — | — | 0 | — | — |
| Design Review | — | — | 0 | — | — |

**VERDICT:** Eng Review CLEARED — Phase 1 可实施。
