---
issue: 246
epic: local-pipeline-spec-gap-fix
github: 246
branch: issue-246-local-pipeline-gap-fix-gf1
depends_on: [237]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md
---

# Local Pipeline Gap Fix GF-1：Reconciler-only tasks + Scheduler tick 顺序

## 背景

Epic #230–#237 已交付 Probe→Reconcile→Worker 主路径，但代码审计（2026-06-09）仍有两处 spec 硬约束违反：

1. **I.0**：`monitor_executor._run_sync_catalog` 在 Worker 内 `MonitorTaskRepo.enqueue(download)`，绕过 TaskReconciler。
2. **I.2**：`TaskSchedulerLoop.tick_once` 顺序为 content → post_process；规格与 plan D4 要求 **post_process 先于 content**。

本 Issue 对应 gap-fix 计划 **GF-1**（Eng Review D3A：download dedupe 已存在时仍清 `sync_needs_download` flag）。

**参考**

- 规格：[2026-06-08-m2t-local-pipeline-refactor-design.md](../superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md) §I.0、§I.2
- 计划：[2026-06-09-m2t-local-pipeline-spec-gap-fix.md](../superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md) GF-1 Tasks 1–3

**依赖**：#237（notify outbox 基础）已合并；与 #239 共享 `live/` 模块，建议先合并本单。

## 验收标准

### Task 1 — RC-04 sync→download 经 Reconciler

- [x] DB 迁移：`creators.sync_needs_download INTEGER DEFAULT 0`
- [x] `CreatorRepo.mark_sync_needs_download` / `clear_sync_needs_download`
- [x] `_run_sync_catalog` 成功时 mark flag，**删除** Worker 内 `enqueue(download)`
- [x] `reconcile_content` RC-04：`sync_needs_download=1` → `ensure_task(download:...)`
- [x] **Edge（D3A）**：`has_active_dedupe(f"download:{id}")` 时仍 `clear_sync_needs_download`
- [x] `test_reconcile_download_after_sync_catalog_success` 通过
- [x] `test_reconcile_clears_flag_when_download_already_pending` 通过

### Task 2 — Scheduler drain 顺序

- [x] `tick_once` 顺序：reconcile → p0 → live p1–9 → **post_process** → content p10+
- [x] `test_scheduler_tick_order_post_process_before_content` 通过

### Task 3 — `reconciler_enabled=false` 文档化

- [x] `reconciler_enabled=False` 时 startup warning（legacy probe enqueue 已移除）
- [x] `config.example.yaml` 注释更新；spec 附录 D 注明迁移窗口结束

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_task_reconciler.py tests/unit/test_task_scheduler.py tests/unit/test_live_worker_tasks.py -v
ruff check src/media2text/core/live/task_reconciler.py src/media2text/core/live/monitor_executor.py src/media2text/core/live/task_scheduler.py src/media2text/core/storage/db.py
```

## 非目标范围

- Notify outbox 闭环（#247 GF-2）
- SlowTick 独立 conn / 删 dead code（#248）
- StateWriter 全量收口 / `probe_parallelism`（#249）
- 删除 `reconciler_enabled` 配置字段（仅 warning）
- API/agent 手动 enqueue 改 Reconciler

## 依赖与顺序

- **依赖**：#237 已合并
- **阻塞**：#247（GF-2 notify）建议在本单之后合并

## 实现备注

- 分支：`issue-246-local-pipeline-gap-fix-gf1`
- GitHub Issue: [#246](https://github.com/oychao1988/media2text/issues/246)
