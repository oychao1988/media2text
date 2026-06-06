# m2t-desktop Agent Pane PR4：多 Tab + 全局历史侧栏（A1–A10, D3）

## 背景

Cursor 风格 Agent 区：最多 5 个 Tab、左侧全局线程历史（`GET /api/chat/threads` 不过滤 creator）、creator 不匹配 toast +「切换到该博主」（D3）。移除 `.agent-header` / model-pill。

**参考**

- 计划 Task 10–12：[2026-06-06-m2t-desktop-agent-pane.md](../superpowers/plans/2026-06-06-m2t-desktop-agent-pane.md)
- **依赖 PR2**（context.refresh paths）+ **PR3**（布局/agentHistoryW）
- Epic 验收：[2026-06-06-m2t-desktop-agent-pane-acceptance.md](../superpowers/verification/2026-06-06-m2t-desktop-agent-pane-acceptance.md)

## 验收标准

### Hooks（Task 10）

- [x] `useAgentThreads`：全局列表、创建、删除 thread（`DELETE /api/chat/threads/{id}`）
- [x] `useAgentTabs`：最多 5 tab，新开挤掉最左；关 tab **不** DELETE thread
- [x] `useAgentTabs.test.ts` 覆盖 cap + close 语义

### UI（Task 11）

- [x] `AgentTabsBar`、`AgentHistorySidebar`、`AgentThreadContextMenu`
- [x] `useAgentHistoryResize` 拖拽 `--agent-history-w`；☰ 折叠 persist `m2t-agent-history-collapsed`
- [x] 删除 thread 前 `window.confirm`
- [x] `AgentPanel` 移除 `.agent-header` / model-pill

### 行为（Task 12, D3）

- [x] `useM2tAgent({ threadId, creatorId, sessionContext })` 按 thread 隔离消息
- [x] 激活他 creator 的 thread → toast + 可选「切换到该博主」
- [x] 转写场次变更 → `PATCH /api/chat/threads/{id}` + `sendAgentContextRefresh`（含 paths）

### 测试

- [x] `pnpm --filter m2t-desktop test`（agent hooks + mismatch toast mock + 组件结构）
- [x] Epic 验收文档 §11.2 / Post-merge 审计（#177）；视觉 diff 见 acceptance 表「手工/N/A」

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 手工 A9/A10 全链路：sidecar 联调 + 跨 creator 切换
media2text serve --port 8765
```

## 非目标范围

- Tab 拖拽重排、刷新后恢复 open tabs
- 历史列表按 creator 过滤
- 附件/上下文按钮真实能力（仍 toast）
- P1 thread 搜索 API

## 实现备注

- 分支：`issue-173-agent-multi-thread-ui`
- GitHub Issue: [#173](https://github.com/oychao1988/media2text/issues/173)（已关闭）
- PR: [#177](https://github.com/oychao1988/media2text/pull/177)
