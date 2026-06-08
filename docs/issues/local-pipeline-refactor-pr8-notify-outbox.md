---
issue: 237
epic: local-pipeline-refactor
github: 237
branch: issue-237-local-pipeline-refactor-pr8-notify-outbox
depends_on: [236]
spec: docs/superpowers/specs/2026-06-08-m2t-local-pipeline-refactor-design.md
plan: docs/superpowers/plans/2026-06-09-m2t-local-pipeline-refactor.md
---

# Local Pipeline Refactor PR8：R4 notify_events Outbox + Sidecar Drain

## 背景

daemon 路径内同步 `NotifyService.emit` 会阻塞 Worker 且与 Desktop sidecar 模型不一致。本 PR 引入 `notify_events` 表，StateWriter 在 offline 等节点 enqueue，API sidecar 异步 drain（mirror `state_event_drain.py`）。

**参考**：规格附录 A notify_events · 计划 R4 Task 16 · Epic G6/L6

**依赖**：PR7（StateWriter 全量）已合并。

## 验收标准

### Task 16 — DDL + Repo

- [x] `notify_events` 表迁移（spec 附录 A SQL）
- [x] `NotifyEventRepo`：enqueue / claim_pending / mark_done
- [x] `tests/unit/test_notify_outbox.py` 基础 CRUD

### StateWriter 集成

- [x] `set_offline_since` 写 `notify_events` kind=`live_ended`，不再 sync emit
- [x] `test_notify_outbox_only`：mock `NotifyService.emit` 必须 fail；pending count ≥ 1

### Sidecar drain

- [x] `core/notify/outbox.py` + `api/services/notify_event_drain.py`
- [x] `api/app.py` lifespan 启动 drain loop（mirror desktop_events）
- [x] `notify.outbox_only: true` 时 daemon 路径禁止 sync emit（raise 或 log+no-op）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_notify_outbox.py tests/unit/test_state_writer.py -v
pytest tests/unit/test_api_* -v -k notify 2>/dev/null || true
ruff check src/media2text/core/notify/outbox.py src/media2text/api/services/notify_event_drain.py src/media2text/core/live/state_writer.py
media2text doctor --json  # 本地/开发机；CI 无 playwright 浏览器，不纳入 issue_verify
```

## 非目标范围

- 飞书 webhook 格式变更
- 所有 notify kind 一次性迁移（可先 live_ended + recording_completed）
- Redis 队列

## 依赖与顺序

- **依赖**：PR7 已合并
- **Epic 最后一单**：合并后更新 acceptance 表 L6

## 实现备注

- 分支：`issue-237-local-pipeline-refactor-pr8-notify-outbox`
- GitHub Issue: [#237](https://github.com/oychao1988/media2text/issues/237)
