# m2t-desktop — Agent 面板 UI 细化（Accio 式消息 + 布局修复）

**日期:** 2026-06-07  
**状态:** 已批准（原型已落地于 `finalized.html`，待同步 React）  
**前置:** [Agent 区块与桌面分区布局](./2026-06-06-m2t-desktop-agent-pane-design.md)、[UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md)  
**原型真源:** [finalized.html](../designs/m2t-desktop/finalized.html)  
**本文性质:** 对 `2026-06-06` Agent 面板规格的 **增量修订**；冲突处以本文 + 原型为准。

---

## 0. 背景与范围

### 0.1 动机

在 `2026-06-06` Agent 面板骨架（页签 + 历史栏 + 三分区预设）之上，本轮对话完成三类细化：

1. **历史与会话模型** — 由「按时间分组」改为「按 Agent 身份分组」（全局 **灵犀** + 各博主）。
2. **消息流视觉** — 参照 Accio / Cursor Agent 面板：用户右对齐气泡、助手全宽正文、悬停操作区。
3. **布局与 Composer** — 修复三栏列宽拖动、两栏对话区居中、输入框单行起增与滚动条样式。

### 0.2 范围

| 在范围内 | 不在范围内 |
|----------|------------|
| Agent pane 内 HTML/CSS/原型 JS | Hermes / sidecar 协议变更 |
| 三分区 grid 列宽与 `chat-only` 居中 | 页签拖拽排序 |
| 空会话身份选择 UI | 附件 / 上下文按钮真实能力 |
| 批量删除确认框（原型） | 点赞/点踩后端持久化 |
| Composer 高度与滚动条 | 消息重试/编辑真实逻辑 |
| 移除 HistoryFilter（§14.4） | API-1 先 POST 后改绑 creator |

---

## 1. 相对 `2026-06-06` 的已锁定决策（修订）

| 项 | 旧（2026-06-06） | **新（本文）** |
|----|------------------|----------------|
| 历史列表分组 | 按时间：`today` / `yesterday` / `week` / `month` | **按 Agent：** `global`（灵犀）+ 各 `creator_id` |
| 全局 Agent 显示名 | （未单独定义） | **灵犀**（`agentId: 'global'`） |
| 新建空会话 | 直接进 Composer | **空态居中身份条** + 下拉选 Agent（灵犀优先，再博主） |
| 历史批量删除 | 单条删除（建议确认框） | 分组头 **⌫** → **确认对话框** 后删除该 Agent 下全部 thread |
| 用户消息对齐 | 未规定 | **右对齐**，`max-width: 520px` |
| 助手消息布局 | 气泡式（沿用旧 chat） | **无气泡全宽** + 处理过程行 + 底栏常驻操作 |
| 页签 | 仅标题 | 标题前加 **Agent 头像**（`.agent-tab-avatar`） |
| `transcript-chat` 右列宽 | `minmax(280px, 1fr)` | `minmax(280px, var(--right-w))`，`#resize-right` 有效 |
| `chat-only` 右列宽 | `minmax(280px, 1fr)` 填满 | 右栏仍 **1fr 占满**；**对话列居中**，`max-width: min(720px, 50vw)`；**无** `#resize-right` |
| Composer 高度 | 未规定 | 默认 **1 行**，随输入增至 **最多 10 行** |
| Composer 滚动条 | 系统默认 | **悬停/聚焦时** 显示 5px 细滚动条 |
| 历史栏筛选 | 「全部 / 当前博主」 | **移除**；仅搜索 + Agent 分组（§14.4） |
| 空会话建 thread | `+` 立即 `POST /threads` | **延迟建 thread**：draft 页签 + 首条发送再 POST（§14.1） |

---

## 2. Agent 身份模型

### 2.1 Profile

```ts
type AgentProfile = {
  id: string;           // 'global' | API creator_id（非 sec_uid）
  name: string;         // '灵犀' | 博主 display_name
  abbr: string;         // 头像内 1–2 字
  tag?: string;         // '全局' | '博主'
  isGlobal?: boolean;
};
```

| `agentId` | 名称 | 视觉 |
|-----------|------|------|
| `global` | 灵犀 | 渐变圆头像（`.global`） |
| `<creator_id>` | 左栏博主 `data-name` | 纯色圆头像，取自 `GET /api/creators` |

- **React：** 全局常量 `AGENT_GLOBAL_PROFILE`；博主顺序取自 **creators 列表**（与左栏一致），不硬编码 mock 顺序。
- **原型：** `AGENT_GLOBAL_PROFILE` + `AGENT_CREATOR_ORDER`（mock 顺序）。

### 2.2 Thread 与 agentId（派生，非 API 字段）

API / `ThreadRow` 仅含 `creator_id: string | null`。UI **`agentId` 一律派生**，不持久化双字段：

```ts
function threadAgentId(thread: { creator_id: string | null }): string {
  return thread.creator_id ?? 'global';
}
```

**Draft 页签**（§14.1）与 API thread 分离：

```ts
type AgentTabEntry =
  | { kind: 'draft'; draftId: string; agentId: string }   // 未 POST，无 threadId
  | { kind: 'thread'; threadId: string };

function getEffectiveAgentId(
  activeTab: AgentTabEntry | null,
  draftAgentId: string | null,
): string {
  if (activeTab?.kind === 'draft') return activeTab.agentId;
  if (activeTab?.kind === 'thread') return threadAgentId(/* lookup */);
  return draftAgentId ?? 'global';
}
```

- Draft 页签 **无** `creator_id` / DB 记录；`isEmpty` 仅描述 draft 态 UI，**不**写入 API thread 模型。

---

## 3. 空会话态 `#agent-chat-empty`

**显示条件：** 当前激活页签为 **draft**（`AgentTabEntry.kind === 'draft'`），或等价原型态 `isEmpty === true`。

**结构：**

```
#agent-chat-empty
  └── .agent-identity-bar
        ├── .agent-identity-logo (#agent-identity-logo)
        └── .agent-identity-picker-wrap
              ├── #agent-identity-picker（名称 + ▾）
              └── #agent-identity-menu（listbox，灵犀置顶）
```

| 行为 | 说明 |
|------|------|
| 垂直居中 | `.agent-chat-empty` 在 `#chat-scroll` 内 flex 居中 |
| 选 Agent | 更新 `draftAgentId`；同步 logo / 名称 / placeholder |
| placeholder | 全局：`输入问题… (@ 引用文件)`；博主：`向「{name}」Agent 提问…` |
| 首条发送 | `POST /threads`（灵犀 omit `creatorId`）；再 `POST .../turn`；draft 页签 **晋升** 为 thread 页签；隐藏 empty |
| 关闭 draft 页签 | 无 API 调用；丢弃 `draftAgentId` |

**与消息区互斥：** `#chat-live` / `#chat-playback` 在 empty 显示时 `hidden`。

---

## 4. 历史会话列表（按 Agent 分组）

### 4.1 分组结构

替换原 §4.1「时间分组」。每个分组 `.agent-thread-group`：

```
.agent-thread-group-head
  ├── .agent-thread-group-toggle（头像 + 名称 + chevron）
  └── .agent-thread-group-actions
        └── .agent-thread-group-action（⌫ 批量删除）
.agent-thread-group-sessions（padding-left: 24px）
  └── .agent-thread-item × N
```

| 分组 ID | 标题 | 排序 / 可见性 |
|---------|------|----------------|
| `global` | 灵犀 | 固定首位；**仅当该组 ≥1 条 thread 时渲染**（§14.2） |
| `creator_id` | 博主名 | creators 列表顺序；**仅当该组 ≥1 条 thread 时渲染** |

**空列表：** 无任何分组时，历史区显示「暂无会话」占位（非空白侧栏）。

### 4.2 分组交互

| 操作 | 行为 |
|------|------|
| 点击组头 toggle | 折叠/展开 `.agent-thread-group-sessions`；状态 `agentGroupCollapsed[agentId]` |
| 点击 ⌫ | `openAgentConfirm` → 对该组 thread id **并行** `DELETE`；成功后移除组内会话与对应页签 |
| 点击 ⌫ 部分失败 | 已删条目从列表移除；失败 id 保留；toast「已删除 N 条，M 条失败」；不关闭对话框直至用户确认（§14.2 注） |
| 点击会话项 | 同原 spec：选中、开页签、creator 不一致 toast |

### 4.3 确认对话框 `#agent-confirm-backdrop`

| 元素 | 说明 |
|------|------|
| `role="alertdialog"` | 标题 `#agent-confirm-title`、正文 `#agent-confirm-message` |
| 取消 / 删除 | `#agent-confirm-cancel`、`#agent-confirm-ok.danger` |
| 焦点 | 打开时聚焦取消钮 |

实现期：单条删除与批量删除均建议走同一 confirm 组件。

---

## 5. 消息流 UI（Accio 风格）

### 5.1 容器

- `#chat-live`、`#chat-playback`：`display: flex; flex-direction: column; gap: 20px; width: 100%`。
- 用户消息靠右需父级 flex 列 + `.chat-msg-user { margin-left: auto }`（不可仅靠 `align-self` 于 `.chat-scroll` 直接子级）。

### 5.2 用户消息 `.chat-msg-user`

| 部分 | 规格 |
|------|------|
| 对齐 | `margin-left: auto`；`max-width: 520px` |
| 头部 `.chat-msg-head` | 右对齐：**时间 · 名称 · 头像**（`order` 1/2/3） |
| 正文 | `.chat-msg-bubble` 灰底圆角气泡 |
| 悬停 | `.chat-msg-time` 显示；`.chat-msg-actions` 显示 |
| 操作 | 重试（文+图标）、编辑、复制 — 原型 Toast |

### 5.3 助手消息 `.chat-msg-agent`

| 部分 | 规格 |
|------|------|
| 宽度 | `align-self: stretch; width: 100%`（无气泡容器） |
| 头部 | 左对齐：**头像 · 名称 · 时间** |
| 处理行 | `.chat-msg-process`：见 §5.3.1 |
| 正文 | `.chat-msg-body` 全宽 Markdown 样式（`p` / `code` / `ol`） |
| 悬停 | 仅 `.chat-msg-time` 淡入 |
| 底栏 | `.chat-msg-footer` **常驻**：复制、点赞、点踩（图标按钮） |

### 5.3.1 处理过程行 `.chat-msg-process`（§14.3 已锁定）

| 阶段 | 行文案 | `›` / 展开 |
|------|--------|------------|
| **Turn 进行中** | WS `turn.phase` → `phaseLabel`（如「思考中…」） | 不可展开；隐藏 `›` 或置灰 |
| **Turn 已完成** | 「已处理 {duration_s} 秒」（来自 `duration_ms`） | 默认 **折叠** |
| **折叠** | 仅摘要行 | `›` 向右（collapsed） |
| **展开** | 摘要行下方 `.chat-msg-process-body` 展示 `thinking_text`（Markdown 轻量样式） | 点击行或 `›` 切换；`›` 向下（expanded） |
| **无 thinking** | 仅摘要行 | 隐藏 `›`，不可展开 |

- 流式过程中 **不** 逐字展开 `thinking_text`；完成后一次性可读。
- `aria-expanded` 绑在 `.chat-msg-process` button 上。

### 5.4 Tool 卡片

保留 `.tool-card` 嵌于助手消息流（与旧 chat 兼容）。

---

## 6. 页签栏增强

在 `2026-06-06` §3.3 基础上：

| 新增 | 说明 |
|------|------|
| `.agent-tab-avatar` | 18px 圆头像，文案为 `profile.abbr` |
| `.agent-tab-avatar.global` | 与灵犀渐变一致 |
| 布局 | `.agent-tab` 内 `[avatar][label]`，`gap: 6px` |

`renderAgentTabs()` 通过 `getAgentProfile(threadAgentId(thread))` 渲染；draft 页签用 `draft.agentId`。

---

## 7. Composer 输入框

### 7.1 尺寸行为

| 项 | 值 |
|----|-----|
| 默认 | 1 行（`min-height: calc(13px * 1.45 + 14px)`） |
| 最大 | 10 行（`max-height: calc(13px * 1.45 * 10 + 14px)`） |
| 增长 | CSS `field-sizing: content`；JS `syncAgentInputHeight` 仅在 `input` 事件 |
| 禁止 | **页面加载时** 不得调用 `syncAgentInputHeight`（避免空内容 `scrollHeight` 撑满 10 行 ≈ 203px） |

**不支持 `field-sizing` 时的 JS 回退：**

- 空内容：清除 `style.height`
- 有内容：`height: 1px` → 读 `scrollHeight` → clamp 到 min/max

### 7.2 滚动条（超过 10 行）

| 状态 | 表现 |
|------|------|
| 默认 | thumb **透明**（Firefox：`scrollbar-color: transparent transparent`） |
| `.agent-composer:hover` 或 input `:focus` | 显示 **5px** 圆角细滚动条 |
| 浅色主题 thumb | `rgba(0,0,0,0.14)`，hover `0.28` |
| 深色主题 thumb | `rgba(255,255,255,0.18)`，hover `0.32` |
| track | 透明，`margin: 6px 0` |

发送后：`input.value = ''` + `syncAgentInputHeight` 收回单行。

---

## 8. 桌面分区布局（修订）

### 8.1 Grid 列定义（右栏未折叠）

| 预设 | `grid-template-columns` |
|------|-------------------------|
| `full` | 不变（见 `2026-06-06` §2.1） |
| `transcript-chat` | `sidebar \| grip \| minmax(280px, 1fr) \| grip \| minmax(280px, var(--right-w))` |
| `chat-only` | `sidebar \| grip \| 0 \| 0 \| minmax(0, 1fr)` |

左栏折叠时：`0px` 替代对应 `grip` 列（与原型一致）。

### 8.2 `transcript-chat` 列宽拖动

| 手柄 | 作用 |
|------|------|
| `#resize-right` | 调整 `--right-w`；左拖加宽 Agent 列、右拖加宽转写列 |
| `#resize-right-split` | **隐藏**（转写已在中栏，右栏仅 Agent） |

`getRightWidthLimits()`：非 `chat-only` 时 reserve `center.min`；右栏上限仍为视口 50% 与 `SIZE_LIMITS.right.max` 的较小值。

### 8.3 `chat-only` 对话列居中

| 项 | 规格 |
|----|------|
| `#resize-right` | `display: none`；**不可**拖边界改宽 |
| 右栏 | 占满剩余 `1fr` |
| 对话列 | `.agent-main { max-width: min(720px, 50vw); margin-inline: auto; width: 100% }` |
| 范围 | 含 `#chat-scroll` + `.agent-composer-wrap`（页签栏仍全宽） |
| `#collapse-right` | 隐藏（切换入该 mode 时若已折叠则展开，同旧 spec） |

**React 迁移注记：** 当前 `apps/m2t-desktop/src/styles/layout.css` 仍为 `minmax(280px, 1fr)` 且 `.agent-main` 无居中约束；实现 Issue 5 须改为本文 grid + `.agent-main` 规则。

### 8.4 持久化

`m2t-desktop-layout` 仍存 `desktopLayoutPreset`、`rightW` 等；`chat-only` **不**再依赖 `--right-w` 控制可见宽度（仅 `transcript-chat` / `full` 使用）。

---

## 9. 前端状态补充

```ts
type AgentHistoryUI = {
  historyCollapsed: boolean;
  historySearch: string;
  agentGroupCollapsed: Record<string, boolean>;  // 替代 weekExpanded
  contextMenuThreadId: string | null;
  draftAgentId: string | null;                 // draft 页签内 identity picker 所选 Agent
  tabEntries: AgentTabEntry[];                 // §2.2；含 draft + thread
  activeTabId: string | null;                  // draftId 或 threadId
};
```

---

## 10. React 实现注意事项

| 话题 | 建议 |
|------|------|
| 历史分组 | `groupThreadsByAgent()` 替代时间分组；**仅渲染有 thread 的组**（§14.2）；移除 `HistoryFilter` |
| 空会话 | `+` → `pushAgentTab({ kind: 'draft', agentId: 'global' })`；首条 send 时 `POST /threads` 再 turn |
| 页签 | `useAgentTabs` 扩展 `AgentTabEntry`；draft 关闭不触 API |
| 消息组件 | 拆 `ChatMessageUser` / `ChatMessageAgent` + `ChatMessageProcess`（§5.3.1） |
| `chat-only` 居中 | `.agent-main { max-width: min(720px, 50vw); margin-inline: auto }`；grid 末列 `minmax(0, 1fr)` |
| `transcript-chat` 列宽 | `useColumnResize` + `--right-w` 已就绪；核对与 §8.1 一致 |
| Composer | `field-sizing: content`；**mount 且 value 为空时不写 height**（对齐 §7.1） |
| 确认框 | 共用 `ConfirmDialog`；批量删 `Promise.allSettled` + 部分失败 toast |

---

## 11. 验收要点（原型 / React）

| ID | 场景 | 预期 |
|----|------|------|
| A1 | 历史栏 | 按 **灵犀 + 博主** 分组（**仅有会话的组**）；无「全部/当前博主」筛选；组可折叠；会话项缩进 24px |
| A2 | 组头 ⌫ | 弹出确认框；确认后该组会话与相关页签清除；部分失败时 toast 且保留未删项 |
| A3 | 新建 `+` | 开 **draft 页签**（无 POST）；空态身份条；默认灵犀；首条发送才建 thread |
| A4 | 页签 | 显示 Agent 小头像 + 标题 |
| A5 | 用户消息 | 右对齐、灰气泡；悬停显示时间与操作 |
| A6 | 助手消息 | 全宽正文；完成后处理行可展开 `thinking_text`；进行中显示 phase；底栏复制/赞/踩常驻 |
| A7 | Composer 初始 | **单行**高度，无 ~203px inline height |
| A8 | Composer 输入 | 随文字增高至 10 行；超出后细滚动条（悬停/聚焦可见） |
| A9 | `transcript-chat` | 转写与 Agent 之间 `#resize-right` 可拖 |
| A10 | `chat-only` | 无右边界手柄；消息+输入区水平居中，宽 ≤ `min(720px, 50vw)` |

**原型自测：**

```bash
open docs/superpowers/designs/m2t-desktop/finalized.html
# 或本地静态服务预览；切换三种 layout-preset-btn 逐项核对 A1–A10
```

---

## 12. 文档同步

| 文档 | 动作 |
|------|------|
| `2026-06-06-m2t-desktop-agent-pane-design.md` | §4.1 时间分组 → 引用本文 §4；§2.1 grid → 引用本文 §8；文首已链到本文 |
| `2026-06-06-m2t-desktop-agent-hermes-refactor-design.md` | §24.1.5 双轨 thread 与本文 §13.2 一致；无需改 Agent 内核 |
| `2026-06-04-m2t-desktop-ui-design.md` | Agent 消息与 Composer 段落 → 引用本文 §5–§7 |
| `finalized.html` | 当前真源，已落地 |

---

## 13. 后端 / Agent 适配分析

### 13.1 结论（TL;DR）

| 层 | 是否需要改 | 说明 |
|----|------------|------|
| **Desktop React / CSS** | **是（主工作量）** | 历史分组、消息组件、空态、页签头像、布局预设、Composer |
| **Python API / SessionDB** | **基本不需要** | `creator_id` 双轨、messages 字段、turn/stream 已覆盖 |
| **AIAgent / prompt** | **基本不需要** | 全局 vs 博主 profile 已由 `creator_id` + `profile_resolver` 驱动 |
| **可选 API 增强** | 见 §13.5 | 批量删 API、反馈持久化；**不需要** API-1（§14.1） |

**原则：** UI 的 `agentId` 是 **展示层别名**，不新增 DB 列；`agentId === 'global'` ↔ `creator_id IS NULL`（与 [Hermes 重构 §D16](./2026-06-06-m2t-desktop-agent-hermes-refactor-design.md) 一致）。

### 13.2 数据模型映射

```
UI agentId          API / DB creator_id       Agent Profile 根目录
─────────────────────────────────────────────────────────────────
'global'            null                      data/.agent/
<creator_id>        <creator_id>              data/creators/{sec_uid}/.agent/
```

| UI 概念 | 后端对应 | 备注 |
|---------|----------|------|
| 灵犀 | `creator_id: null` | 显示名、头像为 **前端常量**；默认 title 可改为「灵犀」或首条消息后 auto-title |
| 博主 Agent | `creator_id` 非空 | `GET /api/creators` 供头像/昵称 |
| Draft 页签 | **无 DB 字段** | 客户端 `AgentTabEntry.kind === 'draft'`；首条 send 才 `POST /threads` |
| `draftAgentId` | **无 DB 字段** | identity picker 所选 Agent；首条 `POST` 时写入 `creatorId`（灵犀 omit） |

### 13.3 分项：UI 能力 vs 现有后端

#### A. 历史按 Agent 分组（§4）

| 项 | 判定 |
|----|------|
| 分组数据 | ✅ `GET /api/agent/threads` 已含 `creator_id` / `creatorId` |
| 组内排序 | ✅ `updated_at` 降序（`SessionDB.list_threads`） |
| 搜索 | ✅ 客户端 filter title；可选 `SessionDB.search_messages`（FTS）作增强 |
| 实现 | **React**：重写 `threadGroups.ts`（当前仍为 **时间分组**）；`AgentHistorySidebar` 改 markup/CSS |

**已锁定（§14.4）：** 移除 `HistoryFilter`（`useAgentThreads.historyFilter` 及侧栏两颗筛选按钮）。

#### B. 空会话 + 身份选择（§3）

| 项 | 判定 |
|----|------|
| 现状 React | `+` → 立即 `POST /threads`（`createGlobalThread` / `createThread`） |
| **已锁定** | **延迟建 thread**（§14.1）：draft 页签 → 首条 send 时 `POST /threads` + turn |

1. Tab 栏 `+` → `{ kind: 'draft', agentId: 'global' }`；**不**调用 POST。
2. 首条 send：`POST /threads`（`creatorId` = picker；灵犀 omit）→ `POST .../turn`；draft 晋升为 thread 页签。
3. 409 `creator_mismatch` 逻辑不变；picker 与 POST 的 `creatorId` 必须一致。

**不采用：** 「先 POST 空 thread 再改绑」（API-1）— 见 §14.1。

#### C. 组头批量删除（§4.2）

| 项 | 判定 |
|----|------|
| 单条 | ✅ `DELETE /api/agent/threads/{id}` |
| 批量 | ⚠️ 无专用 API |

**P0：** 前端对该组 thread id 列表 **并行 DELETE**（`Promise.allSettled`）；部分失败 UX 见 §4.2。  
**P2 可选：** `DELETE /api/agent/threads?creatorId=` 或 bulk-delete API（减少 RTT；非阻塞）。

#### D. Accio 式消息流（§5）

| UI 元素 | 后端 / 流式事件 | 判定 |
|---------|----------------|------|
| 用户气泡 | `role=user`, `content` | ✅ |
| 助手正文 | `role=assistant`, `content` | ✅ |
| 「已处理 N 秒」 | `duration_ms` / WS `message.assistant.durationMs` | ✅ 已落库 |
| 处理过程展开 | `thinking_text` / WS `message.thinking` | ✅ 已有；UI 行为见 **§5.3.1**（折叠/phase） |
| 流式阶段文案 | WS `turn.phase` | ✅ Turn 进行中显示 `phaseLabel`（§5.3.1） |
| Tool 卡片 | `role=tool` + JSON payload | ✅ |
| 悬停 重试/编辑/复制 | — | **纯 UI**；重试 = 再调 `POST .../turn`（新 user 消息或 regen 策略待定） |
| 点赞/点踩 | — | **纯 UI v1**；P2 若要做质量闭环见 §13.5 |

**Agent 内核：** `AIAgent.run_conversation` 已写 `thinking_text`、`duration_ms`，**无需**为 UI 改 replay 或压缩逻辑。

#### E. 页签头像（§6）

| 项 | 判定 |
|----|------|
| 数据 | `thread.creator_id` + `CreatorsContext` + 全局常量 |
| 实现 | **React** `AgentTabsBar`；无 API 变更 |

#### F. 博主不一致（§1 / 06-06 §1.1）

| 项 | 判定 |
|----|------|
| 发送拦截 | ✅ `POST .../turn` + `_check_creator_mismatch` → 409 |
| 历史选中提示 | ✅ 前端 `shouldNotifyCreatorMismatch` + toast + 切换博主 |
| 与空态选 Agent | 延迟建 thread 时，首条 POST 的 `creatorId` 应与 picker 一致，避免假 409 |

#### G. 桌面三分区 / Composer（§7–§8）

| 项 | 判定 |
|----|------|
| Grid / 居中 / 拖动 | **纯 CSS + layout state**（`desktopLayoutPreset`、`--right-w`） |
| Composer 行数 | **纯前端**（`field-sizing` / `useAutoResizeTextarea` 对齐原型） |

### 13.4 与 Hermes Agent 的关系

[Hermes 重构规格](./2026-06-06-m2t-desktop-agent-hermes-refactor-design.md) 已锁定：

- **D9** Agent Pane UI 可演进，运行时换 HTTP/WS 不断协议形状。
- **D16** `creator_id=NULL` 全局 Agent ↔ 本文「灵犀」。
- **D13/D15** 博主 profile 目录与 prompt 分轨 — 与 UI 按博主分组 **一致**，Agent 侧 **不用** 为分组单独加逻辑。

本次 UI 细化 **不** 要求新增 tool、不改 `run_conversation` 主流程、不改 WS 事件类型枚举。

### 13.5 可选 API / 数据增强（非阻塞）

| ID | 增强 | 优先级 | 说明 |
|----|------|--------|------|
| API-1 | `PATCH /threads/{id}` 支持 `creatorId` | — | **不采用**（§14.1 延迟建 thread） |
| API-2 | 批量删除 threads by `creatorId` | P2 | 组头 ⌫ 优化；前端 loop 可替代 |
| API-3 | `message_feedback` 表 + `POST .../messages/{id}/feedback` | P2 | 点赞/点踩持久化；v1 可 noop |
| API-4 | `GET /threads` 返回 `creator_display_name` | P3 | 减少前端 join；可用 creators 列表代替 |
| API-5 | 首条消息后 auto-title（LLM 或截断 user 首句） | P3 | 改善历史列表可读性；与 UI 无关 |

### 13.6 建议实现顺序（Issue 切分）

| 顺序 | 范围 | 依赖 |
|------|------|------|
| 1 | React 消息组件 Accio 化（user/agent/process/footer） | 无 |
| 2 | `threadGroups` → Agent 分组 + 组折叠/批量删 ConfirmDialog | 无 |
| 3 | 空态身份条 + draft 页签 + 首条 POST thread | 无后端依赖 |
| 4 | 页签头像、`AgentTabsBar` | creators 列表 |
| 5 | 布局预设 + `chat-only` 居中（对齐 §8） | AppShell grid |
| 6 | Composer 单行/10 行/滚动条（对齐 §7） | `useAutoResizeTextarea` |

后端 / Agent：**全程零后端变更** 可交付（步骤 3 已锁定延迟建 thread）。

### 13.7 回归与测试关注点

| 区域 | 建议测试 |
|------|----------|
| API | 现有 `tests/unit/test_api_chat.py` / agent routes（无新增必需用例） |
| Desktop | `agentGroups.test.ts`（分组 + 空组隐藏）；`useAgentTabs.test.ts`（draft 页签）；`useAutoResizeTextarea.test.ts`（**CRITICAL** mount 单行）；扩展 `agentPaneAcceptance.test.tsx` |
| E2E | draft → 首条 send 建 thread；全局 + 博主各一轮 turn；409 mismatch；三栏 resize；chat-only 居中 |
| Agent | 确认 `duration_ms` / `thinking_text` 仍在 integration 路径写入 |

---

## 14. 工程审查决议（2026-06-07 `/plan-eng-review`）

以下四项在 eng review 中 **已锁定**；实现与 Issue 拆分须遵循。

### 14.1 D1 — 空会话：延迟建 thread（draft 页签）

| 选项 | 决议 |
|------|------|
| A) `+` 开 client draft，首条 send 再 `POST /threads` | **采用** |
| B) 立即 POST 空 thread + API-1 改绑 creator | 不采用 |

**理由：** 零后端改动；避免空 thread 垃圾数据；与 §13.3 B 一致。`useAgentTabs` / `AgentPanel` 须支持 `AgentTabEntry`（§2.2）。

### 14.2 D2 — 历史分组可见性 + 批量删失败

| 规则 | 决议 |
|------|------|
| 空博主组（0 thread） | **不渲染** |
| 灵犀组 0 thread | **不渲染**（与博主组同规则） |
| 无任何组 | 显示「暂无会话」 |
| 批量 DELETE 部分失败 | 成功项移除 + toast「已删除 N 条，M 条失败」+ 失败项保留 |

**理由：** 减少侧栏噪音；新建会话走 `+` draft，不需空组占位。原型可保留「全量 mock 组」作演示，**React 以本规则为准**。

### 14.3 D3 — `.chat-msg-process` 交互

| 规则 | 决议 |
|------|------|
| Turn 进行中 | 显示 WS `phaseLabel`；不可展开 |
| Turn 完成 | 默认折叠；摘要「已处理 N 秒」 |
| 有 `thinking_text` | 点击行/`›` 展开正文 |
| 无 `thinking_text` | 无 `›`，不可展开 |

详见 §5.3.1。

### 14.4 D4 — 移除 HistoryFilter

| 选项 | 决议 |
|------|------|
| 移除「全部 / 当前博主」 | **采用** |
| 保留为第二筛选维 | 不采用 |

**理由：** Agent 分组 + 搜索已覆盖用途；少一层状态，避免与 `creator_id` 分组语义冲突。删除 `HistoryFilter` 类型、`useAgentThreads` 筛选逻辑及侧栏 UI。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-07 | 初稿：汇总 Agent 面板 UI 细化会话全部修改 |
| 2026-06-07 | §13：后端 / Agent 适配分析；§12 补充 Hermes 交叉引用 |
| 2026-06-07 | §14：工程审查四项决议锁定；同步 §2–§11、§13 |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 8 issues addressed via §14 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **VERDICT:** Eng review CLEARED — §14 locked; ready for Issue 拆分 / 实现
