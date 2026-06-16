# Monitor 自愈 SH-3：运维脚本与文档

GitHub Issue: [#315](https://github.com/oychao1988/media2text/issues/315)  
**Depends on:** [#313](https://github.com/oychao1988/media2text/issues/313)（SH-1 合并后；与 SH-2 可并行开发）  
规格：[2026-06-16-monitor-self-heal-design.md](../superpowers/specs/2026-06-16-monitor-self-heal-design.md)  
计划：[2026-06-16-monitor-self-heal-implementation.md](../superpowers/plans/2026-06-16-monitor-self-heal-implementation.md)（Task 9）  
系列：SH-1 → SH-2 → **SH-3**

## 背景

SH-1 提供 `clear_invalid_monitor_lock` Python API 后，运维入口 `bin/monitor-watch-daemon.sh` 仍用 `kill -0` 判活，与 core 同缺陷。本 Issue 对齐 **Layer 3（运维）** 并补充排错文档，完成 Epic 可运维闭环。

## 验收标准

### Task 9 — Shell + 文档

- [x] `bin/monitor-watch-daemon.sh` 启动前调用 Python `clear_invalid_monitor_lock(Path('data/.monitor-watch.lock'))`，替换 `kill -0` 假锁逻辑
- [x] `CLAUDE.md` 监控排错一节（3–5 行）：假锁症状、`daemon_lock_valid`、`POST /api/runtime/takeover`、`desktop.monitor_self_heal` 配置
- [x] `config.example.yaml` 含 `monitor_self_heal*` 四字段（若 SH-2 未合入则本 PR 一并补）
- [x] 规格 `2026-06-16-monitor-self-heal-design.md` 状态改为 **Implemented**（Epic 收尾）
- [x] `docs/superpowers/verification/2026-06-16-monitor-self-heal-acceptance.md` 验收表勾选

### 手动冒烟

- [ ] `echo 581 > data/.monitor-watch.lock` 后执行 `bin/monitor-watch-daemon.sh`：假锁被清或合法 monitor 启动
- [ ] `pgrep -fl 'monitor watch'` 可见 daemon（环境允许时）

## 验证命令

```bash
source .venv/bin/activate

pytest tests/unit/test_monitor_lock.py tests/unit/test_process_lock.py -v
python scripts/verify_monitor_watch_daemon_smoke.py
```

**手动冒烟**（勿纳入 CI / `issue_verify`）

```bash
echo 581 > data/.monitor-watch.lock
bin/monitor-watch-daemon.sh
cat data/.monitor-watch.lock   # 应为 JSON 或当前 monitor PID，非 581
pgrep -fl 'monitor watch'
```

## 非目标范围

- 新增 CLI 子命令（自愈仅 serve + health loop + 脚本）
- macOS LaunchAgent plist 模板
- CHANGELOG（由 SH-2 交付一句迁移说明）

## 依赖与顺序

- **依赖**：SH-1（`monitor_lock` 模块）；与 SH-2 无硬依赖，可并行
- **建议分支**：`issue-315-monitor-self-heal-sh3`
- **Epic 验收**：SH-1 + SH-2 + SH-3 合并后，更新 `docs/superpowers/specs/2026-06-16-monitor-self-heal-design.md` 状态；可选 `docs/superpowers/verification/` 验收表
