---
issue: 247
epic: local-pipeline-spec-gap-fix
github: 247
branch: issue-247-local-pipeline-gap-fix-gf2
depends_on: [246]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md
---

# Local Pipeline Gap Fix GF-2：Notify outbox 闭环（CLI daemon drain）

## 背景

#237 仅让 `StateWriter.set_offline_since` 写 `notify_events`，Sidecar lifespan drain。Gap 审计发现：

- 多数 kind 仍 `notify.emit` 同步路径；`outbox_only` 默认 false；daemon 内 emit 被 skip 且**不入队**
- 纯 CLI `monitor watch --daemon` **无 notify drain**（仅 API sidecar 有）
- `drain_once` 调 `emit()`；若 Task 4 改 emit 入 outbox 会 **无限 re-enqueue**（Eng Review P0）

本 Issue 完成 R4/L6 闭环：**emit→outbox（daemon）+ deliver（drain）+ TaskScheduler tick 末 drain**。

**已锁决策（Eng Review）**

- **D1A**：`NotifyService.deliver()` 与 `emit()` 拆分；drain 只调 `deliver`
- **D2A**：`PostProcessExecutor.submit` worker 入口 `NotifyDaemonGuard.enter()`

**参考**

- 规格 §R4、附录 B（`outbox_only: true` 默认）
- 计划 GF-2 Tasks 4–6、Task 4b、Task 5 增补

**依赖**：#246 建议先合并（共享 scheduler/notify 触达面）。

## 验收标准

### Task 4 — emit 入 outbox（daemon）

- [x] 扩展 `NotifyEvent`：`creator_id`, `session_id`, `dedupe_key`（可选）
- [x] `outbox_only=true` + `NotifyDaemonGuard.is_active()` → `NotifyEventRepo.enqueue`
- [x] 默认 `outbox_only: true`（`config.py` + `config.example.yaml`）
- [x] CLI 非 daemon（Guard 未 active）仍可 sync deliver
- [x] `test_emit_in_daemon_enqueues_when_outbox_only` 通过

### Task 4b — deliver 拆分（阻塞 drain）

- [x] `NotifyService.deliver(event)` — 仅 sound/feishu，永不写 outbox
- [x] `emit()`：daemon+outbox → enqueue；否则 → `deliver()`
- [x] `core/notify/drain.py` 从 `api/services/notify_event_drain.py` 下沉；API 复用
- [x] `drain_once` 改调 `deliver()`，**禁止**经 `emit()`
- [x] `test_notify_drain_delivers_without_reenqueue` 通过
- [x] `test_notify_drain_emits_pending` 更新为 mock `deliver`

### Task 5 — CLI daemon drain

- [x] `TaskSchedulerLoop.tick_once` 末尾 `drain_once(cfg, limit=20)`
- [x] `PostProcessExecutor.submit` 内 `NotifyDaemonGuard.enter()`
- [x] `test_notify_daemon_drain_on_scheduler_tick` 通过
- [x] `test_post_process_emit_enqueues_under_outbox_only` 通过

### Task 6 — StateWriter live_ended 统一 emit

- [x] 删 `_enqueue_notify_outbox` 直写 SQL；改 `NotifyService.emit`（commit 后最终一致可接受）
- [x] 现有 `test_notify_outbox_only`（StateWriter）仍 PASS

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_notify_outbox.py tests/unit/test_notify_daemon_drain.py tests/unit/test_state_writer.py -v
pytest tests/unit/test_task_scheduler.py -v -k notify 2>/dev/null || pytest tests/unit/test_task_scheduler.py -v
ruff check src/media2text/core/notify/ src/media2text/core/live/task_scheduler.py src/media2text/core/live/post_process_pool.py src/media2text/core/live/state_writer.py
```

## 非目标范围

- 飞书 webhook 格式变更
- 所有 call site 一次性加 dedupe_key（热路径 kind 冒烟即可）
- 第四条 daemon 线程（用 tick 末 drain，非新线程）
- G1′ P95 指标

## 依赖与顺序

- **依赖**：#246 建议先合并
- **阻塞**：Epic acceptance L6 在本单后可勾选

## 实现备注

- 分支：`issue-247-local-pipeline-gap-fix-gf2`
- GitHub Issue: [#247](https://github.com/oychao1988/media2text/issues/247)
