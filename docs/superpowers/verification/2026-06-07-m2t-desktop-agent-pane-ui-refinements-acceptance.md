# m2t-desktop Agent Pane UI 细化 — Epic 验收

**日期:** 2026-06-07  
**规格:** [2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md) §11 A1–A10  
**原型:** [finalized.html](../designs/m2t-desktop/finalized.html)

## 总 verdict

| 类别 | 结论 |
|------|------|
| **Issue #199–#204** | 已全部 squash 合并至 `main`（tip `673e9fd`，2026-06-07） |
| **Epic verify** | `python scripts/epic_verify.py agent-pane-ui-refinements` — **PASS** |
| **Vitest** | `pnpm --filter m2t-desktop test` — **117/117 PASS** |
| **Desktop pytest** | `pytest tests/unit/test_desktop_* tests/unit/test_api_* -m desktop` — **124 passed** |
| **Issue verify** | `issue_verify.py --issue 199..204` — 全部 exit 0 |
| **spec A1–A10** | A1–A8、A10 有自动化/静态证据；A3/A7–A10 需 Tauri 手工复验（见下） |

**Epic 签署建议:** 自动化闸门 **PASS**；Epic 可关单。Tauri 手工四项建议在本地 `tauri dev` 点验后勾选下方清单。

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
python scripts/epic_verify.py agent-pane-ui-refinements
pnpm --filter m2t-desktop test
pytest tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop
pnpm --filter m2t-desktop tauri dev
media2text serve --port 8765
open docs/superpowers/designs/m2t-desktop/finalized.html
```

**2026-06-07 自动化跑数记录:** `epic_verify` + Vitest + pytest + `issue_verify 199–204` 均在 `main` @ `673e9fd` 通过；sidecar `GET /api/health` 冒烟 OK。

## 手工待办（Tauri）

- [ ] A3：`+` 无 POST；选博主后首条发送建 thread + turn
- [ ] A7/A8：打开面板初始单行；粘贴长文 10 行后滚动条
- [ ] A9：`transcript-chat` 拖 `#resize-right`
- [ ] A10：`chat-only` 对话列居中 ≤720px
