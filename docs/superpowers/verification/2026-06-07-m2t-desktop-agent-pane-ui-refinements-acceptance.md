# m2t-desktop Agent Pane UI 细化 — Epic 验收

**日期:** 2026-06-07  
**规格:** [2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md) §11 A1–A10  
**原型:** [finalized.html](../designs/m2t-desktop/finalized.html)

## 总 verdict

| 类别 | 结论 |
|------|------|
| **Issue #199–#204** | 代码已实现于 `issue-199-agent-accio-messages` 分支（待分 PR 合并） |
| **Vitest** | `pnpm --filter m2t-desktop test` — **117/117 PASS** |
| **spec A1–A10** | 自动化覆盖见下表；Tauri 手工项待 `pnpm --filter m2t-desktop tauri dev` 复验 |

**Epic 签署建议:** 自动化闸门 **PASS**；合并前 issue-reviewer + Tauri 手工 A3/A7/A8/A9 复验。

---

## 自动化证据

| ID | 项 | 证据 |
|----|-----|------|
| A1 | Agent 历史分组 | `agentGroups.test.ts`、`AgentHistorySidebar.test.tsx` |
| A2 | 组头批量删除 | `AgentHistorySidebar.test.tsx` batch delete；`ConfirmDialog` + `Promise.allSettled` in `AgentPanel` |
| A3 | Draft 页签 | `useAgentTabs.test.ts`；`AgentChatEmpty.tsx`；首条 send 在 `AgentPanel.handleSend` |
| A4 | 页签头像 | `AgentTabsBar.test.tsx` global/creator abbr |
| A5 | 用户 Accio 气泡 | `chatMessages.test.tsx`、`agentPaneAcceptance.test.tsx` |
| A6 | 助手 process/footer | `chatMessages.test.tsx`、`agentPaneAcceptance.test.tsx` |
| A7 | Composer 单行 | `useAutoResizeTextarea.test.tsx` mount 无 inline height |
| A8 | Composer 滚动条 | CSS `.agent-composer-input` scrollbar 规则（layout.css） |
| A9 | transcript-chat 拖右栏 | 既有 `transcriptChatLayout.test.ts` + grid `minmax(280px, var(--right-w))` |
| A10 | chat-only 居中 | CSS `minmax(0, 1fr)` + `.agent-main` max-width；`agentPaneAcceptance` toast |

---

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
media2text serve --port 8765
open docs/superpowers/designs/m2t-desktop/finalized.html
```

## 手工待办（Tauri）

- [ ] A3：`+` 无 POST；选博主后首条发送建 thread + turn
- [ ] A7/A8：打开面板初始单行；粘贴长文 10 行后滚动条
- [ ] A9：`transcript-chat` 拖 `#resize-right`
- [ ] A10：`chat-only` 对话列居中 ≤720px
