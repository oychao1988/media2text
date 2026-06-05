# Monitor Daemon v3 Phase 2：统一 `monitor_tasks` 执行队列

## 背景

Phase 1 交付跨进程状态推送与观测/开录拆分后，SlowTick 仍内联 Playwright sync/download，`poll_active` 仍直接 `_finalize_recording`，与「检测 → 入队 → Executor 消费」模型不一致。Phase 2 引入 `monitor_tasks` 有界 worker 池，finalize 单入口，ContentObserve 只 enqueue。

**前置**：Monitor Daemon v3 Phase 1 已合并并手动验收 O1/O2/O6。

**参考**

- 设计 spec §6.3、§8 Phase 2：[2026-06-05-monitor-daemon-observe-execute-design.md](../superpowers/specs/2026-06-05-monitor-daemon-observe-execute-design.md)
- 计划 Phase 2 纲要：[2026-06-05-monitor-daemon-v3.md](../superpowers/plans/2026-06-05-monitor-daemon-v3.md) Task P2-1–P2-5

## 验收标准

### P2-1 — `monitor_tasks` + `MonitorTaskRepo`

- [ ] 迁移 SQL：`monitor_tasks` 表 + `idx_monitor_tasks_status_prio` + `idx_monitor_tasks_dedupe_active`（pending/running 部分 UNIQUE）
- [ ] Repo：`enqueue` / `claim_pending` / `mark_done` / `mark_failed` / `reset_stale_running`
- [ ] worker 独立 `open_db()`（D1）
- [ ] `tests/unit/test_monitor_task_repo.py`

### P2-2 — `MonitorExecutor`

- [ ] `monitor_executor.py`：有界 ThreadPoolExecutor，镜像 `PostProcessExecutor`
- [ ] `monitor.executor_max_parallel` 默认 **1**；`config.example.yaml` 注释 Playwright OOM 风险
- [ ] Playwright 类 job 模块级 `Semaphore(1)`

### P2-3 — ContentObserve 只 enqueue

- [ ] `MonitorWatcher._run_pipeline_tick`：检测新 aweme/archive/dynamic → `enqueue(sync_catalog|download|…)`，不内联长任务
- [ ] SlowTick 间隔不变，单次 tick 阻塞时间缩短（G5）

### P2-4 — finalize 单入口

- [ ] `poll_active`：**禁止**直接 `_finalize_recording`；offline 满 `offline_confirm_sec` 后 `enqueue(finalize:{session_id})`
- [ ] LiveTick tick 末：`drain_priority_zero()` 同 tick 消费 finalize/start（保 G4/G1）
- [ ] 集成测：mock offline 时间线 → 仅一条 finalize 任务执行

### P2-5 — CLI 可观测

- [ ] `media2text live status --json` 含 `monitor_tasks: { pending, running, failed }`
- [ ] `tests/unit/test_live_status_cli.py` 扩展断言

## 验证命令

```bash
pytest tests/unit/test_monitor_task_repo.py tests/unit/test_live_scheduler.py \
  tests/unit/test_live_status_cli.py -v
media2text live status --json
```

## 非目标范围

- Phase 1 outbox / observe 拆分（已完成）
- `post_process_jobs` 与 `monitor_tasks` 合并
- Phase 3：公平性、DLQ、Desktop 队列 UI
- 多机 / Redis

## 依赖与顺序

- **依赖**：Phase 1 Issue 已关闭
- **建议**：2–3 个独立 PR，不与 Phase 1 混发

## 实现备注

- GitHub Issue: （Phase 1 完成后开单）
- 分支：`issue-<N>-monitor-daemon-v3-phase2`
