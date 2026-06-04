# media2text Desktop — UI 设计系统

**日期:** 2026-06-04  
**状态:** 已批准（**UI 真源：** [finalized.html](../designs/m2t-desktop/finalized.html)；本文随原型同步）  
**关联:** [架构规格](./2026-06-04-m2t-desktop-design.md) · [UI 审视](./2026-06-04-m2t-desktop-ui-review.md)  
**可交互原型:** [finalized.html](../designs/m2t-desktop/finalized.html)

---

## 1. 产品语境

| 项 | 说明 |
|----|------|
| 产品 | media2text 个人桌面监控控制台（Tauri） |
| 用户 | 自用；本机单 workspace；长期后台 daemon |
| 类型 | 工具型 dashboard + 内嵌视频 + 实时转写 + Agent |
| 第一印象 | 「一眼知道谁在录、能否立刻开录、字幕与 Agent 是否跟得上当前场次」 |

**Memorable thing（设计锚点）：** 左栏状态灯 + 中栏画面/场次，右栏「转写在上、Agent 在下」——监控工具感，不是通用 Chat 壳。

---

## 2. 美学方向

| 维度 | 选择 | 说明 |
|------|------|------|
| 方向 | **Industrial / Utilitarian** | 数据密度、状态优先；**默认亮色** + 可选暗色（长时间盯屏） |
| 装饰 | **Minimal** | 无渐变 blob；边框与层级区分面板 |
| 布局 | **Grid-disciplined（三栏 + 拖动手柄）** | 240px / flex / 360px 默认；左折叠 56px、右折叠 48px rail；列宽可拖 |
| 色彩 | **Restrained + 语义灯** | 蓝 accent；绿/黄/红/灰为直播状态；`data-theme="light"|"dark"` |
| 动效 | **Minimal-functional** | 折叠 0.2s；直播头像呼吸环；`prefers-reduced-motion` 全关 |

**SAFE（品类基线）：** 三栏工具布局、顶栏 Tab、列表 + 详情、只读 Markdown 区（默认亮色，可选暗色）。  
**RISK（差异化）：** 圆形头像 + 角标状态灯 + **直播中红色外环呼吸**；🔴「在播未录」录制横幅；历史合并组行；Agent **Cursor 式 Composer** + tool 卡片嵌在对话流。

---

## 3. 版式与区域

```
┌ 中栏 toolbar 44px（macOS drag，无顶栏标题条）────────────────┐
├ grip ┬────────── 中栏 flex ──────────┬ grip ┬─右 360px──────┤
│左栏  │ 博主名 + badge              │      │ 内容（44px 头） │
│240px│ Tab: 直播|历史               │      │ 转写 | 摘要     │
│     │ .video-viewport 16:9        │      │ Markdown 区     │
│监控 │   └ 竖屏 9:16 居中          │      ├─────────────────┤
│列表 │                             │      │ Agent + Composer│
│     │ （配置/管理 ← 用户菜单）     │      │                 │
│daemon│                             │      │                 │
│用户 │                             │      │                 │
│rail │                             │      │                 │
└─────┴─────────────────────────────┴──────┴─────────────────┘
  56px 折叠 rail：展开钮 + 圆形博主栈 + daemon 点 + 用户钮
```

| 区域 | 组件 | 数据绑定（实现时） |
|------|------|-------------------|
| 左栏结构 | `.left-rail`（折叠 rail）+ `.left-content`（展开内容） | 768px 下仅 rail |
| 左栏顶 | 标题「监控」+ 折叠 `‹` | — |
| 左栏列表 | `creator-item` + light；直播态 `.avatar-wrap.is-live` | `GET /api/creators`、WS events |
| 左栏底 | **Daemon 卡**（`#daemon-card`）+ `#daemon-log-panel`（5 行 `<pre>`） | `GET /api/daemon`、启停 API |
| 左栏底 | 用户栏 + 弹出菜单 | 系统配置、监控管理 |
| 左 rail | 圆形 `.rail-dot`（40px）；直播态 `.is-live` | 同列表 `data-creator`；点 rail 博主**只切换选中**；`#rail-daemon` 展开左栏；`#rail-user-menu` **只开菜单** |
| 中栏 Tab | 直播 / 历史 | 路由态；回放时历史 Tab 高亮；配置/管理不经 Tab |
| 中栏直播 | **16:9 视窗** + 竖屏 `video-frame` + 录制横幅 | proxy stream、`POST recording/start` |
| 中栏历史 | chip：**全部** / **仅有转写** / **仅有摘要** + `#history-search` + 场次 + 合并组 | `GET .../sessions`、`live_groups` |
| 中栏回放 | 面包屑 + 视窗 + meta | `GET /api/media`、session id |
| 右栏顶 | 标题「内容」+ 折叠 `›` | — |
| 右栏上 | 转写/摘要 Tab | live: WS partial；playback: final 文件 |
| 右栏下 | **Cursor 式 Composer** + chat | PiEvent、`desktop_chat_*`；模型下拉 `#agent-model-select` |
| 列宽 | `#resize-left` / `#resize-right` / `#resize-right-split` | `localStorage` `m2t-desktop-layout` |

---

## 4. 设计令牌（Design Tokens）

实现时写入 Tauri/React theme（与原型 CSS 变量一致）。**以 [finalized.html](../designs/m2t-desktop/finalized.html) 为准**；本文档为摘要。

### 4.1 色彩与主题

根节点 `html[data-theme="light"|"dark"]`；**默认亮色**。配置 · 环境 → `#cfg-theme`：变更后**立即** `applyTheme` + 写 `localStorage` `m2t-desktop-theme`（不必点保存）；撤销配置时随 `configSaved` 还原。

**亮色（默认）：**

```css
--bg-app: #f4f4f5;
--bg-panel: #ffffff;
--bg-elevated: #ececee;
--bg-hover: #e4e4e7;
--border: #d4d4d8;
--text: #18181b;
--text-muted: #52525b;
--accent: #2563eb;
--green: #16a34a;
--yellow: #ca8a04;
--red: #dc2626;
--composer-bg: #ffffff;
--composer-border: #e4e4e7;
--send-bg: #27272a;
--video-stage-bg: #0a0a0c;
```

**暗色：**

```css
--bg-app: #121214;
--bg-panel: #1c1c21;
--bg-elevated: #25252d;
--bg-hover: #2e2e38;
--border: #3f3f48;
--text: #ececef;
--text-muted: #9898a4;
--accent: #3b82f6;
--green: #22c55e;
--yellow: #eab308;
--red: #ef4444;
--composer-bg: #25252d;
--composer-border: #3f3f48;
--send-bg: #ececef;
--video-stage-bg: #0a0a0c;
```

注：HTML 中 `--center-max-w: 1120px` 已定义但**未使用**；中栏宽度由 grid flex 决定，双栏折叠时 `.both-collapsed` 取消 max-width 限制。

| 语义 | 用法 |
|------|------|
| `badge-live` | 🔴 在播未录 |
| `badge-recording` | 🟢 录制中 |
| `flv-badge` | 技术路径提示；**v1 默认隐藏**，仅 `?debug=1` 或 dev 构建显示（M1） |

### 4.2 字体（v1 已锁定）

| 角色 | 字体 | 备注 |
|------|------|------|
| UI | **Geist Sans** 400–700 | 13px 基准；`/plan-design-review` 方案 A |
| 时间戳 / meta / 面包屑 | JetBrains Mono 400–500 | tabular-nums 在实现时开启 |

**实现：** Tauri 打包 `@fontsource/geist-sans` + `@fontsource/jetbrains-mono`（或等效本地子集）；原型用 Google Fonts CDN。回退栈：`Geist, system-ui, sans-serif`。

**非色通道（H3）：** 状态灯旁显示单字缩写，与 `aria-label` 并存：

| 灯色 | 缩写 | `aria-label` 示例 |
|------|------|-------------------|
| green | 录 | 录制中 |
| red | 播 | 在播未录 |
| yellow | 收 | 收尾中 / STT 降级 |
| gray | 离 | 离线 |

### 4.3 间距与圆角

| 令牌 | 值 |
|------|-----|
| `--radius` | 8px |
| `.side-panel-header` / `.center-toolbar` | **44px** 高 |
| 面板 header padding | 0 12–16px（侧栏统一 `.side-panel-header`） |
| 列表项 padding | 8px 10px |
| Agent Composer 外边距 | `.composer` padding `0 14px 14px`（与右栏边缘留白） |
| 按钮 padding | 6px 12px（primary 略大） |

### 4.4 布局尺寸与持久化

| 令牌 / 行为 | 值 |
|-------------|-----|
| `--sidebar-w` | 默认 240px；拖动 **180–420px** |
| `--right-w` | 默认 360px；拖动 **280px – min(50vw, 剩余宽度)** |
| `--right-agent-h` | 默认 320px；右栏内 Agent 区高度 **160–720px** |
| `--grip-w` | 6px（`#resize-left` / `#resize-right`） |
| `--center-min-w` | 100px |
| `--center-edge-pad` | 32px（中栏内容区内边距） |
| Agent 分割上限计算 | `transcriptMin: 100` px（转写区最小高度，参与 `#resize-right-split` max） |
| 左折叠 rail | `--sidebar-collapsed-w` **56px** |
| 右折叠 rail | `--right-collapsed-w` **48px** |
| 网格 | 5 列：`panel-left \| grip \| center \| grip \| panel-right`（子项显式 `grid-column`，避免折叠时中栏错位） |
| 双栏折叠 | `.app.both-collapsed`：中栏 `max-width: none` 占满 |

**localStorage `m2t-desktop-layout`：** `leftCollapsed`、`rightCollapsed`、`sidebarW`、`rightW`、`agentH`。

### 4.5 响应式（原型 CSS）

| 断点 | 行为 |
|------|------|
| `≤1024px` | CSS 默认 `--sidebar-w: 200px`、`--right-w: 300px`（可被拖动覆盖并持久化） |
| `≤768px` | 强制双 rail 布局；隐藏 `.left-content` / `.right-content` 与列 resize；`grid` 为 56px + flex + 48px |

---

## 5. 状态灯与徽章

与 [架构 §4.4](./2026-06-04-m2t-desktop-design.md#44-博主状态灯与手动录制) 一致。

| 灯 | CSS class | 用户文案示例 |
|----|-----------|--------------|
| 🟢 | `.light.green` | 录制中 |
| 🟡 | `.light.yellow` | 收尾中 / STT 降级 |
| 🔴 | `.light.red` | 在播未录 |
| ⚫ | `.light.gray` | 离线 |

选中博主：`.creator-item.selected` + `aria-current="true"`。

**空列表（左栏）：** `monitor_enabled=0` 或 API 返回 `[]` 时显示 `.creator-list-empty`：文案「暂无监控博主」+ 主按钮「添加博主」→ `view-manage`（原型见 `finalized.html` `#creator-list-empty`）。

**直播中头像（🟢 录制 / 🔴 在播）：**

| 态 | 展开列表 | 折叠 rail |
|----|----------|-----------|
| 判定 | `data-light="red"` 或 `"green"` → `.avatar-wrap.is-live` | 同 → `.rail-dot.is-live` |
| 视觉 | 固定 **2px 红色外环** + 角标状态点 | 圆形 **40px**；外环同上 |
| 动效 | 头像 `.avatar-live-breathe`（scale 1↔0.88，2.6s） | rail 内首字 span 同动画 |
| 非直播 | 普通圆形头像 + 角标 | 圆形 40px，无红环 |

rail 选中：蓝色外圈 `box-shadow`（非方形 inset 条）。

---

## 6. 视图状态机（中栏）

| 视图 | `id` | 进入条件 |
|------|------|----------|
| 系统配置 | `view-config` | 左栏用户菜单；信息架构见 [配置/管理 IA](./2026-06-04-m2t-desktop-config-manage-ia.md) |
| 监控管理 | `view-manage` | 左栏用户菜单；博主 CRUD + 运维操作 |
| 直播 | `view-live` | Tab「直播」或选中博主 default `live` |
| 历史 | `view-history` | Tab「历史」或 offline 博主 default |
| 回放 | `view-playback` | 点击场次 / 合并组；Tab 显示历史为 active |

**右栏联动：**

- **直播上下文：** `#transcript-live` + `#chat-live`；摘要 Tab 在 live 下提示固定转写。
- **回放上下文：** `#transcript-playback` / `#summary-playback` + `#chat-playback`；`center-badge` 隐藏。

---

## 7. 组件清单（实现对照）

| 组件 | 原型选择器 / id | React 建议名 |
|------|-----------------|--------------|
| SidePanelHeader | `.side-panel-header` `.side-panel-title` | `SidePanelHeader` |
| DaemonCard | `#daemon-card`（`.left-daemon-wrap`，用户栏**上方**）；`#btn-daemon-stop` 单钮 **⏹/▶** 切换启停；`#btn-daemon-log` 显隐 `#daemon-log-panel`；停止时 `.daemon-card.stopped` + `app.daemon-stopped` | `DaemonCard` |
| CreatorListItem | `.creator-item` | `CreatorListItem` |
| ColumnResize | `#resize-left` `#resize-right` | `ColumnResizeHandle` |
| CenterTabs | `#center-tabs` | `CenterToolbarTabs` |
| LivePlayer | `.video-viewport` + `.video-frame` | `LivePlayer` + flv.js |
| RecordBanner | `#record-banner` | `RecordBanner` |
| HistoryToolbar | `.history-toolbar` · `data-filter="all|transcript|summary"` | `HistoryFilters` |
| ManagePage | `#view-manage` · `#manage-stats` · `data-manage-filter` chips · `#btn-add-creator` | `ManagePage` |
| ManageDrawer | `#manage-drawer`（单例，行下内联；进入管理时默认展开首行） | `ManageDrawer` |
| ConfigAddProvider | `#btn-add-llm-provider`（AI 段可见，撤销/保存左侧） | `ConfigAddProviderBtn` |
| SessionRow | `.session-row` | `SessionListItem` |
| MergedGroupRow | `#merged-row` | `MergedGroupRow` |
| PlaybackChrome | `.breadcrumb-bar` | `PlaybackHeader` |
| TranscriptPane | `.transcript-pane` | `TranscriptPane` |
| RightSplitResize | `#resize-right-split` | `RightSplitResizeHandle` |
| AgentPaneHeader | `.agent-header` `.model-pill` | `AgentPaneHeader` |
| AgentChat | `#agent-form.agent-composer` | `AgentComposer` + `ChatThread` |
| AgentModePill | `#agent-mode-pill` | `AgentModePill` |
| AgentModelSelect | `#agent-model-select` | `AgentModelSelect` |
| AgentContextBtn | `#agent-ctx-btn` | `AgentContextBtn` |
| AgentAttachBtn | `#agent-attach-btn` | `AgentAttachBtn` |
| ToolResultCard | `.tool-card` | `ToolResultCard` |
| ThemeSelect | `#cfg-theme` | `ThemeSelect` |
| Toast | `#toast` | `Toast` / sonner |

### 7.1 系统配置视图（`view-config`）

**入口：** 左栏用户菜单 → 系统配置；中栏 toolbar 显示 `context-settings` 标题「系统配置」（无博主名 / badge）。

**布局：**

```
┌ settings-head-inner（居中 max 640px）────────────────────┐
│ [环境][监控][直播][AI]                    [撤销][保存]   │
├ settings-scroll（flex 居中）───────────────────────────┤
│ #config-form（max-width 640px）                         │
└──────────────────────────────────────────────────────┘
```

| 分段 | 内容 |
|------|------|
| 环境 | **界面主题**（亮色/暗色）、通知提示音、环境自检（`data-config-panel="user"`） |
| 监控 | **全局调度**四字段（直播检测 / 作品同步 / 每轮博主数 / 并行扫描）+ 抖音·B 站 `.platform-config-card`（各平台独立轮询 + 登录态） |
| 直播 | 管线、实时转写（引擎下拉）、摘要、云盘卡、Webhook 通知 |
| AI | Provider 行列表 + 详情页；顶栏添加 Provider；Agent 默认 |

### 7.2 Agent Composer（Cursor 式）

```
┌ agent-composer（圆角边框，距右栏边缘 ~14px）─────────────┐
│ textarea「继续提问…」                                      │
├──────────────────────────────────────────────────────────┤
│ ∞ Agent ▾ │ Auto ▾（#agent-model-select）│ ◎ │ 📎 │ ⬆发送 │
└──────────────────────────────────────────────────────────┘
```

| 元素 | 说明 |
|------|------|
| `.agent-header` / `.model-pill` | 对话区顶栏；pill 显示当前 Provider · 模型（如 `nvidia · auto`） |
| `#agent-mode-pill` | Agent 模式（实现期扩展） |
| `#agent-model-select` | 模型下拉：Auto + LLM 列表（与配置 AI 段同步） |
| `#agent-ctx-btn` | 上下文（原型 Toast） |
| `#agent-attach-btn` | 附件（原型 Toast） |
| `#btn-agent-send` | 圆形发送钮；`textarea.agent-composer-input` 自动增高（max 120px） |

**组件（原型选择器）：**

| 组件 | 选择器 | 说明 |
|------|--------|------|
| ConfigSegments | `#config-segments` | 四段 Tab |
| ConfigSaveBar | `#btn-config-save` `#btn-config-revert` `#config-save-hint` | 脏检测 + 保存/撤销 |
| ConfigForm | `#config-form` `[data-cfg]` `[data-cfg-toggle]` | `configDraft` ↔ 表单 |
| PlatformConfigCard | `.platform-config-card` | 媒体平台：轮询 + 状态 + 登录 |
| LlmProviderCard | `.llm-provider-card` | Base URL / Key / 模型列表 |
| AuthLoginBtn | `[data-auth-login]` | 平台登录（监控=媒体；直播=云盘） |

**v1 交互：** 表单编辑 + 保存/撤销；不展示配置文件路径。见 [配置 IA §3](./2026-06-04-m2t-desktop-config-manage-ia.md)。

---

### 7.3 直播视频视窗

| 层 | 选择器 | 说明 |
|----|--------|------|
| 外框 | `.video-viewport` | **16:9**；`width: min(100%, 960px, calc((100vh - 220px) × 16/9))`；中栏居中 |
| 内框 | `#view-live .video-frame` | **9:16 竖屏流**在 16:9 视窗内垂直居中（抖音/B 站竖屏） |
| 回放视窗 | `#view-playback .video-viewport` | 同 16:9 结构；边框 `rgba(59,130,246,0.3)` 区分回放 |
| 技术标 | `.flv-badge` | 原型默认可见；实现建议 debug 隐藏（见 UI 审视 M1） |

---

## 8. 原型交互范围

`finalized.html` 含 **原型级** 交互（非真实 API）：

- 左右栏折叠、**三列 + 右栏上下拖动手柄**、博主切换、中栏 Tab、录制横幅、历史筛选/搜索、场次回放、合并摘要、右栏 Tab、复制、Agent 发送、**主题切换**、Toast 反馈。
- **布局持久化**：`m2t-desktop-layout`（折叠 + 三档宽度）。
- **直播头像**：`syncRailDots()` 同步 `.is-live` 与 rail 角标。
- 脚本：**普通 `<script>`** 保证 `file://` 可点；**`pretext.js`** 仅在 `http(s)` 下加载（动态排版）。

本地预览：

```bash
cd docs/superpowers/designs/m2t-desktop
python3 -m http.server 8766
# 打开 http://127.0.0.1:8766/finalized.html
```

---

## 9. 与 Tauri 实现差异（ intentional gaps）

| 原型 | 实现 |
|------|------|
| 静态示例文案 | API + manifest 真数据 |
| 视频占位 | flv.js / `<video>` |
| Agent 追加气泡 | PiEvent 流 + ToolResultCard |
| 配置保存 Toast | `PATCH /api/config` 真落盘 |
| 管理 sync/remove | 真实 API（原型为 Toast） |
| `#detail-open-profile` | Tauri 打开 `profile_url` |
| `#btn-copy-transcript` | 剪贴板；读已加载 transcript 文本 |
| `#btn-open-merged` | `/api/media` 或本地 summary 路径 |
| `data-manage-filter` | 客户端筛选；API 仍返回全量 `?all=1` |
| 手动停止录制 | **无中栏按钮**；API + Agent tool；v1.1 可加 UI |
| `#agent-ctx-btn` / `#agent-attach-btn` | 实际上下文与附件能力 |
| Geist 来自 CDN / fontsource | Tauri 打包本地字体；禁止 v1 默认 Inter |

---

## 10. 决策日志

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-06-04 | 三栏 + 状态灯（默认亮色） | 对齐架构规格与长时间监控场景 |
| 2026-06-04 | 历史与回放独立视图 | D9/D10；右栏 final 转写 |
| 2026-06-04 | Agent 占右栏下半 | 边看边问；与 scmclaw 一致 |
| 2026-06-04 | 原型入库 `docs/superpowers/designs/` | 与 superpowers 规格同仓、可版本化 |
| 2026-06-04 | 系统配置可编辑表单 | 保存/撤销、中文标签、无 yaml 路径；见 §7.1 |
| 2026-06-04 | **以 finalized.html 为 UI 真源** | 规格随原型迭代同步 |
| 2026-06-04 | 默认亮色 + 暗色主题 | `#cfg-theme` + `data-theme` |
| 2026-06-04 | Daemon 移至左栏底（用户栏上） | 5 行日志 + 图标停/日志切换 |
| 2026-06-04 | 列宽拖动 + 右栏 ≤50vw | 竖屏直播给中栏留空间 |
| 2026-06-04 | 16:9 视窗 + 竖屏流 | `.video-viewport` / `.video-frame` |
| 2026-06-04 | Cursor 式 Agent Composer | 模型下拉 Auto + 圆钮发送 |
| 2026-06-04 | 监控段字段与 HTML 对齐 | 全局四字段 + 平台卡独立 poll；非「单一直播间隔」 |
| 2026-06-04 | Daemon 单钮 ⏹/▶ 启停 | 非 disabled；日志 `#btn-daemon-log` 独立切换 |
| 2026-06-04 | **v1 UI 字体 Geist Sans** | 设计审视 H1；方案 A |
| 2026-06-04 | 状态灯缩写 录/播/收/离 + `aria-label` | 设计审视 H3；色盲可辨 |
| 2026-06-04 | `flv-badge` 默认隐藏 | 设计审视 M1 |
| 2026-06-04 | 左栏空列表 CTA | 设计审视；`#creator-list-empty` |

---

**Agent 约束：** 实现 `apps/m2t-desktop` 任何 UI 前须读 **[finalized.html](../designs/m2t-desktop/finalized.html)**（UI 真源）+ 本文 + [UI 审视](./2026-06-04-m2t-desktop-ui-review.md)；视觉/交互变更须先改原型再同步本文。
