---
issue: 370
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/370
branch: issue-370-monitor-session-sm-mh4b
depends_on: [mh4a]
---

# MH-4b：删除 watcher / LiveWatcher 长连接 + LiveObserveService

GitHub Issue: [#370](https://github.com/oychao1988/media2text/issues/370)  
Epic：**Monitor DB Write Path Phase 2**  
规格：§5.6  
系列：MH-4a → **MH-4b** → MH-4c

## 背景

`MonitorWatcher._conn` + `DouyinLiveWatcher._conn` + `BilibiliLiveWatcher._conn` 导致 7/3 `lsof` 10+ DB FD。MH-4a 已有 StateMachine；本 Issue **删除全部长连接**，probe/poll 改短连接 + gateway。

## 验收标准

### Task 1 — 删除长连接

- [ ] `MonitorWatcher` 无 `self._conn`；VOD/archive/dynamic tick 用 `gateway.read` / `gateway.write`
- [ ] `DouyinLiveWatcher` / `BilibiliLiveWatcher` 无 `_conn`；`core_for_conn` 改为 factory 无 conn 绑定
- [ ] grep 无 `watcher._conn` 生产路径（测试 mock 除外）

### Task 2 — LiveObserveService

- [ ] 新增 `LiveObserveService`（或等价）：`poll_active_recordings(registry, gateway)` 替代 `run_poll_active` 长 conn 路径
- [ ] `run_live_probe_tick` Phase1/3 仅用 gateway + registry

### Task 3 — 测试

- [ ] `tests/unit/test_live_observe_no_long_conn.py`：poll 期间无持久 `open_db` 连接（spy）
- [ ] `tests/unit/test_probe_live_parallel.py` 仍 PASS

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_live_observe_no_long_conn.py tests/unit/test_probe_live_parallel.py tests/unit/test_live_scheduler.py -v
ruff check src/media2text/core/monitor/watcher.py src/media2text/core/platform/douyin/live.py src/media2text/core/platform/bilibili/live.py
```

## 非目标范围

- `monitor_executor` MH-3 删除（→ MH-4c）
- `recording.py` facade 瘦身（→ MH-4d）

## 依赖与顺序

- **依赖 MH-4a**；阻塞 MH-4c
