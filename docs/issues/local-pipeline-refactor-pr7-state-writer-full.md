---
issue: 236
epic: local-pipeline-refactor
github: 236
branch: issue-236-local-pipeline-refactor-pr7-state-writer-full
depends_on: [234]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR7：R3b StateWriter 全量收口 + CI

## 背景

R2c 引入 StateWriter 最小集后，仍有 scattered `LiveSessionRepo` 直接写 session/offline/manifest。本 PR 将所有 live session 突变路由经 `StateWriter`，并加 CI grep/script 防止回归。

**参考**：规格 StateWriter 单写口 · 计划 R3b Task 15

**依赖**：PR5 已合并（R3b 与 R3a 可并行）。

**阻塞**：PR8（notify 经 StateWriter enqueue）；Client-Primary Phase 1。

## 验收标准

### Task 15 — 迁移 direct repo 写

- [x] `recording.py` / `platform/*/live.py` 不再直接调用 `LiveSessionRepo.set_offline_since` 等（allowlist 仅 `state_writer.py`）
- [x] `update_status`、manifest refresh 等迁入 StateWriter
- [x] `set_offline_since` / `clear_offline_since` 使用 `BEGIN IMMEDIATE` 单事务（session + obs + event + outbox 占位）
- [x] `test_offline_since_atomic` 通过

### CI 守卫

- [x] `scripts/check_no_direct_live_repo.py`：扫描违规 direct write
- [x] `.github/workflows/ci.yml` 增加 check step
- [x] `test_no_direct_repo_outside_state_writer` 或 script 本地 exit 0

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_state_writer.py tests/unit/test_live_scheduler.py -v
python scripts/check_no_direct_live_repo.py
ruff check src/media2text/core/live/state_writer.py src/media2text/core/live/recording.py
```

## 非目标范围

- notify_events 表与 sidecar drain（#237）— 但 StateWriter 需预留 outbox hook
- pipeline_phase（#235）
- asyncio 重写

## 依赖与顺序

- **依赖**：PR5 已合并
- **建议**：在 PR8 之前合并，以便 notify enqueue 只改 StateWriter 一处

## 实现备注

- 分支：`issue-236-local-pipeline-refactor-pr7-state-writer-full`
- GitHub Issue: [#236](https://github.com/oychao1988/media2text/issues/236)
