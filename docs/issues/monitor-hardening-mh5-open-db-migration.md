---
issue: 349
epic: monitor-hardening-2026-06-26
github: 349
branch: issue-349-monitor-hardening-mh5
depends_on: []
---

# MH-5：`open_db()` migration 单次化

GitHub Issue: [#349](https://github.com/oychao1988/media2text/issues/349)  
Epic：**Monitor Hardening**（2026-06-26）  
系列：与 MH-1–MH-4 **可并行**、**独立 PR**

## 背景

daemon 热路径（`live-probe`、`task-scheduler`、`slow-tick`）每秒多次 `open_db()`。若每次 connect 执行全量 schema migration / 探测，放大 SQLite `_connect_lock` 持有时间。MP Epic 验收 §非本 Epic 已列为 follow-up；eng review D11 确认纳入本 Epic 独立交付。

## 验收标准

### Task 1 — 进程内 migration 单次化

- [x] `open_db()` / `connect()`：migration 在同一进程内仅执行一次（模块级 flag 或读 `schema_migrations` 版本后 skip）
- [x] 多线程首次并发 connect 仍安全（现有 lock 或 double-check）
- [x] 不改变 migration 语义；新库首次仍完整 migrate

### Task 2 — 测试

- [x] 单元测：同一进程两次 `open_db(cfg)`，migration 入口调用次数为 1（mock/spy）
- [x] 现有 `tests/unit/test_live_db_migration.py` 仍 PASS

### Task 3 — 文档

- [x] `CLAUDE.md` 或 monitor spec 脚注一句：daemon 依赖单次 migration

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_live_db_migration.py tests/unit/test_task_scheduler.py -v -q
ruff check src/media2text/core/workspace.py src/media2text/core/storage/db.py
```

## 非目标范围

- WAL / busy_timeout 调参 alone
- 多进程 daemon 共享 migration 状态（仍单进程 lock 模型）
- MH-1–MH-4 行为变更

## 依赖与顺序

- **无前置**；建议与 MH-1 同 release train，独立 merge
