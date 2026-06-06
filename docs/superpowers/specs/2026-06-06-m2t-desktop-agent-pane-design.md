# m2t-desktop — Agent 区块与桌面分区布局

**日期:** 2026-06-06  
**状态:** 草案（原型已落地于 `finalized.html`，待同步 React）  
**前置:** [m2t-desktop 总规格](./2026-06-04-m2t-desktop-design.md)、[UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md)  
**原型真源:** [finalized.html](../designs/m2t-desktop/finalized.html)（本文与布局/Agent 相关段落优先于 ui-design 旧描述）

---

## 0. 背景与范围

### 0.1 Agent 区块

右栏下半为 **Agent 对话区**。v1 原设计为「顶栏标题 + 单线程 Composer + 消息流」。本次参照 **Cursor Agent 面板** 调整为：

- 近期 **页签**（最多 5 个）
- 右侧 **全局历史会话栏**（可折叠、可搜索、按时间分组）
- 对话区与历史栏之间的 **可拖边界**

目标：多线程切换更像 IDE Agent；关闭页签 ≠ 删除会话。

### 0.2 桌面分区布局

右栏标题栏提供 **3 种分区预设**（迷你示意图按钮），在「四区完整 / 左中右转写 / 仅对话」间切换，并持久化到 `localStorage`。

其中 **`transcript-chat`** 将转写区从中栏下方叠放改为 **左（博主）| 中（转写/摘要）| 右（Agent）**，并在中栏转写顶栏增加 **历史场次下拉**，与左栏选中博主联动。

### 0.3 范围边界

| 在范围内 | 不在范围内 |
|----------|------------|
| Agent pane 内部 UI/交互 | Pi **tool** 语义变更（新增/改 tool 行为） |
| 三分区预设 + 转写区挂载（React 条件渲染；见 §1.2） | 页签拖拽排序、按 creator 过滤 Agent 历史 |
| 历史场次下拉（转写/摘要切换） | 页签 **open tabs** 持久化（v1 刷新后页签栏空） |
| `GET .../history/{kind}/{item_id}/transcript\|summary`（§14.3 A，已锁定） | 附件 / 上下文按钮真实能力（仍为 Toast） |
| sidecar **`context.refresh` 字段扩展**（paths/kind，§14.3 C，已锁定） | B 站 archive/dynamic 进下拉（P2） |

---

## 1. 已锁定决策

### 1.1 Agent 会话

| 项 | 决策 | 说明 |
|----|------|------|
| 会话范围 | **全局** | 历史列表跨 creator / live session；v1 不做按博主筛选 UI |
| 历史栏位置 | **右侧** | `对话区 \| 拖动手柄 \| 历史栏` |
| 页签顺序 | **固定** | 点击切换 **不重排**；新建/从历史打开 **追加末尾**；满 5 个 **丢弃最左** |
| 页签关闭 | **仅关页签** | 不删除 SQLite thread |
| 历史删除 | **删 thread** | `DELETE /api/chat/threads/{id}`；同步关页签 |
| 历史栏折叠 | **仅隐藏历史栏** | `☰` 不折叠整个右栏 |
| 对话区顶栏 | **取消** | 无 `.agent-main-header`；标题仅在页签 |
| 模型显示 | **Composer 内** | `#agent-model-select`；无顶部 `model-pill` |
| 全局 thread vs 当前博主 | **激活时校验** | `thread.creator_id` ≠ 左栏选中博主 → **toast** 说明上下文可能不一致，并提供 **「切换到该博主」**；不自动改 sidebar，除非用户确认 |

### 1.2 桌面分区

| 项 | 决策 | 说明 |
|----|------|------|
| 默认预设 | **`full`** | 博主 + 播放 + 转写 + 对话 |
| 转写挂载（**React**） | **条件渲染 slot** | 同一 `TranscriptPane` 树：`full` → 右栏 `.right-split` 上部；`transcript-chat` → 中栏 slot；**禁止** DOM `appendChild` 迁移（避免 unmount 断 WS） |
| 转写挂载（**原型 HTML**） | **DOM 迁移** | `finalized.html` 仍用 `mountTranscriptPane(preset)` 作交互真源 |
| 右栏标题 | **随预设变化** | `transcript-chat` 时为「Agent」；否则「内容」 |
| 无播放区时右栏宽度 | **`minmax(280px, 1fr)`** | `transcript-chat` / `chat-only` 填满剩余宽度 |
| 三列列宽 clamp | **扩展 viewport 逻辑** | `transcript-chat` 下 center/right 各 `1fr`；现有 `maxRightWForViewport` 假定 center+right 二分，实现时需扩展 `useColumnResize` / clamp（§2.2） |
| `chat-only` | **自动展开右栏** | 隐藏 `#collapse-right`；切换入该模式时若已折叠则展开 |
| 场次下拉范围 | **当前选中博主** | 直播 + 作品（API `kind: live \| vod`）；「当前 · …」= live partial / 未开录占位 |

### 1.3 工程审核锁定（2026-06-06）

| ID | 决策 | 选项 |
|----|------|------|
| D1 | VOD 转写/摘要 | **API 统一路由**（§14.3 A）— 不用 v1 path-only 规避 |
| D2 | sidecar 上下文 | **扩展 `context.refresh`** 传 `transcriptPath` / `summaryPath` / `sessionKind` |
| D3 | 全局 thread vs 博主 | **toast + 可选切换博主**（§1.1） |
| D4 | React 转写挂载 | **条件渲染 slot**（§1.2），不 port 原型 DOM 迁移 |

---

## 2. 桌面分区布局

### 2.1 预设一览

右栏标题行 `.side-panel-header-actions` 内 `.layout-preset-group`，三钮 `data-layout`：

| `data-layout` | 可见分区 | 隐藏 / 变化 |
|---------------|----------|-------------|
| `transcript-chat` | 博主 \| **中栏转写/摘要** \| 右栏 Agent | 播放区；右栏不再上下叠放转写 |
| `full`（默认） | 博主 \| 播放 \| 转写 + Agent（右栏上下 split） | — |
| `chat-only` | 博主 \| Agent（右栏独占） | 播放区 + 转写区 |

**App 类名：**

| 预设 | `#app` class | 说明 |
|------|--------------|------|
| `full` | （无额外 class） | 标准四区 grid |
| `transcript-chat` | `.desktop-layout-transcript` | 三列 grid + 中栏显示转写 |
| `chat-only` | `.desktop-layout-chat` | 隐藏中栏与转写 |

**Grid（`transcript-chat`，右栏未折叠）：**

```
sidebar | grip | minmax(280px, 1fr) center | grip | minmax(280px, 1fr) right
```

**Grid（`chat-only`，右栏未折叠）：**

```
sidebar | grip | 0 | 0 | minmax(280px, 1fr) right
```

### 2.2 `transcript-chat` — 左中右

**原型 HTML（`finalized.html`）：**

| 行为 | 实现要点 |
|------|----------|
| 中栏容器 | `#transcript-center-slot`（`<main class="center">` 内） |
| 转写 DOM | `#transcript-pane` 由 `mountTranscriptPane('transcript-chat')` 挂入 center slot |
| 隐藏播放 | `.center-toolbar`、`.center-body` → `display: none` |
| 右栏 | 仅 `.agent-pane`；`#resize-right-split` 隐藏 |
| 中/右列宽 | `.col-resize-right` 可拖 |

切回 `full` 时，`mountTranscriptPane('full')` 将 `#transcript-pane` 插回 `.right-split` 内、`#resize-right-split` 之前。

**React（`apps/m2t-desktop`）：**

| 行为 | 实现要点 |
|------|----------|
| Grid | `AppShell` 按 `desktopLayoutPreset` 切换 grid class（同 §2.1） |
| 转写区 | **条件渲染**：`preset === 'transcript-chat'` → `<TranscriptPane />` 在中栏 slot；否则在右栏 `.right-split` 上部；**同一组件**、同一 props 源（§5 `TranscriptSelection`） |
| 播放区 | `transcript-chat` / `chat-only` 隐藏 `CenterToolbar` + 播放 body |
| 列宽 | 扩展 `layoutConstants` / `useColumnResize`：三列模式下 center、right 独立 clamp，勿复用仅适用于「center+right 二分剩余宽度」的 `maxRightWForViewport` |
| WS 直播转写 | preset 切换时保持 `TranscriptPane` 挂载策略，避免 unmount 断开 `/transcript/stream` |

### 2.3 历史场次下拉（中栏转写顶栏）

位于 `.transcript-pane .tab-row` 右侧 `.transcript-tab-actions`，与「复制」并列：

| 元素 | 说明 |
|------|------|
| `#transcript-session-select` | 按左栏 `data-creator` 填充选项 |
| 选项类型 | **当前**（合成项 `id: live`）、历史 **直播**、**作品**（API **`kind: vod`**，勿写 `aweme`） |
| 切换行为 | `live` → 当前录制 / partial（`GET/WS /api/sessions/{live_uuid}/...`）；历史 **live** → 同上 UUID；历史 **vod** → **`GET /api/creators/{id}/history/vod/{item_id}/transcript\|summary`**（§14.3 A，已锁定） |
| 无转写 | toast「该场次暂无转写」；有转写无摘要时强制切到「转写」Tab |

**数据（实现期）：**

- 列表：`GET /api/creators/{id}/sessions`（`kind` 枚举：`live` \| `vod`）
- Live 内容：`GET/WS /api/sessions/{live_session_uuid}/transcript|summary`
- VOD 内容：`GET /api/creators/{creator_id}/history/vod/{item_id}/transcript|summary`（与 live 路由对称，禁止对 aweme_id 调 `/api/sessions/{id}/transcript`）

**原型：** mock 对象 `CREATOR_TRANSCRIPT_SESSIONS[creatorId]`；切换博主时 `syncTranscriptSessionSelect(creatorId)` 并重置为 `live`。

### 2.4 持久化与折叠

| Key / 字段 | 内容 |
|------------|------|
| `m2t-desktop-layout.desktopLayoutPreset` | `'full' \| 'transcript-chat' \| 'chat-only'` |

左栏 / 右栏手动折叠（`.left-collapsed` / `.right-collapsed`）与预设 **叠加生效**；预设仅在未 `right-collapsed` 时改变 grid 列定义。

---

## 3. Agent 区块布局

### 3.1 在右栏中的位置

- **`full`：** 右栏上下 split — 上 `#transcript-pane`，下 `#agent-pane`，`#resize-right-split` 调 `--right-agent-h`
- **`transcript-chat`：** 转写已迁至中栏；右栏 **仅** Agent
- **`chat-only`：** 右栏 **仅** Agent（`.agent-pane` flex 撑满）

### 3.2 纵向结构（Agent 区内）

```
┌─ agent-pane ───────────────────────┐
│ agent-tabs-bar          +  ☰      │
├────────────────────────────────────┤
│ agent-body                         │
│ ┌──────────────┬─┬──────────────┐  │
│ │ agent-main   │█│ agent-history│  │
│ │ chat-scroll  │ │ search       │  │
│ │ composer     │ │ thread list  │  │
│ └──────────────┴─┴──────────────┘  │
└────────────────────────────────────┘
```

### 3.3 页签栏 `agent-tabs-bar`

| 区域 | 元素 | 行为 |
|------|------|------|
| 左 | `.agent-tabs-scroll` | 横向滚动；最多 **5** 个 `.agent-tab-wrap` |
| 右 | `.agent-tabs-actions` | `+` 新建 thread；`☰` 折叠/展开历史栏 |

**页签 `.agent-tab-wrap`：**

- 文案：thread `title`（ellipsis，max-width ~168px）
- 激活：底边 accent
- 悬停：显示 `×`（`.agent-tab-close`）
- 点击主体：切换 `activeAgentThreadId`
- 点击 `×`：从 `agentTabIds` 移除；若关当前 thread，激活相邻或清空

### 3.4 对话区 `agent-main`

| 元素 | 说明 |
|------|------|
| `#chat-scroll` | 用户/助手消息、thinking、tool-card（沿用现有） |
| `#agent-form.agent-composer` | 模式 pill、模型下拉、上下文/附件、发送 |
| ~~`.agent-main-header`~~ | **已取消** |

### 3.5 历史栏 `agent-history`

| 元素 | 说明 |
|------|------|
| `#agent-history-search` | placeholder：`搜索 Agent…` |
| `#agent-thread-list` | 分组列表，见 §4 |
| ~~「新建 Agent」~~ | **已移除** — 新建仅 Tab 栏 `+` |

### 3.6 拖动手柄 `#resize-agent-history`

- 位置：对话区与历史栏之间（`.agent-col-resize`）
- **方向：** 向右拖 → **加宽**历史栏；`agentHistoryW = clamp(start - dx, 140, 340)`
- 历史栏折叠时：手柄 `display: none`

---

## 4. Agent 历史会话列表

### 4.1 时间分组

| `group` | 展示标题 |
|---------|----------|
| `today` | TODAY |
| `yesterday` | YESTERDAY |
| `week` | LAST 7 DAYS |
| `month` | LAST 30 DAYS |

**Last 7 Days：** 默认最多 3 条 + 「More」展开（原型）；实现期可按 API 分页。

### 4.2 列表项 `.agent-thread-item`

| 部分 | 说明 |
|------|------|
| `.agent-thread-icon` | 选中项 accent 高亮 |
| `.agent-thread-main` | 标题 + 可选 meta |
| `.agent-thread-menu-btn` | 悬停显示 `⋯` |

**交互：**

- 点击主区域：选中 thread；未在页签中则 `ensureAgentTab(id)`；若 `thread.creator_id` ≠ 当前选中博主 → toast +「切换到该博主」（§1.1）
- 点击 `⋯`：上下文菜单（fixed + backdrop）

### 4.3 上下文菜单

| 菜单项 | 行为 |
|--------|------|
| 重命名 | `PATCH /api/chat/threads/{id}` `{ title }`；同步页签 |
| 删除 | `DELETE` thread；从列表与页签移除（实现期建议确认框） |

---

## 5. 前端状态模型

```ts
// Agent — React 参考
type AgentTabState = {
  agentTabIds: string[];        // max 5，固定顺序；v1 不持久化（刷新后页签栏空，历史栏仍有 thread）
  activeAgentThreadId: string | null;
};

type AgentHistoryUI = {
  historyCollapsed: boolean;
  historySearch: string;
  weekExpanded: boolean;
  contextMenuThreadId: string | null;
};

// 布局 + 转写场次（单一数据源，替代 playbackSession 与下拉各管各）
type TranscriptSelection =
  | { mode: 'live'; liveSessionId: string | null }   // null = 未开录占位
  | { mode: 'history'; kind: 'live' | 'vod'; itemId: string };

type DesktopLayoutState = {
  desktopLayoutPreset: 'full' | 'transcript-chat' | 'chat-only';
  transcriptSelection: TranscriptSelection;         // 下拉与 TranscriptPane 共用
};
```

**页签 vs 历史：**

| 操作 | `agentTabIds` | 后端 thread |
|------|---------------|-------------|
| 关闭页签 `×` | 移除 | **保留** |
| 历史「删除」 | 移除 | **删除** |
| 新建 `+` | 末尾追加（满则 shift 最左） | `POST` |
| 从历史选中未开页签 | 末尾追加 | 不变 |

---

## 6. 尺寸与持久化

### 6.1 CSS 变量

| 变量 | 默认 | 范围 | 说明 |
|------|------|------|------|
| `--right-agent-h` | 380px | 160–720px | Agent 区高度（`#resize-right-split`） |
| `--agent-history-w` | 200px | 140–340px | Agent 历史栏宽度 |

### 6.2 localStorage

| Key | 内容 |
|-----|------|
| `m2t-desktop-layout` | `sidebarW`, `rightW`, `agentH`, `agentHistoryW`, **`desktopLayoutPreset`** |
| `m2t-agent-history-collapsed` | `'1'` = 历史栏折叠 |

---

## 7. API 映射

### 7.1 Agent threads

| UI 动作 | API | 后端状态 |
|---------|-----|----------|
| 列出全局 threads | `GET /api/chat/threads`（无 query） | ✅ 已有 |
| 切换 thread | `GET .../messages` + sidecar `context.refresh`（含 paths/kind，§14.3 C） | ✅ 字段扩展待 sidecar 实现 |
| 新建 | `POST /api/chat/threads`（`creatorId` 必填） | ✅ |
| 重命名 | `PATCH ...` `{ title }` | ✅ |
| 删除 | `DELETE /api/chat/threads/{id}` | ✅ |
| 绑定转写场次 | `PATCH ...` `{ sessionId }` | ✅ 字段已有；前端待接 |
| 发送消息 | sidecar stdin + `POST .../messages` 落库 | ✅ |
| 模型 | `PATCH` `{ model }` | ✅ |

时间分组用响应字段 **`updated_at`**（v1 足够；增强见 §14.4）。

### 7.2 转写场次下拉

| UI 动作 | API | 后端状态 |
|---------|-----|----------|
| 填充下拉 | `GET /api/creators/{id}/sessions` | ✅ |
| 「当前」首项 | `creators[].active_session_id` + live status | ✅ 前端合成 |
| Live 转写/摘要（当前） | `GET/WS /api/sessions/{live_uuid}/transcript\|summary` | ✅ |
| 历史 live 转写/摘要 | `GET .../history/live/{session_id}/transcript\|summary` | ⚠️ P0 新增（§14.3 A） |
| VOD 转写/摘要 | `GET .../history/vod/{item_id}/transcript\|summary` | ⚠️ P0 新增（§14.3 A，已锁定 D1） |
| 选项展示名 | `display_label`（live）/ `title`（vod） | ⚠️ P0（§14.3 B） |

---

## 8. React 组件映射

| 原型 / 职责 | 建议组件 / hook |
|-------------|-----------------|
| `.layout-preset-group` | `DesktopLayoutPresets` |
| `#transcript-session-select` | `TranscriptSessionSelect`（驱动 `TranscriptSelection`） |
| 转写区 slot | `AppShell` 内按 `desktopLayoutPreset` **条件渲染** `TranscriptPane`（**非** `useTranscriptPaneMount` DOM 迁移） |
| `.agent-tabs-bar` | `AgentTabsBar` |
| `.agent-tab-wrap` | `AgentTab` |
| `.agent-main` + `#chat-scroll` | `AgentChatThread` |
| `#agent-form` | `AgentComposer`（移除 `.agent-header` / `model-pill`） |
| `.agent-history` | `AgentHistorySidebar`（含 creator 不一致 toast 流程） |
| `#resize-agent-history` | `useAgentHistoryResize` |
| `.agent-context-menu` | `AgentThreadContextMenu` |
| Agent 数据层 | `useAgentThreads()` 全局 CRUD + `useAgentTabs()` 页签 UI + `useM2tAgent(threadId)` 单 thread 消息/sidecar |

---

## 9. 无障碍

| 元素 | 要求 |
|------|------|
| `#agent-tabs-row` | `role="tablist"`；tab `aria-selected` |
| `#btn-agent-history-toggle` | `aria-pressed` |
| `#resize-agent-history` | `role="separator"` `aria-orientation="vertical"` |
| `.layout-preset-btn` | `aria-pressed` 反映选中预设 |
| `#transcript-session-select` | `aria-label="选择历史场次"` |
| 上下文菜单 | `role="menu"`；Esc / backdrop 关闭 |
| 页签关闭 | `aria-label="关闭页签"` |

---

## 10. 与旧 UI 设计差异

相对 [ui-design §7.2](./2026-06-04-m2t-desktop-ui-design.md#72-agent-composercursor-式)：

| 旧 | 新 |
|----|-----|
| 无页签 / 无历史栏 | 页签 + 右侧历史栏 |
| `.agent-header` + `.model-pill` | **移除**；模型仅在 Composer |
| 固定四区 grid | 三种分区预设 + `desktopLayoutPreset` |
| 转写仅在右栏上部 | `transcript-chat` 下转写在中栏 + 场次下拉 |
| layout 仅 `agentH` | 增加 `agentHistoryW`、历史折叠 key |

**待同步文档：** ui-design §7、总规格 §4.6 布局描述。

---

## 11. 验收标准

### 11.1 桌面分区（L）

| ID | 通过条件 |
|----|----------|
| L1 | 三钮切换后可见分区与 §2.1 表一致 |
| L2 | 选中钮 active；刷新后 `desktopLayoutPreset` 保留 |
| L3 | `full` 下中栏播放、右栏转写/Agent split 正常 |
| L4 | `transcript-chat` 下转写在中栏、右栏仅 Agent、标题为「Agent」 |
| L5 | 切换博主后场次下拉更新；选历史场次加载转写/摘要（live/vod 均走 history 或 session 路由，不对 vod 调 `/api/sessions/{aweme_id}`） |
| L6 | `chat-only` 隐藏转写与折叠右栏钮；右栏 Agent 撑满 |

### 11.2 Agent 区块（A）

| ID | 通过条件 |
|----|----------|
| A1 | 历史栏在右；对话区无顶栏；Composer 正常 |
| A2 | 最多 5 页签；切换不重排；悬停 `×`；关闭不关 thread |
| A3 | `+` 新建并激活；满 5 挤掉最左 |
| A4 | 搜索过滤；四组时间标签；`☰` 折叠/展开 |
| A5 | 重命名改 title；删除移除列表与页签 |
| A6 | 历史栏拖动 140–340px；刷新保留 |
| A7 | 折叠后无历史栏与手柄 |
| A8 | `agentHistoryW`、折叠态写入 localStorage |
| A9 | 转写/摘要 split、PiEvent、tool-card、模型 PATCH 回归 |
| A10 | 激活其他博主的 thread → toast + 可选切换博主；确认后 sidebar 与 Agent 上下文一致 |

**原型验收：** 打开 `finalized.html`，逐项验证 L1–L6、A1–A8（A10 为 React 实现项）。

---

## 12. 非目标

- 页签拖拽排序；页签中键关闭 / 右键菜单（v1.1）
- **页签 open tabs 持久化**（v1 仅持久化 thread 本体；刷新后 `agentTabIds` 清空）
- 历史栏「新建 Agent」重复入口
- Agent 历史按 creator 筛选
- VOD 转写 **path-only** 读法作为正式方案（已选 API 统一，§1.3 D1）
- 附件 / 上下文按钮真实能力（仍为 Toast）
- 删除 thread 确认框（原型无；实现建议加）

---

## 13. 实现顺序

1. **finalized.html** — 已完成（交互真源；React 不 port DOM 迁移）
2. 同步 **ui-design.md** §7、总规格布局段落
3. **后端 P0** — §14.3 A（history transcript/summary 路由）、B（`display_label`）、测试 §14.6
4. **sidecar P0** — §14.3 C（`context.refresh` 扩展 paths/kind）
5. **React 布局** — `DesktopLayoutPresets` + 条件渲染 `TranscriptPane` + `TranscriptSessionSelect` + `TranscriptSelection`
6. **React Agent** — 多 thread UI + hook 拆分 + creator 不一致 toast + `PATCH sessionId` / `context.refresh` 联动
7. **后端 P1** — §14.4（thread 列表搜索/分页、可选 preview）
8. **验收** — §11 + 总规格 D4/D8/D9/D10 回归

---

## 14. 后端适配（相对现状）

布局预设、列宽、Agent 历史栏折叠等 **纯前端 localStorage**。Python sidecar **无 tool 语义变更**；Node sidecar 需扩展 `context.refresh`（§14.3 C）。

以下对照仓库现状（`src/media2text/api/routes/chat.py`、`creators.py`、`sessions.py`，`api/services/sessions_list.py`，`packages/m2t-agent-sidecar`，`DesktopChatRepo`）。

### 14.1 已满足 — 可直接复用

| 能力 | 现状 | 前端用法 |
|------|------|----------|
| Agent thread CRUD | `GET/POST/PATCH/DELETE /api/chat/threads`，`GET/POST .../messages` | 页签、历史菜单、持久化 |
| **全局** thread 列表 | `GET /api/chat/threads` **不传** `creatorId` → 全表 `ORDER BY updated_at DESC` | Agent 历史栏（v1 全局） |
| 时间分组字段 | 响应含 `updated_at`（发消息时刷新） | Today/Yesterday/7d/30d 前端分组 |
| 重命名 / 删 thread | `PATCH` title、`DELETE` 级联 messages | 历史 `⋯` 菜单 |
| 博主场次列表 | `GET /api/creators/{id}/sessions` | 转写顶栏下拉 |
| 场次元数据 | `kind`（`live`/`vod`）、`has_transcript`、`has_summary`、`transcript_path`、`summary_path`、`title`（vod） | 选项文案、禁用无转写 |
| Live 转写 | `GET /api/sessions/{live_session_id}/transcript` + WS `.../transcript/stream` | 「当前 · 录制中」 |
| Live 摘要 | `GET /api/sessions/{live_session_id}/summary` | 摘要 Tab |
| 历史场次转写/摘要（统一） | `GET /api/creators/{id}/history/{kind}/{item_id}/transcript\|summary` | **P0 新增**（§14.3 A）；`kind` = `live` \| `vod` |
| 当前录制 session | `GET /api/creators` / `{id}` 含 `active_session_id` | 下拉首项「当前 · …」 |
| 按路径读 sidecar | `GET /api/media?path=` | 保留给 playback 视图 / 兜底；**下拉 VOD 正式路径为 history API** |

### 14.2 无需后端 — 前端 / sidecar 壳层

| 项 | 说明 |
|----|------|
| `desktopLayoutPreset` | 仅 localStorage |
| 页签最多 5 个、固定顺序 | 纯前端 `agentTabIds` |
| 关闭页签保留 thread | 不调 DELETE |
| 新建 thread 的 `creatorId` | 传 **当前选中博主**（DB 字段必填；与「全局历史 UI」不矛盾） |

### 14.3 P0 — 已锁定 / 待实现

#### A. 历史场次转写与摘要 API（**已锁定 D1：API 统一**）

**问题：** `GET /api/sessions/{id}/transcript|summary` 仅查 **`live_sessions`**；VOD 的 `session_id` = `aweme_id` 会 **404**。禁止前端对 vod item_id 复用该路由。

**已锁定方案 — 新增对称路由：**

```
GET /api/creators/{creator_id}/history/{kind}/{item_id}/transcript
GET /api/creators/{creator_id}/history/{kind}/{item_id}/summary
```

| 参数 | 说明 |
|------|------|
| `creator_id` | DB `creators.id`（与 sessions 列表一致） |
| `kind` | `live` \| `vod`（与 `GET .../sessions` 响应一致） |
| `item_id` | live：`live_sessions.id`（UUID）；vod：`awemes.aweme_id` |

**实现要点：**

- 内部复用 `read_transcript_payload` / `read_summary_text` + manifest / `transcript_path` 解析（与 `history_media`、playback 同源）
- 404：场次不存在、或无转写/摘要文件时返回明确 JSON error（前端 toast）
- **当前 live**（下拉首项）仍可用现有 `GET/WS /api/sessions/{uuid}/...`；历史 live 条目走 `history/live/{uuid}/...` 或继续用 session 路由（实现时二选一，文档以 history 路由为准）

**响应：** 与现有 `/api/sessions/{id}/transcript` 形状对齐，便于 `TranscriptPane` 共用 fetch 逻辑。

#### B. Live 场次下拉展示名

- `_build_live_item` 返回 `title: null`；下拉若只用 `title` 会空白。
- **推荐：** 在 `sessions_list` 增加 **`display_label`**（如 `2026-06-02 21:04 直播`），规则：`started_at` 格式化 + `kind` 后缀；VOD 继续用 `title` 或 aweme 描述。

#### C. Agent sidecar 上下文与转写场次联动（**已锁定 D2：扩展 refresh**）

- `context.refresh` 当前仅传 `creatorId` / `sessionId` / `threadId`；`hydrateContextFromApi` 用 `GET /api/sessions/{sessionId}`，**VOD 场次 hydration 失败**。
- **已锁定方案 — 扩展 refresh payload（Tauri → sidecar stdin，不改 Python tool）：**

```ts
// context.refresh 扩展字段（sidecar packages/m2t-agent-sidecar）
{
  creatorId: string;
  sessionId?: string | null;
  threadId?: string | null;
  sessionKind?: 'live' | 'vod' | null;
  transcriptPath?: string | null;   // workspace 相对路径
  summaryPath?: string | null;
  contextMode?: 'transcript' | 'summary' | 'both';
}
```

- sidecar `hydrateContextFromApi`：**优先**使用 payload paths；仅 live 且无 paths 时回退 `GET /api/sessions/{id}`。
- **不采用** hydrate 404 后扫 `GET .../sessions` 列表回退（D2 未选）。

#### D. Thread 绑定当前转写场次

- `PATCH /api/chat/threads/{id}` 已支持 `sessionId` / `clearSession`。
- **前端行为：** 用户切换场次下拉时，对 **当前 active thread** `PATCH { sessionId }`（vod 传 aweme_id 或约定 sentinel，与 DB 语义一致）+ `context.refresh`（含 paths/kind）。
- **可选增强：** `contextMode` 随 Tab（转写/摘要）自动 `transcript|summary|both`（已有 PATCH 字段）。

### 14.4 P1 — Agent 历史栏体验增强

| 项 | 现状 | 建议 |
|----|------|------|
| 列表分页 | 一次返回全表 | `limit` / `offset`（或 `cursor`）+ 默认 cap |
| 搜索 | 仅前端 filter | 可选 `q` 参数 `LIKE title` |
| 列表 meta | 无最后一条消息摘要 | 可选 `last_message_preview`（子查询最近 user/assistant 截断） |
| `last_message_at` | 用 `updated_at` 近似 | v1 可接受；若 PATCH 仅改 title 也会 bump `updated_at` |

### 14.5 P2 — 可选 / 后续

| 项 | 说明 |
|----|------|
| `GET .../sessions?kind=live\|vod` | 下拉只要直播或只要作品时减少 payload |
| B 站 `archives` / `dynamics` | 列表目前合并 **live_sessions + awemes**；manifest 里纯 archive/dynamic 若未进 aweme 表则 **不会出现在下拉**，需扩展 `sessions_list` |
| 服务端合成「当前 · 录制中」项 | 也可前端用 `active_session_id` + status 拼首项（原型做法） |
| Agent thread 按 creator 筛选 | v1 非目标；API 已支持 `creatorId` 查询供日后使用 |

### 14.6 测试补充建议

| 场景 | 测试文件方向 |
|------|----------------|
| 全局 thread 列表无 filter | `test_api_chat.py` 增 `GET /threads` 无参 |
| history transcript/summary（P0-A，**必做**） | `test_api_history_transcript.py` — live + vod happy/404 |
| `display_label` 非空 | `test_api_sessions.py` assert live item label |
| PATCH thread sessionId + context.refresh paths | sidecar 单测 + 集成 mock hydrate |
| 不对 vod aweme_id 调 `/api/sessions/{id}/transcript` | React/API 回归（防 404 混用） |

---

## 附录 A — Agent DOM 骨架

```html
<section class="agent-pane" id="agent-pane">
  <div class="agent-tabs-bar">
    <div class="agent-tabs-scroll" id="agent-tabs-row"></div>
    <div class="agent-tabs-actions">
      <button id="btn-agent-new">+</button>
      <button id="btn-agent-history-toggle">☰</button>
    </div>
  </div>
  <div class="agent-body">
    <div class="agent-main">
      <div class="chat-scroll" id="chat-scroll">…</div>
      <form class="composer agent-composer" id="agent-form">…</form>
    </div>
    <div class="col-resize agent-col-resize" id="resize-agent-history"></div>
    <aside class="agent-history" id="agent-history">
      <input id="agent-history-search" />
      <div class="agent-thread-list" id="agent-thread-list"></div>
    </aside>
  </div>
  <div class="agent-context-menu-backdrop" id="agent-context-backdrop"></div>
  <div class="agent-context-menu" id="agent-context-menu">…</div>
</section>
```

## 附录 B — 布局相关 DOM / 类名

```html
<!-- 右栏标题行 -->
<div class="layout-preset-group" role="group">
  <button data-layout="transcript-chat" class="layout-preset-btn">…</button>
  <button data-layout="full" class="layout-preset-btn active">…</button>
  <button data-layout="chat-only" class="layout-preset-btn">…</button>
</div>

<!-- 中栏转写挂载点（transcript-chat） -->
<main class="center">
  <div id="transcript-center-slot" class="transcript-center-slot"></div>
  …
</main>

<!-- 转写顶栏场次下拉 -->
<select id="transcript-session-select" class="transcript-session-select">…</select>
```

**关键 JS（仅原型 HTML）：** `applyDesktopLayoutPreset()`、`mountTranscriptPane(preset)`、`syncTranscriptSessionSelect(creatorId)`、`applyTranscriptSessionSelection(sessionId)`。

**React：** 见 §8 — 条件渲染 `TranscriptPane`，不 port 上述 DOM 迁移函数。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | issues_open → **decisions locked** | 7 arch issues; D1–D4 resolved in §1.3 |
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

- **UNRESOLVED:** 0（D1–D4 已写入 §1.3）
- **VERDICT:** Eng decisions locked — ready for P0 backend + React implementation
