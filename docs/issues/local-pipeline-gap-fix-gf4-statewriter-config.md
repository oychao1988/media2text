---
issue: 249
epic: local-pipeline-spec-gap-fix
github: 249
branch: issue-249-local-pipeline-gap-fix-gf4
depends_on: [248]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-spec-gap-fix.md
---

# Local Pipeline Gap Fix GF-4：StateWriter 收口 + probe_parallelism + 验收文档

## 背景

#236 完成 R3b 部分收口；gap 审计仍见 Probe 直调 `upsert_live_snapshot` / `record_event` / `enqueue_creator_updated`。另 `monitor.probe_parallelism` 配置存在但未接线（`probe_live` 仍用 `live.scan_concurrency`）。

本 Issue 完成 **GF-4** + Epic 验收表更新（Task 13）。

**参考**

- 规格 §I.3、§I.4、R3b
- 计划 GF-4 Tasks 10–13

**依赖**：#248 建议先合并（`recording.py` 重叠）。

## 验收标准

### Task 10 — StateWriter 收口

- [x] `StateWriter.update_snapshot(creator_id, live_info)` 包装 snapshot + creator_updated
- [x] `StateWriter.record_pipeline_event(...)` 包装 `record_event`
- [x] `probe_live` / `observe_live_state` / `poll_active_session` 改调 StateWriter
- [x] `scripts/check_no_direct_live_repo.py` 扩展：禁止 guarded 文件 direct upsert/record/enqueue
- [x] `test_state_writer_update_snapshot` / `test_state_writer_record_pipeline_event` 通过

### Task 11 — probe_parallelism 接线

- [x] `_probe_workers(cfg, n)`：`probe_parallelism or scan_concurrency`，clamp 到 `[1, n_targets]`
- [x] `probe_live` 使用 `_probe_workers`
- [x] `config.example.yaml` 注释：`probe_parallelism` 优先于 `live.scan_concurrency`
- [x] 单测覆盖 parallelism 优先逻辑

### Task 12 — Probe guard strict（dev）

- [x] `monitor.probe_guard_strict: bool = False`
- [x] `ProbeExecutionGuard.exit_probe_tick(strict=cfg.monitor.probe_guard_strict)`
- [x] 默认 false；dev config 可 true

### Task 13 — 文档与 Epic 验收

- [x] 更新 `docs/superpowers/verification/2026-06-09-m2t-local-pipeline-refactor-acceptance.md`（GF-1..4 对应行）
- [x] 更新 `docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md` Status：「主干已交付，GF 已补完」

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_state_writer.py tests/unit/test_probe_guard.py tests/unit/test_poll_active_obs.py tests/unit/test_task_scheduler.py -v
python scripts/check_no_direct_live_repo.py
ruff check src/media2text/core/live/state_writer.py src/media2text/core/live/recording.py src/media2text/core/live/probe.py
python scripts/epic_verify.py local-pipeline-refactor 2>/dev/null || true
```

## 非目标范围

- G1′ 开录 P95 自动化基准（单独 issue）
- Desktop Vitest pipeline_phase UI
- 删除 `reconciler_enabled` 字段
- Notify 全 kind 迁移（#247 范围）

## 依赖与顺序

- **依赖**：#248 建议先合并
- **Epic 终点**：本单合并后跑 `epic_verify.py` + 填 acceptance 表

## 实现备注

- 分支：`issue-249-local-pipeline-gap-fix-gf4`
- GitHub Issue: [#249](https://github.com/oychao1988/media2text/issues/249)
