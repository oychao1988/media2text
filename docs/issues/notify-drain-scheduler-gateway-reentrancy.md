---
issue: 385
epic: monitor-db-write-path-phase2-2026-07-05
github: https://github.com/oychao1988/media2text/issues/385
branch: issue-385-notify-drain-scheduler-reentrancy
depends_on: [372]
---

# Fix：TaskScheduler notify drain 在 gateway write_batch 内重入失败

## 背景

DL-4c（#372）将 `notify/drain.py` 改为经 `DbWriteGateway.write` 执行。`TaskSchedulerLoop.tick_once` 末尾仍调用 `drain_once()`，而 tick 本身已在 `gw.write_batch(...)` 的 **writer 线程** 内运行。

`gateway_write` 禁止 writer 线程重入，每秒触发：

```
RuntimeError: DbWriteGateway.write cannot be called from writer thread
```

Desktop 内嵌 monitor 日志表现为 **`notify drain tick failed`**（约 1s 一次）。

## 复现步骤

1. 启动 Desktop 内嵌 monitor（或 `monitor watch --daemon` + gateway 已启）
2. 打开 DaemonCard 日志面板
3. 观察每秒 `notify drain tick failed`

## 验收标准

- [x] `drain_once` 移出 `write_batch` 回调，在 scheduler tick 完成后调用
- [x] 新增回归单测：gateway `write_batch(tick_once)` 后 `drain_once` 不抛重入异常且 pending 清零
- [x] `test_notify_daemon_drain.py` 全部 PASS
- [x] `ruff check` 相关文件 PASS

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_notify_daemon_drain.py tests/unit/test_db_write_gateway.py -v
ruff check src/media2text/core/live/task_scheduler.py tests/unit/test_notify_daemon_drain.py
```

## 非目标范围

- notify outbox 双 drain（API sidecar + scheduler）竞态去重
- Desktop 日志 UI 展示 exception 详情

## 依赖与顺序

- **根因**：#372 DL-4c gateway 迁移遗漏
- **阻塞**：无

## 实现备注

- 分支：`issue-385-notify-drain-scheduler-reentrancy`
- GitHub Issue: [#385](https://github.com/oychao1988/media2text/issues/385)
