---
issue: 367
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/367
branch: issue-367-monitor-db-lock-dl4a
depends_on: []
---

# DL-4a：`DbWriteGateway` Writer 线程 + 生命周期

GitHub Issue: [#367](https://github.com/oychao1988/media2text/issues/367)  
Epic：**Monitor DB Write Path Phase 2**（2026-07-05）  
规格：[monitor-db-write-gateway-session-sm-design.md](../superpowers/specs/2026-07-05-monitor-db-write-gateway-session-sm-design.md) §4  
系列：**DL-4a** → DL-4b → MH-4a → …

## 背景

2026-07-03 事故：`task_scheduler_db_locked` ×47，根因是进程内多线程裸 `commit()` 与 `with_db_lock_retry` 分裂。用户决策：**单 Writer 线程 + 单写连接**，所有写经 `DbWriteGateway` 队列。

本 Issue 交付 gateway 骨架与 lifecycle，**不**迁移全部 repos（→ DL-4b）。

## 验收标准

### Task 1 — `DbWriteGateway` 模块

- [x] 新增 `src/media2text/core/storage/write_gateway.py`：`start` / `shutdown` / `write` / `read` / `write_batch`
- [x] Writer 线程持 **单条** `sqlite3.Connection`（`check_same_thread=False`）；caller `write(fn)` 经 `Future` 阻塞等待
- [x] Writer 内 `database is locked` 指数退避重试（与 `with_db_lock_retry` 参数一致：max 6, base 0.2s）
- [x] `write()` 在 writer 线程内调用 → `RuntimeError`（禁重入）
- [x] `get_write_gateway(cfg)` 进程 singleton；`serve` lifespan + `MonitorSupervisor` 启动/停止 gateway

### Task 2 — `WriteGuard`

- [x] 新增 `WriteGuard`：writer fn 执行期间 thread-local 标记
- [x] `playwright_exclusive` 入口在 WriteGuard active 时 log warning（strict 模式可 raise，默认 warning）

### Task 3 — 兼容层

- [x] `with_db_lock_retry` 委托 `get_write_gateway().write`（迁移期）
- [x] `config.example.yaml` 增加 `monitor.write_gateway.*`（queue_maxsize、timeout、shutdown_drain_sec）

### Task 4 — 测试与 doctor

- [x] `tests/unit/test_db_write_gateway.py`：并发 write 无 sustained locked；shutdown drain；重入拒绝
- [x] `media2text doctor --json` 输出 `write_gateway.running`、`write_gateway.queue_depth`（idle 时 0）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_db_write_gateway.py tests/unit/test_db_lock_retry.py -v
ruff check src/media2text/core/storage/write_gateway.py src/media2text/core/storage/db.py
pyright src/media2text/core/storage/write_gateway.py
media2text doctor --json | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'write_gateway' in str(d) or d.get('ok')"
```

## 非目标范围

- P0 repos 迁移（→ DL-4b）
- 删除 `_sqlite_write_lock`（→ DL-4d）
- SessionStateMachine（→ MH-4a）
- Feature flag 默认 false 可选；本 Issue 完成后 gateway 可被单测与子进程测试启用

## 依赖与顺序

- **无前置**；阻塞 DL-4b、MH-4a
