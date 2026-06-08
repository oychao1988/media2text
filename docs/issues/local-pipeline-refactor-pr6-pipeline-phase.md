---
issue: 235
epic: local-pipeline-refactor
github: 235
branch: issue-235-local-pipeline-refactor-pr6-pipeline-phase
depends_on: [234]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR6：R3a pipeline_phase 投影 + API

## 背景

Desktop / Client-Primary 需要单一字段表达博主直播管线阶段（offline → recording → finalizing → completed）。本 PR 从 `live_sessions` + in-flight `monitor_tasks` + `post_process_jobs` 推导 `pipeline_phase`，并暴露于 `GET /api/creators`。

**参考**：规格 pipeline_phase · 计划 R3a Task 14

**依赖**：PR5（Reconciler 切流）已合并。

**阻塞**：Client-Primary Phase 1（与 PR7 并列出口）。

## 验收标准

### Task 14 — derive_pipeline_phase

- [x] 新建 `pipeline_phase.py`：`derive_pipeline_phase(session, post_jobs=..., monitor_tasks=...)`
- [x] Phase 链覆盖：`offline`、`live_unrecorded`、`recording`、`recording_stt_pending`、`offline_pending`、`finalizing`、`post_processing`、`completed`、`failed`
- [x] `tests/unit/test_pipeline_phase.py` parametrized 用例全绿

### API

- [x] `GET /api/creators`（或现有 creator list DTO）增加 `pipeline_phase` 字段
- [ ] Desktop 可选：只读消费，无强制 UI 改动（Vitest 全量非本 Issue 目标）

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_pipeline_phase.py tests/unit/test_api_creators_list.py -v
ruff check src/media2text/core/live/pipeline_phase.py src/media2text/api/routes/creators.py
```

## 非目标范围

- StateWriter 全量收口（#236）
- notify outbox（#237）
- Desktop Vitest 全量回归 / UI 改版
- WebSocket 推送 pipeline_phase（可后续 Issue）

## 依赖与顺序

- **依赖**：PR5 已合并
- **可与 PR7 并行**（不同文件为主）

## 实现备注

- 分支：`issue-235-local-pipeline-refactor-pr6-pipeline-phase`
- GitHub Issue: [#235](https://github.com/oychao1988/media2text/issues/235)
