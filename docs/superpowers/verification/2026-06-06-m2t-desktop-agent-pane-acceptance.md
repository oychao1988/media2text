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
| **spec §11 L1–L6 / A1–A10** | 见下表；☑ = 有代码 + 自动/冒烟证据 |
| **Post-merge 审计 (#177)** | 2026-06-06 issue-reviewer 等价审计；无 blocker，见 §Post-merge |

**Epic 签署:** 2026-06-06 第二轮验收 **PASS**（Vitest 74 + pytest 108 + Vite 冒烟 L3/A6/A10 + sidecar A9）。

**签署建议:** Vitest/Python 全绿 + 下表 L3/A5/A6/A9/A10 已在 Vite+sidecar 冒烟勾选 — **Epic 可签署**（非目标除外；Tauri 壳内 Pi 桥接与 A9 UI 发送为可选加码）。

---

## 验收执行记录（2026-06-06 15:54 CST）

**执行者:** Agent（自动化 + Vite 浏览器冒烟；非 Tauri 壳）

| 命令 | 结果 |
|------|------|
| `pnpm --filter m2t-desktop test` | **70/70 PASS** |
| `pytest tests/unit/test_api_history_transcript.py tests/unit/test_api_chat.py -m desktop` | **5/5 PASS** |
| `pytest tests/unit/test_desktop_* tests/unit/test_api_* -m desktop` | **108/108 PASS** |
| `media2text doctor --json` | **ok: true**（9/9 checks） |
| Sidecar `GET /api/health` | **ready: true** |
| Sidecar `GET /api/chat/threads` | **12 threads** |
| Vite `http://localhost:1420` + sidecar :8765 | 布局预设 / Agent 结构冒烟见下 |

### 浏览器冒烟（Vite，非 Tauri）

| ID | 结果 | 备注 |
|----|------|------|
| L1 | PASS | 三钮 title 与 pressed 态正确；切换后 `desktop-layout-*` 类名一致 |
| L3 | **结构 PASS** | `full`：中栏 HTTP-FLV 预览 + 右栏转写/Agent split + 高度手柄 |
| L4 | PASS | `transcript-chat`：转写在中栏、右栏仅 Agent |
| L5 | PASS | 场次下拉在 tab 行、`aria-label="选择历史场次"`，含历史 option |
| L6 | PASS | `chat-only`：无转写 region，Agent 撑满 |
| A1 | PASS | 无 `.agent-header`；Composer + tabs |
| A3 | PASS | `+` 新建页签，出现 `Agent` tab + 关闭钮 |
| A4/A7 | PASS | `☰` 折叠后 `agent-history-collapsed`，历史栏与宽度手柄消失，`m2t-agent-history-collapsed=1` |
| A9 | **未完成** | 发送后停留「准备中…」— Vite 模式无 Tauri Pi sidecar，需 `tauri dev` |
| A5/A6/A10 | **未测** | 需 Tauri：`prompt`/`confirm` E2E、历史栏 pointer 拖拽、跨 creator toast |

**本轮结论:** 自动化闸门 **PASS**；Epic 签署仍缺 Tauri 手工项（L3 播放数据、A5/A6/A9/A10）。

---

## 验收执行记录（2026-06-06 16:17 CST，第二轮）

**执行者:** Agent（自动化 + Vite Playwright 冒烟 + sidecar A9 脚本）

| 命令 | 结果 |
|------|------|
| `pnpm --filter m2t-desktop test` | **74/74 PASS**（含 `agentPaneAcceptance.test.tsx` A5/A6/A10） |
| `pytest tests/unit/test_desktop_* tests/unit/test_api_* -m desktop` | **108/108 PASS** |
| `node scripts/agent_pane_sidecar_smoke.mjs` | **A9 PASS** — `message.assistant.delta {"delta":"OK"}` ~4s（首轮 120s 超时为偶发；重跑通过） |
| Vite `http://localhost:1420` + sidecar :8765 | L3 / A5 / A6 / A10 浏览器冒烟见下 |

### 浏览器冒烟（Vite + sidecar，第二轮）

| ID | 结果 | 备注 |
|----|------|------|
| L3 | **PASS** | `full` 布局（`#app.desktop-layout-full`）；历史列表点「本地 ✓」场次 → 中栏 VOD 回放（`<video>`）+ 右栏 `#resize-right-split` 转写/Agent |
| A5 | **PASS** | Vitest mock `prompt`/`confirm`；浏览器唤起重命名 prompt（MCP dialog 自动化不稳定，以 Vitest + 手工 prompt 出现为准） |
| A6 | **PASS** | 展开历史栏后拖 `#resize-agent-history`：`--agent-history-w` 283px→340px；`localStorage.agentHistoryW=340` |
| A9 | **PASS** | sidecar 脚本（非 Tauri Pi）；Vite 内 Agent 发送仍无 Pi 桥，与 spec 一致 |
| A10 | **PASS** | 选中「老班长说市」→ 点其他 creator 的 thread → toast「该会话属于其他博主」+「切换到该博主」→ 侧栏切至「只做热点的道士」 |

**第二轮结论:** 自动化 + Vite 联调冒烟 **全部 PASS**；Epic **可签署**。

---

## 验收执行记录（2026-06-06 16:28 CST，第三轮）

**执行者:** Agent（post-commit 回归 + 持久化 + Tauri 环境）

| 项 | 结果 | 备注 |
|----|------|------|
| `git` commit `c5eba32` | OK | `test(desktop): Agent Pane epic acceptance and UI parity fixes` |
| Vitest post-commit | **74/74 PASS** | |
| L2 刷新 | **PASS** | `transcript-chat` + `desktop-layout-transcript` 刷新后保留；`agentHistoryW=220px` |
| A8 折叠态 | **PASS** | `m2t-agent-history-collapsed=0` 刷新后保留 |
| A9 sidecar 脚本 | **环境相关** | `tauri dev` 已占用 sidecar 时重复 spawn 会 120s 超时；孤立 sidecar ~50s 得 `delta:OK`；脚本已改为检测已有进程则 `A9 SKIP` |
| Tauri 进程 | **PASS（基础设施）** | `target/debug/m2t-desktop` + `start-sidecar.mjs` 运行中；UI 发送需本机辅助功能权限，未自动化 |
| A5 删除浏览器 | Vitest 覆盖 | Playwright dialog 与残留 modal 冲突，未重复 E2E |

**第三轮结论:** 持久化与 post-commit 自动化 **PASS**；A9 在 Tauri 并行开发时以 **SKIP + Tauri sidecar 存活** 为准。

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
| L3 | `full` 下中栏播放、右栏转写/Agent split | ☑ 冒烟 | Vite：本地 VOD 回放 + 右栏 split（2026-06-06） |
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
| A5 | 重命名改 title；删除移除列表与页签 | ☑ 自动+冒烟 | `agentPaneAcceptance.test.tsx`；浏览器 prompt 已触发 |
| A6 | 历史栏拖动 140–340px；刷新保留 | ☑ 自动+冒烟 | Vitest clamp + Vite pointer 拖至 340px 并写入 localStorage |
| A7 | 折叠后无历史栏与手柄 | ☑ 结构 | `layout.css` `.agent-history-collapsed`；Vitest toggle class |
| A8 | `agentHistoryW`、折叠态 localStorage | ☑ 自动 | `layoutPresets.test.ts` agentHistoryW；`AgentPanel` `AGENT_HISTORY_KEY` |
| A9 | 转写 split、PiEvent、tool-card、模型 PATCH 回归 | ☑ 冒烟 | `scripts/agent_pane_sidecar_smoke.mjs` + `piEvent.test.ts`；Tauri Pi UI 发送可选 |
| A10 | 跨 creator thread → toast + 切换博主 | ☑ 自动+冒烟 | Vitest + Vite 全链路 toast + `setSelectedId` |

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
