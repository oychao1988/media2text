---
issue: 347
epic: monitor-hardening-2026-06-26
github: 347
branch: issue-347-monitor-hardening-mh3
depends_on: []
---

# MH-3：prepare 开录路径 — Playwright 解耦 + hybrid DB conn

> **Superseded (2026-07-05):** MH-4c/MH-4d 已移除 `watcher._conn` hybrid 路径；live worker 经 `SessionStateMachineRegistry` + `DbWriteGateway` dispatch，见 [monitor-db-write-gateway-session-sm-design.md](../superpowers/specs/2026-07-05-monitor-db-write-gateway-session-sm-design.md) §5.4–5.5。

GitHub Issue: [#347](https://github.com/oychao1988/media2text/issues/347)  
Epic：**Monitor Hardening**（2026-06-26）  
系列：MH-1 / MH-2 / **MH-3** 可并行 → MH-4

## 背景

`prepare_live_recording` 在 `MonitorExecutor` 外层包 `playwright_exclusive()`，与 `sync_catalog` 共享 semaphore(2)。content 任务占锁时，live-critical 的 prepare 可能 `TimeoutError`，表现为「已开播但 `active_recordings` 为空」（2026-06-25 事故模式）。

Eng review 原拟「worker 全换独立 conn」，outside voice 指出 `LiveRecordingCore` 故意绑定 `watcher._conn`（STT/ffmpeg side effects 超越 task 生命周期）。**决议：hybrid** — claim/mark 用 task conn，core 仍 `watcher._conn`。

**参考**

- Eng review D3、D5（hybrid）；outside voice nested `resolve_stream_via_web_enter` 仍可能抢锁
- `src/media2text/core/live/monitor_executor.py`、`src/media2text/core/playwright_env.py`

## 验收标准

### Task 1 — prepare 移出 executor 层 Playwright 锁

- [x] `prepare_live_recording` **不在** `run_monitor_task` 的 `playwright_exclusive()` 分支（从 `_PLAYWRIGHT_TASK_TYPES` 移除或等价）
- [x] 单元测：mock `playwright_exclusive` 被 content 任务长期占用时，`prepare_live_recording` 仍可 dispatch（不 TimeoutError 于 acquire）

### Task 2 — nested Playwright 审计（最小修复）

- [x] 梳理 `run_prepare_live_recording` → `resolve_stream` / `fetch_web_enter_payload` 路径；在 Issue 正文或代码注释记录哪些分支仍内层 `playwright_exclusive()`
- [x] 若 HTTP/adapter 可解析 stream 则 **不** 启动 Playwright（已有逻辑保持或补强）
- [x] 可选：probe tick 活跃时 prepare 使用更短 acquire timeout（仅当仍必须 Playwright 且实现简单）

### Task 3 — hybrid conn 文档 + claim 路径

- [x] `MonitorTaskRepo.claim/mark_done/fail` 继续使用 worker `open_db()` conn
- [x] `_core_for_task` 保持 `watcher.core_for_platform(watcher._conn, …)`；补充注释说明 STT/session 生命周期约束
- [x] 若 claim 路径仍写 `watcher._conn`，改为 task conn（仅 repo 操作，不迁移 core）
- [x] `test_live_worker_tasks.py::test_prepare_live_recording_task` 仍 PASS

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_live_worker_tasks.py tests/unit/test_task_scheduler.py -v -k prepare
ruff check src/media2text/core/live/monitor_executor.py src/media2text/core/live/recording.py
```

## 非目标范围

- 全量 SessionRuntime / core  per-worker conn 重构（outside voice 警告范围）
- 增加 Playwright semaphore 至 >2
- G1 benchmark（MH-4）

## 依赖与顺序

- 与 MH-1、MH-2 可并行
- MH-4 集成测依赖本 Issue 的 prepare 行为稳定
