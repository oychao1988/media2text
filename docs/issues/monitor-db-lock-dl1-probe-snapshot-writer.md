---
issue: 356
epic: monitor-db-lock-write-path-2026-06-30
github: 356
branch: issue-356-monitor-db-lock-dl1
depends_on: []
---

# DL-1：Live probe 探活与写 DB 分离 + snapshot 串行写入

GitHub Issue: [#356](https://github.com/oychao1988/media2text/issues/356)  
Epic：**Monitor DB Lock Write Path**（2026-06-30 直播快照 stale / database is locked 跟进）  
系列：**DL-1** → DL-2 → DL-3

## 背景

2026-06-30 事故：博主在播但 Desktop 显示离线。根因链：

1. `probe_live` 并行 worker 在 `_observe_for_probe` 中 **open_db → Playwright/HTTP（20–30s）→ upsert snapshot → close**；多路探活结束时间接近，**写 snapshot 在同一秒碰撞**。
2. `LiveTickLoop` 主连接在整轮 probe 期间保持打开，与 TaskScheduler（1s tick）叠加写竞争。
3. SQLite WAL 下写者串行；`busy_timeout=5000` 后报 `database is locked`，快照无法刷新 → Desktop 按 stale 规则显示离线。

MP/MH Epic 已缓解 post_process 重复入队、单 owner、live lane 让路，但 **probe 路径仍在慢 I/O 期间持有连接并在并行时_burst 写**。

本 Issue：**探活不持 DB 连接；snapshot/desktop_events 写入经进程内串行锁 + 短连接**。

## 验收标准

### Task 1 — `persist_live_probe_result` 短连接 + 串行写

- [x] 新增 `core/live/snapshot.py`（或同级模块）函数：`persist_live_probe_result(cfg, creator_id, live_info, *, error=None)`  
  - 进程内 `threading.Lock` 串行化 snapshot / probe_error / `creator.updated` outbox 写入  
  - `open_db` → 写 → `close`，持锁期间不做 HTTP/Playwright
- [x] `_observe_for_probe` 改为：仅 `_fetch_live_info`（无 conn）→ `persist_live_probe_result`
- [x] 现有 `observe_live_state`（带 conn 路径）可委托同一 persist 函数或保持等价语义

### Task 2 — 测试

- [x] 更新/新增单测：并行 probe 后 4 博主 snapshot 均写入；mock 验证 persist 阶段使用独立短连接（非探活期间长占）
- [x] 新增单测：并发两次 `persist_live_probe_result` 不产生 `database is locked`（同进程 `tmp_path` DB）
- [x] `tests/unit/test_probe_live_parallel.py`、`test_live_snapshot_upsert.py`、`test_live_observe_state.py` 仍 PASS

### Task 3 — 配置

- [x] 恢复 `config.example.yaml` 中 `monitor.probe_parallelism` 推荐值为 **4**（DL-1 后并行探活安全）；文档注释一句「写 snapshot 已串行化」

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_probe_live_parallel.py tests/unit/test_live_snapshot_upsert.py tests/unit/test_live_observe_state.py tests/unit/test_snapshot_probe_failure.py tests/unit/test_live_db_lock_probe_snapshot.py -v
ruff check src/media2text/core/live/snapshot.py src/media2text/core/live/recording.py
```

## 非目标范围

- `post_process` summarize 长占连接（→ DL-2）
- `monitor_self_heal` / serve drain 外部模式（→ DL-3）
- 提高 `busy_timeout`（→ DL-3）
- 去掉 `MonitorWatcher._conn` 长连接（MH-3 hybrid，另 Epic）
- 多进程 SQLite 换 PostgreSQL

## 依赖与顺序

- **无前置**；阻塞 DL-2、DL-3 合并（建议先合并本单）
