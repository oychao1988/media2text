---
epic: monitor-live-simplify-2026-07-06
github: TBD
branch: issue-TBD-mls1-dead-code-reconciler
depends_on: []
---

# MLS-1：死代码 + reconciler_log_only 清理

Epic：**Monitor / Live 架构精简**（2026-07-06）  
规格：[2026-07-06-monitor-live-simplify-refactor-design.md](../superpowers/specs/2026-07-06-monitor-live-simplify-refactor-design.md) §3 Phase 1（P1-1,2,3,6,7）

## 背景

Eng Review 2026-07-06 锁定 D10：删除 rollout 阴影模式与无调用方代码，保持 daemon `reconciler_enabled` 硬要求，单测不依赖 `reconciler_enabled=false`。

## 验收标准

- [ ] 删除 `run_poll_active_tick`（`probe.py`，无调用方）
- [ ] 删除 `probe._run_live_probe_tick_legacy` 及 `conn=` 废弃路径（单测改走 gateway mock）
- [ ] 删除 `reconciler_log_only` 配置字段与 `task_scheduler` 分支
- [ ] 删除 `offline_confirm_polls` 配置字段（逻辑已用 `offline_confirm_sec`）
- [ ] 删除 `clear_snapshot_write_lock_for_tests` no-op
- [ ] `reconciler_enabled=false` 的 notify drain 等单测改为 mock，不依赖关闭 reconciler
- [ ] `config.example.yaml` 注释更新（无 `reconciler_log_only`）

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_task_scheduler.py tests/unit/test_monitor_daemon_integration.py tests/unit/test_notify_daemon_drain.py tests/unit/test_probe_guard.py tests/unit/test_monitor_watcher.py -v
ruff check src/media2text/core/live/probe.py src/media2text/core/live/task_scheduler.py src/media2text/core/config.py
pyright src/media2text/core/live/task_scheduler.py
```

## 非目标范围

- 禁止新 legacy session（MLS-2）
- 删 Node sidecar（MLS-3）
- 删 `reconciler_enabled` 配置字段本身（推迟 P2）
