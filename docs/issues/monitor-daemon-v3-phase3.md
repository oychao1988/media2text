# Monitor Daemon v3 Phase 3：公平调度、失败重试与 Desktop 队列可见性

## 背景

Phase 2 交付 `monitor_tasks` 有界执行池后，仍存在三类体验缺口：

1. **单博主饥饿**：`claim_pending` 全局 FIFO 时，某博主大量 sync 任务会阻塞其他博主；
2. **失败即死信**：`mark_failed` 后无自动重试，Playwright 瞬时错误需人工清队列；
3. **Desktop 不可见**：`DaemonCard` 仅展示 post_process 积压，看不到 `monitor_tasks`。

**前置**：Monitor Daemon v3 Phase 2（Issue #147）已合并。

**参考**

- 设计 spec §8 Phase 3：[2026-06-05-monitor-daemon-observe-execute-design.md](../superpowers/specs/2026-06-05-monitor-daemon-observe-execute-design.md)
- 计划 NOT in scope 解除项：[2026-06-05-monitor-daemon-v3.md](../superpowers/plans/2026-06-05-monitor-daemon-v3.md)

## 验收标准

### P3-1 — 公平 `claim_pending`

- [ ] `claim_pending` 在相同 priority 范围内，优先各博主**最早** pending 任务（per-creator 公平），再按 `priority ASC, created_at ASC`
- [ ] `priority=0`（finalize）路径行为不变
- [ ] `tests/unit/test_monitor_task_repo.py` 新增多博主饥饿用例

### P3-2 — 失败重试 / DLQ

- [ ] 迁移：`monitor_tasks.attempt_count INTEGER NOT NULL DEFAULT 0`
- [ ] 配置：`monitor.task_max_retries` 默认 **3**（`config.example.yaml` 注释）
- [ ] 执行失败：未达上限 → `pending` + `attempt_count++`；达上限 → `failed`（DLQ）
- [ ] Repo：`retry_failed(task_id)` 将 `failed` 重置为 `pending`（attempt_count 归零）
- [ ] `live status --json` 的 `monitor_tasks` 增加 `dlq`（= failed 计数，或显式 failed 字段保持）

### P3-3 — Desktop 队列积压

- [ ] `GET /api/daemon` 响应增加 `monitor_tasks: { pending, running, failed }`
- [ ] `DaemonCard` meta 行展示 monitor 队列（与 post_process 并列）
- [ ] `tests/unit/test_api_daemon.py` 断言新字段

## 验证命令

```bash
pytest tests/unit/test_monitor_task_repo.py tests/unit/test_api_daemon.py \
  tests/unit/test_live_status_cli.py -v -m desktop
pnpm --filter m2t-desktop test
```

## 非目标范围

- B 站 / 抖音 Observe 拆分为独立 tick（spec §12 #5 暂缓）
- `post_process_jobs` 与 `monitor_tasks` 合并
- 多机 / Redis / Desktop 一键 retry UI

## 依赖与顺序

- **依赖**：Phase 2 Issue #147 已关闭
- **分支**：`issue-149-monitor-daemon-v3-phase3`
- **GitHub Issue**：#149
