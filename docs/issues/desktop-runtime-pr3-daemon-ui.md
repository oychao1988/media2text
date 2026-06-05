# Desktop Runtime PR3：Daemon 三态 UI + 可观测性文案

## 背景

PR2 接入 `RuntimeProvider` 与 WS 后，Daemon 面板仍缺少 **health 语义** 的可读展示：`failed 50` 为历史累计易误导；用户无法一眼看到「LiveTick 是否 stale」与当前录制数。本 Issue 落地 **PR3**：三态 health UI、`health_reasons`、`failed_recent_24h` 展示、日志区自动刷新。

**前置**：Desktop Runtime PR2 已合并（或 PR1+PR2 同分支联调完成 WS）。

**参考**

- 设计：[2026-06-05-desktop-runtime-design.md](../superpowers/specs/2026-06-05-desktop-runtime-design.md) §3.6 Health UI、§4 queues、§8 PR3
- 代码锚点：`DaemonCard.tsx`、`RuntimeProvider`

## 验收标准

### Task 1 — Health 三态 UI

- [ ] 状态点颜色：`healthy` 绿 / `degraded` 黄 / `stopped` 灰（spec §3.6 表）
- [ ] 标题文案：「监控正常 / 监控降级 / 监控未运行」
- [ ] `health_reasons[0]` 展示为首条副标题（如「LiveTick 45s 无心跳」）
- [ ] `managed_by: external` 时显示「外部 daemon」且禁用 embedded start（或提示只读）

### Task 2 — 队列与录制展示

- [ ] 展示 `recordings.active_count`（或 items 摘要）
- [ ] `monitor_tasks`：`running` / `pending` 当前值；**同时**展示 `failed_recent_24h` 与 `failed_total`（标注「24h / 累计」避免 scare）
- [ ] `post_process` pending/running 一行摘要
- [ ] `observability.snapshots_stale_count` > 0 时在 degraded 原因或独立 hint 展示

### Task 3 — 日志面板

- [ ] 日志展开时：`GET /api/runtime/logs?tail=N` 自动刷新（间隔可 10–15s，或 WS `runtime.log` 若 PR2 已预留则接入）
- [ ] 折叠时不 poll logs

### Task 4 — a11y / 测试

- [ ] Vitest：`DaemonCard` 渲染 healthy/degraded/stopped 快照
- [ ] 键盘/aria：状态点有 `aria-label` 含 health 文案

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test

# 可选：带 desktop marker 的后端回归
pytest tests/unit/test_runtime_status.py tests/unit/test_api_runtime.py -v -m desktop
```

**手动验收**

```bash
pnpm --filter m2t-desktop tauri dev
# 1. embedded 运行 → 绿点 + active_count
# 2. 模拟 stale tick（或停 LiveTick）→ 黄点 + reason
# 3. stop runtime → 灰点
# 4. failed_total=50 且 failed_recent_24h=2 时 UI 不显示裸「failed 50」
```

## 非目标范围

- 一键 bulk retry 50 条 failed（仅后续管理页）
- 改 health 计算逻辑（PR1 已定义；本 Issue 只 UI）
- post-process / pipeline API（→ PR4）
- 左侧四色灯语义变更

## 依赖与顺序

- **依赖**：Desktop Runtime PR1（`failed_recent_24h` 字段）；PR2 推荐（RuntimeProvider）
- **建议分支**：`issue-<N>-desktop-runtime-pr3`
- **可与 PR4 并行**（PR2 后）

## 实现备注

- GitHub Issue: [#160](https://github.com/oychao1988/media2text/issues/160)
- 分支：`issue-160-desktop-runtime-pr3`
