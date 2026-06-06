# m2t-desktop Agent Pane PR4：多 Tab + 全局历史侧栏（A1–A10, D3）

## 背景

Cursor 风格 Agent 区：最多 5 个 Tab、左侧全局线程历史（`GET /api/chat/threads` 不过滤 creator）、creator 不匹配 toast +「切换到该博主」（D3）。移除 `.agent-header` / model-pill。

**参考**

- 计划 Task 10–12：[2026-06-06-m2t-desktop-agent-pane.md](../superpowers/plans/2026-06-06-m2t-desktop-agent-pane.md)
- **依赖 PR2**（context.refresh paths）+ **PR3**（布局/agentHistoryW）

## 验收标准

### Hooks（Task 10）

- [ ] `useAgentThreads`：全局列表、创建、删除 thread（`DELETE /api/chat/threads/{id}`）
- [ ] `useAgentTabs`：最多 5 tab，新开挤掉最左；关 tab **不** DELETE thread
- [ ] `useAgentTabs.test.ts` 覆盖 cap + close 语义

### UI（Task 11）

- [ ] `AgentTabsBar`、`AgentHistorySidebar`、`AgentThreadContextMenu`
- [ ] `useAgentHistoryResize` 拖拽 `--agent-history-w`；☰ 折叠 persist `m2t-agent-history-collapsed`
- [ ] 删除 thread 前 `window.confirm`
- [ ] `AgentPanel` 移除 `.agent-header` / model-pill

### 行为（Task 12, D3）

- [ ] `useM2tAgent({ threadId, creatorId, sessionContext })` 按 thread 隔离消息
- [ ] 激活他 creator 的 thread → toast + 可选「切换到该博主」
- [ ] 转写场次变更 → `PATCH /api/chat/threads/{id}` + `sendAgentContextRefresh`（含 paths）

### 测试

- [ ] `pnpm --filter m2t-desktop test`（agent hooks + mismatch toast mock）
- [ ] 建议 `/plan-design-review` 或手工对照 finalized.html

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 手工 A1–A10：多 tab、历史侧栏、跨 creator toast、删 thread 确认
media2text serve --port 8765  # sidecar 联调
```

## 非目标范围

- Tab 拖拽重排、刷新后恢复 open tabs
- 历史列表按 creator 过滤
- 附件/上下文按钮真实能力（仍 toast）
- P1 thread 搜索 API

## 实现备注

- 分支：`issue-173-agent-multi-thread-ui`
- GitHub Issue: [#173](https://github.com/oychao1988/media2text/issues/173)
- PR 正文 `Fixes #173`
