---
issue: 234
epic: local-pipeline-refactor
github: 234
branch: issue-234-local-pipeline-refactor-pr5-cutover
depends_on: [233]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR5：R2c-3 Reconciler 默认开启 + Probe-only 切流

## 背景

R2c-1/2 在 flag 保护下落地 Reconciler 与 Probe Guard 后，本 PR **删除 legacy probe 路径**：抖音/B 站 `run_once` 仅 LP-01/02/03；`reconciler_enabled` 默认 true；移除 inline finalize/enqueue 与 `_run_once_legacy`。此为 Execution Engine v2 **Epic 主闸门**，并填写 Epic 验收表。

**阻塞 Client-Primary**：[Client-Primary 控制面](../superpowers/specs/2026-06-08-m2t-client-primary-control-plane-design.md) Phase 1 出口需本 PR + R3a + R3b。

**参考**：计划 R2c-3 Task 13 · Epic 验收 G1–G5

**依赖**：PR4（Guard + poll_active_session）已合并。

## 验收标准

### Task 13 — Platform run_once probe-only

- [x] `douyin/live.py`、`bilibili/live.py`：`run_once` 仅 `poll_active_recordings` + `probe_live` + stale 标记
- [x] 删除 probe path 内 `scan_and_start`（RR-01 → LW-01 经 Reconciler）
- [x] `MonitorConfig.reconciler_enabled: bool = True` 默认
- [x] 删除 `poll_active_recordings` legacy enqueue 分支
- [x] `LiveTickLoop` 线程名已为 `live-probe`（类名保留）

### Epic 闸门测试

- [x] 全量：`test_probe_guard`、`test_task_reconciler`、`test_poll_active_obs`、`test_live_worker_tasks`、`test_live_scheduler`、`test_task_scheduler` 全绿
- [x] `tests/e2e/test_live_pipeline_reconciler.py`：mock is_live → prepare → offline → finalize 时间线
- [x] 填写 `docs/superpowers/verification/2026-06-09-m2t-local-pipeline-refactor-acceptance.md`（G1–G5 初版）

### 可观测

- [x] `media2text live status --json` 仍含 monitor_tasks 统计（回归）
- [x] `media2text doctor --json` exit 0（**本地/开发机**；CI 无 ffmpeg/session，不纳入 issue_verify）

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_probe_guard.py tests/unit/test_task_reconciler.py tests/unit/test_poll_active_obs.py tests/unit/test_live_worker_tasks.py tests/unit/test_live_scheduler.py tests/unit/test_task_scheduler.py tests/unit/test_session_runtime.py -v
pytest tests/e2e/test_live_pipeline_reconciler.py -v
ruff check src/media2text/core/platform/douyin/live.py src/media2text/core/platform/bilibili/live.py src/media2text/core/live/recording.py src/media2text/core/config.py
media2text live status --json
```

## 非目标范围

- `pipeline_phase` API（#235）
- StateWriter 全量 + CI grep（#236）
- notify_events outbox（#237）
- 真实网络 live E2E（`-m live` 可选人工）
- Redis / 多机调度

## 依赖与顺序

- **依赖**：PR4 已合并；`test_probe_never_enqueues` 已绿
- **Epic**：R3a/R3b/R4 可并行于本 PR 之后；Client-Primary 等 R3a+R3b+本 PR

## 实现备注

- 分支：`issue-234-local-pipeline-refactor-pr5-cutover`
- GitHub Issue: [#234](https://github.com/oychao1988/media2text/issues/234)
- Epic manifest：`docs/issues/epic-manifests/local-pipeline-refactor.yaml`（本 Issue 为 R2c 终点）
