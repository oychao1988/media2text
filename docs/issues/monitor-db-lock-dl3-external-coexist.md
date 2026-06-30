---
issue: 358
epic: monitor-db-lock-write-path-2026-06-30
github: 358
branch: issue-358-monitor-db-lock-dl3
depends_on: [356, 357]
---

# DL-3：双监控模式共存 — self_heal 保守 + serve 降写 + busy_timeout

GitHub Issue: [#358](https://github.com/oychao1988/media2text/issues/358)  
Epic：**Monitor DB Lock Write Path**（2026-06-30）  
系列：DL-1 → DL-2 → **DL-3**

## 背景

用户需同时支持：

- **external**：终端 `monitor watch --daemon` + Desktop 作 UI（`managed_by=external`）
- **embedded**：纯 Desktop 内嵌 supervisor

MP-2 已实现 serve 启动 defer external lock，但 2026-06-30 现场仍出现：

1. external 存活、heartbeat stale 时 `monitor_self_heal` 尝试 `takeover` 失败（lock already held）
2. `serve` sidecar 与 external daemon **同时**高频 `open_db`（event drain ~1.5s），放大写碰撞
3. `busy_timeout=5000` 对并行写 burst 偏短

本 Issue：**external 模式下降 serve 写频、self_heal 不对有效 external 做 takeover、提高 busy_timeout 并写路径轻量重试**。

## 验收标准

### Task 1 — `monitor_self_heal` 保守策略

- [x] 当 `read_lock_record.mode == "external"` 且 `is_monitor_watch_pid(lock_pid)`：`heartbeat_stale` 时 **不** 调用 `supervisor.takeover`；返回 `skipped: external_heartbeat_stale`，可选 `recover_stale_work`
- [x] 单测：`test_self_heal_skips_takeover_when_external_alive_but_stale`

### Task 2 — serve drain 在 external 模式降频

- [x] `state_event_drain` / `notify_event_drain`（或 health loop）：当 runtime 判定 `managed_by=external` 时，drain 间隔 ≥ `desktop.external_drain_interval_sec`（默认 5s，`config.example.yaml` 文档化）
- [x] embedded 模式保持现有间隔

### Task 3 — SQLite 写 resilience

- [x] `connect()` 默认 `busy_timeout` 提升至 **15000** ms（`db.py` + SCHEMA 注释）
- [x] `LiveSnapshotRepo.upsert` / 关键写路径：捕获 `OperationalError: database is locked` **最多 2 次**指数退避重试（仅 DL-1 persist 或 repo 层一处，避免散落）

### Task 4 — 测试与文档

- [x] 单测覆盖 self_heal skip、drain interval 分支
- [x] `CLAUDE.md` 或 MP 验收文档补一句：external + Desktop UI 共存时 `managed_by=external` 为预期

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_monitor_self_heal.py tests/unit/test_state_event_drain.py tests/unit/test_live_db_lock_probe_snapshot.py tests/unit/test_monitor_lock.py tests/unit/test_db_lock_retry.py tests/unit/test_api_state_event_drain.py -v
ruff check src/media2text/api/services/monitor_self_heal.py src/media2text/api/services/state_event_drain.py src/media2text/core/storage/db.py
```

## 非目标范围

- 删除 external / embedded 任一模式
- `handoff` / `takeover` API 语义变更
- DL-1/DL-2 已覆盖的 probe/summarize 路径

## 依赖与顺序

- **依赖 DL-1、DL-2 合并**
