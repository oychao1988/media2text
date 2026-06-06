# m2t-desktop Agent Pane + 布局预设 — Epic 验收

**日期:** 2026-06-06  
**基线:** `main` @ #177 合并后（#174–#177）  
**规格:** [agent-pane-design](../specs/2026-06-06-m2t-desktop-agent-pane-design.md) §11 · 计划：[agent-pane-plan](../plans/2026-06-06-m2t-desktop-agent-pane.md)

## 总 verdict

| 类别 | 结论 |
|------|------|
| **Issue PR #174–#177** | 已合并；`docs/issues/README.md` 已链 PR |
| **自动化（Vitest）** | `pnpm --filter m2t-desktop test` — layout + agent hooks/组件 |
| **自动化（Python）** | `pytest tests/unit/test_api_history_transcript.py tests/unit/test_api_chat.py -v -m desktop`（PR1/2 范围） |
| **spec §11 L1–L6 / A1–A10** | 见下表；☑ = 有代码 + 自动/结构证据；☐ 手工 = 需 Tauri 冒烟 |
| **Post-merge 审计 (#177)** | 2026-06-06 issue-reviewer 等价审计；无 blocker，见 §Post-merge |

**签署建议:** Vitest/Python 全绿 + 下表「手工」项在 Tauri 冒烟勾选后，可宣称 Epic 交付（非目标除外）。

---

## 自动化命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pytest tests/unit/test_api_history_transcript.py tests/unit/test_api_chat.py -v -m desktop
pnpm --filter m2t-desktop tauri dev   # 手工 L/A 冒烟
media2text serve --port 8765          # sidecar 联调
```

---

## §11.1 桌面分区（L）— 主要在 #172 / #176

| ID | 通过条件 | 状态 | 证据 |
|----|----------|------|------|
| L1 | 三钮切换后可见分区与 §2.1 表一致 | ☑ 结构 | `DesktopLayoutPresets.tsx` + `AppShell.tsx` 条件渲染；`uiParity.test.tsx` preset 类名 |
| L2 | 选中钮 active；刷新后 `desktopLayoutPreset` 保留 | ☑ 自动 | `layoutPresets.test.ts` localStorage 往返 |
| L3 | `full` 下中栏播放、右栏转写/Agent split | ☐ 手工 | 需 Tauri + 录制/回放数据 |
| L4 | `transcript-chat` 转写在中栏、右栏仅 Agent | ☑ 结构 | `AppShell` `isTranscriptChat`；Vitest preset 类 |
| L5 | 场次下拉 + history 路由（非 vod session API） | ☑ 自动+结构 | `transcriptSelection.test.ts`；`TranscriptPane` history 路径 |
| L6 | `chat-only` 隐藏转写与折叠右栏；Agent 撑满 | ☑ 结构 | `AppShell` `isChatOnly`；`layout.css` `.desktop-layout-chat-only` |

---

## §11.2 Agent 区块（A）— 主要在 #173 / #177

| ID | 通过条件 | 状态 | 证据 |
|----|----------|------|------|
| A1 | 历史栏在右；对话区无顶栏；Composer 正常 | ☑ 结构 | `AgentPanel` 无 `.agent-header`；`AgentTabsBar` + `AgentComposer`；`agentPaneStructure.test.tsx` |
| A2 | 最多 5 页签；切换不重排；悬停 `×`；关闭不关 thread | ☑ 自动 | `useAgentTabs.test.ts`；`AgentTabsBar.test.tsx` close 按钮 |
| A3 | `+` 新建；满 5 挤掉最左 | ☑ 自动 | `useAgentTabs.test.ts` cap；`#btn-agent-new` |
| A4 | 搜索过滤；四组时间标签；`☰` 折叠/展开 | ☑ 自动+结构 | `threadGroups.test.ts`；`AgentHistorySidebar.test.tsx`；折叠 key `m2t-agent-history-collapsed` |
| A5 | 重命名改 title；删除移除列表与页签 | ☑ 结构 | `useAgentThreads` PATCH/DELETE；`window.confirm` in `AgentPanel`；☐ 删改 E2E 手工 |
| A6 | 历史栏拖动 140–340px；刷新保留 | ☑ 半自动 | `SIZE_LIMITS.agentHistory` + `commitLayoutSizes`；`agentHistoryResize.test.ts` clamp；☐ 拖拽手感手工 |
| A7 | 折叠后无历史栏与手柄 | ☑ 结构 | `layout.css` `.agent-history-collapsed`；Vitest toggle class |
| A8 | `agentHistoryW`、折叠态 localStorage | ☑ 自动 | `layoutPresets.test.ts` agentHistoryW；`AgentPanel` `AGENT_HISTORY_KEY` |
| A9 | 转写 split、PiEvent、tool-card、模型 PATCH 回归 | ☐ 手工 | 既有 Agent 路径未在本 Epic 改坏；需 sidecar + LLM 冒烟 |
| A10 | 跨 creator thread → toast + 切换博主 | ☑ 自动 | `agentThreadSelect.test.ts`；`showToastWithAction` in `AgentPanel`；☐ 全链路 Tauri 手工 |

---

## Issue 工单勾选（retro）

| Issue | docs/issues 文件 | reviewer 结论 |
|-------|------------------|---------------|
| #170 | [pr1-history-api.md](../../issues/m2t-desktop-agent-pane-pr1-history-api.md) | 已合并 #174；pytest history API |
| #171 | [pr2-sidecar-context.md](../../issues/m2t-desktop-agent-pane-pr2-sidecar-context.md) | 已合并 #175；`agentSidecar.test.ts` |
| #172 | [pr3-layout-presets.md](../../issues/m2t-desktop-agent-pane-pr3-layout-presets.md) | 已合并 #176；layout Vitest |
| #173 | [pr4-agent-ui.md](../../issues/m2t-desktop-agent-pane-pr4-agent-ui.md) | 已合并 #177；本表 A* + agent tests |

---

## Post-merge 审计（#177，2026-06-06）

**范围:** PR #177 diff vs `docs/issues/m2t-desktop-agent-pane-pr4-agent-ui.md` + spec §11.2 + §12 非目标。

### PASS（实现存在且与 AC 一致）

- `useAgentThreads` / `useAgentTabs` / 三组件 / `useAgentHistoryResize` / D3 toast
- `useM2tAgent({ threadId, creatorId, sessionContext })` + PATCH session + `sendAgentContextRefresh`
- 关 tab ≠ DELETE；删 thread 有 confirm
- 无 `.agent-header` / model-pill 于 `AgentPanel`（Composer 内模型选择保留，符合 Cursor 风格）

### 非阻塞 gap（follow-up 或手工验收）

| 项 | 说明 | 建议 |
|----|------|------|
| A6 拖拽 E2E | clamp 已测，无 pointer 集成测 | Tauri 冒烟拖历史栏；或 Playwright |
| A5 删改 UI | API 与 confirm 有，无 RTL 覆盖 rename prompt | 可选 Vitest mock `window.prompt` |
| A9 回归 | 未在本 PR 增测 PiEvent 全链路 | `tauri dev` + 发一条 Agent 消息 |
| A10 全链路 | unit 测 mismatch；未测 `setSelectedId` 后上下文 | 手工跨 creator 点历史 |
| finalized.html 视觉 | 未跑 `/design-review` 截图 diff | 需要时 gstack design-review |
| legacy CSS | `layout.css` 仍含未用 `.agent-header` 规则 | 清理 follow-up |

### Blockers

无（Epic 范围内）。

---

## 非目标（本 Epic 不验）

- Tab 拖拽、open tabs 持久化、历史按 creator 筛选、附件真实能力、P1 thread 搜索 API（spec §12）
