---
epic: agent-context-attachments
issue: 254
github: 254
branch: issue-254-agent-context-p0-creator-draft
depends_on: []
spec: docs/superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md
---

# m2t-desktop Agent 上下文 P0：左栏选博主 → Agent draft 联动

## 背景

产品决策 **D1**：用户点击左栏博主头像后，Agent 栏应 **自动聚焦该博主的新 draft 页签**（`agentId = creatorId`），而非仅影响 `defaultAgentId` 与 `+` 行为。

工程决策 **E4**：`AppShell` 通过 **`AgentPanel` ref** 调用 `openNewDraftForAgent(creatorId)`，不用全局 event bus。

**参考**

- 规格 §3、§0.4 E4：[2026-06-09-m2t-desktop-agent-context-attachments-design.md](../superpowers/specs/2026-06-09-m2t-desktop-agent-context-attachments-design.md)
- 前置 Agent Pane UI：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md) §14.1 draft 模型

**依赖**：#201（draft/thread 页签）已交付

## 验收标准

### `openNewDraftForAgent(agentId)`

- [x] 新增函数；**不得**直接复用 `openOrFocusDraftTab`（该函数会复用任意 lone draft 且不校验 `agentId`）
- [x] 若已存在 **同 `agentId`、kind=draft、无消息** 的页签 → 聚焦该页签，不重复创建
- [x] 否则 `createDraftTab(agentId)` 并聚焦；满 `MAX_AGENT_TABS`（5）→ 丢弃最左后追加
- [x] 同步空态 identity picker / placeholder / tab 头像
- [x] **不**关闭或切换已有 **thread** 页签

### AppShell 桥接

- [x] `AgentPanel` 经 `useImperativeHandle` 暴露 `openNewDraftForAgent`
- [x] `AppShell` 持有 `agentPanelRef`；`handleSelectCreator` 在 `setSelectedId` 之后调用 ref
- [x] 所有 `handleSelectCreator` 入口行为一致：`LeftRail`、 `CreatorList`、 `DaemonCard` / `DaemonMonitorMenu`

### 规格验收 A1–A5

- [x] **A1**：点博主 B → Agent 聚焦 B 的 draft，空态显示 B 身份
- [x] **A2**：B draft 首条发送 → `POST /api/agent/threads` 的 `creator_id = B`
- [x] **A3**：连点同一博主不无限增 tab（复用同 agent 空 draft）
- [x] **A4**：点 A 再点 B → 分别聚焦 A/B draft（或各一 empty draft）
- [x] **A5**：聚焦 thread 页签时左栏切换博主 → thread 不变；仍可有 mismatch toast

### 测试

- [x] `useAgentTabs.test.ts`：`openNewDraftForAgent` 聚焦/创建/复用/cap 5
- [x] `AgentPanel` / `AppShell` 集成 mock：选博主触发 ref 调用

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
# 可选 Vitest 子集：
pnpm --filter m2t-desktop exec vitest run src/features/agent/useAgentTabs.test.ts
# 手工（需 sidecar + Tauri）：
# media2text serve --port 8765
# pnpm --filter m2t-desktop tauri dev
# 点左栏博主 → Agent 出现对应 draft；连点同博主不堆 tab
```

## 非目标范围

- attachment chips、`@` popover、`contextMode`（P1 / P1b / P2）
- `PATCH /api/agent/threads/.../activate` 扩展
- 修改 `openOrFocusDraftTab` 对外语义（仅新增 `openNewDraftForAgent`）
- 页签拖拽排序

## 依赖与顺序

- **依赖**：Agent Pane UI 细化 #201 已合并
- **阻塞**：无（P1 可并行，但建议先合并本单以便联调左栏联动）

## 实现备注

- 分支：`issue-254-agent-context-p0-creator-draft`
- GitHub Issue: [#254](https://github.com/oychao1988/media2text/issues/254)
