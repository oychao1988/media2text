# m2t-desktop Agent Pane UI 细化 PR2：历史按 Agent 分组 + 批量删除

## 背景

历史侧栏由 **时间分组**（`threadGroups.ts` today/yesterday/week）改为 **Agent 分组**（灵犀 + 各博主）；组头支持折叠与批量删除确认框；移除 `HistoryFilter`（全部/当前博主）。

**参考**

- 规格 §4、§14.2、§14.4、§11 A1–A2：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md)

**依赖**：无后端变更；可与 PR1 并行

## 验收标准

### 分组逻辑

- [x] `groupThreadsByAgent()` 替代时间分组；`agentId = thread.creator_id ?? 'global'`
- [x] 灵犀组固定首位；博主组顺序与 `GET /api/creators` / 左栏一致
- [x] **仅渲染 ≥1 thread 的组**；全局无分组时显示「暂无会话」（§14.2）
- [x] 会话项 `.agent-thread-item` 缩进 24px（`.agent-thread-group-sessions`）

### 侧栏 UI

- [x] `.agent-thread-group-head`：toggle（头像+名称+chevron）+ ⌫ 批量删除
- [x] 折叠状态 `agentGroupCollapsed[agentId]` persist（localStorage 或现有 history UI state）
- [x] **移除** `HistoryFilter` 及 `useAgentThreads.historyFilter`、侧栏两颗筛选按钮（§14.4）
- [x] 保留搜索 filter（title 客户端过滤）

### 批量删除

- [x] 共用 `ConfirmDialog`（`role="alertdialog"`；打开聚焦取消钮）
- [x] 确认后对组内 thread id **并行** `DELETE /api/agent/threads/{id}`（`Promise.allSettled`）
- [x] 成功：移除会话 + 关闭对应页签
- [x] 部分失败：toast「已删除 N 条，M 条失败」；失败项保留（§14.2）
- [x] 单条删除亦走同一 confirm 组件

### 测试

- [x] `agentGroups.test.ts`：分组、空组隐藏、global 首位、creator 顺序
- [x] 批量删 mock：`allSettled` 部分失败 toast

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
# 手工 A1/A2（需 sidecar + Tauri）：
# media2text serve --port 8765
# pnpm --filter m2t-desktop tauri dev
# 多博主 thread 分组；空库「暂无会话」；组头 ⌫ 确认后清除；模拟 409/5xx 部分失败
```

## 非目标范围

- Accio 消息组件（PR1）
- Draft 页签（PR3）
- 批量 DELETE API（API-2 P2；前端 loop 足够）
- 页签头像（PR4）

## 实现备注

- 分支：`issue-200-agent-history-groups`
- GitHub Issue: [#200](https://github.com/oychao1988/media2text/issues/200)
