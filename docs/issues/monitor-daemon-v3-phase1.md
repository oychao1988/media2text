# Monitor Daemon v3 Phase 1：状态贡献 + 观测/开录拆分

## 背景

Desktop 左侧栏直播状态灯与 `monitor watch --daemon` 实际 poll 结果脱节：daemon 为**独立子进程**，写 `creator_live_snapshots` 后无法调用 API 进程内 `EventsHub`，`creator.updated` WS 不触发；`get_live_room` 失败时 `live_info is None` 导致 snapshot `checked_at` 冻结。

v2 三线程调度（LiveTick / SlowTick / PostProcessPool）已交付，但 `scan_and_start` 仍耦合「检测 + 开录」。本 Issue 落实 **Phase 1**：跨进程状态推送（outbox）、观测函数无副作用（O3）、探测失败不冻结 snapshot，**不**引入 `monitor_tasks` 队列。

**参考**

- 设计：[2026-06-05-monitor-daemon-observe-execute-design.md](../superpowers/specs/2026-06-05-monitor-daemon-observe-execute-design.md)（eng review 2026-06-05，§0/§7/§8 Phase 1）
- 实施计划：[2026-06-05-monitor-daemon-v3.md](../superpowers/plans/2026-06-05-monitor-daemon-v3.md) Task 1–6
- 代码锚点：`recording.py`、`snapshot.py`、`api/app.py`、`events_hub.py`

**症状（2026-06-05 排查）**

| 现象 | 根因 |
|------|------|
| 在播但 🔴/⚫ 不准 | snapshot 过期；daemon 未跑时 API 限流 refresh |
| 列表不随 poll 刷新 | 无 daemon→API 跨进程事件桥 |
| Daemon 启动失败 | stale lock（`test_process_lock` 已覆盖，本 Issue 回归） |

## 验收标准

### Task 1 — DB 迁移 `desktop_events` + `probe_error`

- [ ] `_migrate_desktop_v2`：`desktop_events` 表（`event_type`、`creator_id`、`payload_json`、`created_at`、`delivered_at`）+ 部分索引 `idx_desktop_events_pending`
- [ ] `creator_live_snapshots.probe_error TEXT` 可空列
- [ ] `CreatorLiveSnapshotRow` 含 `probe_error`
- [ ] `tests/unit/test_desktop_db_migration.py::test_desktop_v2_tables_and_probe_error`

### Task 2 — `DesktopEventRepo`

- [ ] `enqueue_creator_updated(creator_id)` → 返回 event id
- [ ] `claim_pending(limit)` / `mark_delivered(id)`；已交付不再被 claim
- [ ] `tests/unit/test_desktop_event_repo.py`

### Task 3 — snapshot 变更检测 + 探测失败 touch

- [ ] `LiveSnapshotRepo.upsert` 返回 `bool changed`（`is_live`/`room_id`/`title` 不变则 false；成功时清 `probe_error`）
- [ ] `upsert_live_snapshot` 返回 changed；`live_info is None` 时返回 false（不 silent return 冻结）
- [ ] `touch_snapshot_probe_failed(conn, creator_id, error=…)` 仅更新 `checked_at` + `probe_error`，不改 `is_live`
- [ ] `core/desktop/state_events.py`：`enqueue_creator_updated(conn, creator_id)`（**禁止** `import media2text.api`）
- [ ] `tests/unit/test_snapshot_probe_failure.py`

### Task 4 — `observe_live_state` / `maybe_start_recording`

- [ ] `observe_live_state(creator)`：拉 live、upsert、变更或 probe touch 后写 outbox；**不**调用 `_start_recording` / ffmpeg
- [ ] `maybe_start_recording(creator, live_info)`：封装现有 `_start_recording` 快速通道
- [ ] `scan_and_start` 改为 observe →（auto_record 时）maybe_start；对外行为不变
- [ ] `poll_active_recordings`：`offline_since_at` / finalize 相关 snapshot 或 session 变更后 enqueue outbox
- [ ] `tests/unit/test_live_observe_state.py`（O3）；既有 `test_live_snapshot_upsert` / `test_live_recording_auto_record` 全绿

### Task 5 — API `StateEventDrain` + lifespan

- [ ] `api/services/state_event_drain.py`：`drain_once(cfg)`、`run_drain_loop`（间隔 1–2s）
- [ ] drain：`claim_pending` → `events_hub.publish(creator.updated)` → `mark_delivered`
- [ ] 内层 `FastAPI`（`/api` mount）挂 `lifespan` 启动/停止协程
- [ ] `tests/unit/test_api_state_event_drain.py`：outbox 行 → WS 收到 `creator.updated` → `delivered_at` 非空

### Task 6 — 质量与成功指标

- [ ] O1：daemon 运行时 `checked_at` ≤ 2× `live_poll`（手动 `GET /api/creators` + DB）
- [ ] O2：snapshot/session 变更后 Desktop ≤3s 灯更新（WS 或 20s 轮询兜底）
- [ ] O3：单测证明 observe 路径无 `recording_started`
- [ ] O6：`test_process_lock` + `test_api_daemon` 回归全绿
- [ ] `ruff` / `pyright` 新文件无新增错误

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"

pytest tests/unit/test_desktop_db_migration.py \
  tests/unit/test_desktop_event_repo.py \
  tests/unit/test_snapshot_probe_failure.py \
  tests/unit/test_live_observe_state.py \
  tests/unit/test_api_state_event_drain.py \
  tests/unit/test_live_snapshot_upsert.py \
  tests/unit/test_live_recording_auto_record.py \
  tests/unit/test_process_lock.py \
  tests/unit/test_api_daemon.py \
  tests/unit/test_api_events_ws.py \
  -v -m desktop

ruff check src/media2text/core/desktop src/media2text/core/live/snapshot.py \
  src/media2text/api/services/state_event_drain.py
pyright src/media2text/core/desktop/state_events.py \
  src/media2text/api/services/state_event_drain.py
```

**手动验收（O1/O2）**

```bash
media2text doctor --json
# 终端 A: media2text serve --port 8765
# 终端 B: media2text monitor watch --daemon
# Desktop: pnpm --filter m2t-desktop tauri dev
# 预期：在播博主 poll 后 ≤3s 左侧灯变化；daemon 日志含 snapshot/outbox 相关记录
```

## 非目标范围

- `monitor_tasks` 表、`MonitorExecutor`、SlowTick 搬迁（→ Phase 2 Issue）
- finalize 入队改造、`poll_active` 删除直接 `_finalize_recording`（→ Phase 2）
- 多进程 daemon、Redis 队列、平台 Webhook
- 修改四色灯语义、`compute_status_light` 规则
- Desktop 队列积压 UI（Phase 3）
- 合并 `post_process_jobs` 与 monitor 队列

## 依赖与顺序

- **依赖**：Live Pipeline v2（#81–#87）、m2t-desktop P3 events WS（#128）已交付
- **建议分支**：`issue-<N>-monitor-daemon-v3-phase1`
- **阻塞**：Monitor Daemon v3 Phase 2；Desktop 左侧栏实时性验收

## 实现备注

- GitHub Issue: [#145](https://github.com/oychao1988/media2text/issues/145)
- 分支：`issue-145-monitor-daemon-v3-phase1`
- core 层 **不得** `import media2text.api`；跨进程仅用 SQLite outbox
- 自动开录 **保留** LiveTick 同线程快速路径（G1 P95 ≤30s）
- Phase 1 完成后更新 spec 状态为「Phase 1 已交付」
