# m2t-desktop — 配置 / 管理 信息架构

**日期:** 2026-06-04  
**状态:** 已确认（与 [finalized.html](../designs/m2t-desktop/finalized.html) 同步，2026-06-04）  
**关联:** [桌面架构](./2026-06-04-m2t-desktop-design.md)、[UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md)、[UI 审视](./2026-06-04-m2t-desktop-ui-review.md)（H2）

---

## 1. 入口与中栏 Tab 分工

**入口（v1 原型）：** 左栏底部**用户信息栏**（头像 + 用户名占位）→ 点击弹出菜单 → **系统配置** / **监控管理**。用户系统（登录、多账户）v1 不实现。

| 菜单项 | 中栏视图 | 回答的问题 | 典型动作 |
|--------|----------|------------|----------|
| **系统配置** | `view-config` | 「系统/我 按什么规则跑？」 | 查看与修改**全局默认值**、桌面偏好、密钥占位说明 |
| **监控管理** | `view-manage` | 「管哪些博主、现在做什么？」 | **增删博主**、开关监控、登录态、**立即执行**的一次性操作 |

**中栏 Tab（仅博主视图）：** **直播** / **历史** — 不再放置配置、管理 Tab；进入系统配置/监控管理时，toolbar 显示对应标题（`context-settings`），隐藏当前博主名与 badge。

原则：

- **系统配置** = 规则（写入 `config.yaml` / `desktop.*` / `.env` 指引），多数在下次 daemon tick 或新 session 生效。
- **监控管理** = 实体 + 运维（写入 `creators` 表 / 调现有 CLI 等价 API），立刻或短时生效。
- **博主级覆盖**（若未来有）放在 **监控管理 → 博主详情**，不在「系统配置」里混排。

与左栏关系：左栏是**运行时监控入口**（选博主 → 直播/历史）；系统配置/监控管理**不依赖**当前选中博主（管理列表可独立滚动）。

**左栏折叠 rail 交互（以原型为准）：**

| 控件 | 行为 |
|------|------|
| `#expand-left` | 展开左栏 |
| `#rail-daemon` | 展开左栏（便于查看 Daemon 卡与日志） |
| `#rail-user-menu` | **仅**打开用户菜单，**不**展开左栏 |
| `.rail-dot[data-creator]` | 切换选中博主（`selectCreator`），**不**自动展开左栏 |

---

## 2. 三层配置定义

### 2.1 用户配置（User / Desktop）

**作用域：** 本机 Desktop 应用与「你怎么用」；不改变 media2text 核心录制逻辑（除非显式映射到 `desktop.*`）。

**原型「环境」段（`#config-panel-user`）已实现：**

| 字段 | 控件 | 存储 / 生效 |
|------|------|-------------|
| 界面主题 | `#cfg-theme` 亮色/暗色 | 变更后**立即** `applyTheme` + 写 `localStorage` `m2t-desktop-theme`；保存配置时一并落盘；**撤销**还原 |
| 通知提示音 | `#cfg-notify-sound` toggle | `notify.sound`；保存后生效 |
| Doctor | `#cfg-doctor-*` + `#btn-config-doctor` | 只读状态 + 重新检测 |

**布局（非配置表单）：** 左/右折叠与列宽见 `localStorage` `m2t-desktop-layout`（§3.1）；原型**未**在配置页提供「恢复默认布局」按钮。

**实现期扩展（原型未做，仍属用户层）：**

| 分组 | 字段 / 能力 | 存储 | 计划 UI |
|------|-------------|------|---------|
| 工作区 | `workspace` 路径 | `config.yaml` | 只读 +「在 Finder 中打开 `data/`」 |
| 桌面 API | `desktop.api_port` | `config.yaml` | 只读（改端口需重启 sidecar） |
| 快捷入口 | 打开 `config.yaml`、`.env.example` 说明 | — | 按钮（v1.1） |

**Agent 默认** 在 **AI 段**（`#cfg-agent-model`、`#cfg-max-context`），非环境段。

**不做（v1）：** 多用户、主题商店、快捷键编辑器、在 UI 内编辑 `.env` 密钥明文、配置页展示 `config.yaml` / `data/` 路径。

---

### 2.2 博主配置（Creator）

**作用域：** 单个 `creators` 行 + 该平台下的作品/直播行为；在 **管理** 中维护，直播/历史 Tab 只**消费**结果。

| 分组 | 字段 / 能力 | 存储 | v1 UI |
|------|-------------|------|-------|
| 身份 | `platform`, `sec_uid`, `display_name`, `profile_url`, `avatar_url` | DB | 列表 + 详情只读；添加时由 URL 解析 |
| 监控开关 | `monitor_enabled`（合并原 `watch_live`） | DB | 单一「监控」Switch；开=检测直播后走录制/转写/后处理；中栏观看可选 |
| 开录策略 | `auto_record_override`：`inherit` \| `on` \| `off` | DB | 详情区三选一；覆盖全局 `live.auto_record` |
| 资料新鲜度 | `profile_synced_at` | DB | stale 标记 +「同步资料」按钮 |
| 运行时 | 状态灯、`live_snapshot`、active session | DB + 新表 | 左栏展示；详情只读 |
| 作品流水线 | catalog sync、transcribe 队列 | DB + 文件 | 详情区「同步资料」「同步作品」→ API；**v1 原型无「下载待处理」**（v1.1 或 CLI） |
| B 站专属 | `sync-dynamics` 一轮 | — | 按钮（仅 `platform=bilibili`） |
| 危险操作 | `creator remove [--delete-media]` | DB + 磁盘 | 详情底部二次确认 |

**全局默认：** `pipeline_mode`、poll 间隔、STT 引擎等在 **系统配置**；`live.auto_record` 为全局默认，博主可用 `auto_record_override` 覆盖。

**左栏 vs 管理列表：** 左栏仅 `monitor_enabled=1`；**管理列表展示全部已登记博主**（含未开监控）。

---

### 2.3 系统配置（System）

**作用域：** `config.yaml` 全局段；影响 daemon、`monitor watch`、后处理、转写/摘要/云盘/通知。

**原型：** 四段可编辑表单（`#config-form` + 保存/撤销/脏检测）；敏感项密码框留空表示不修改；平台登录为「登录 ××」按钮（非复制 CLI）。**无**独立「转写」分段——流式 STT 在「直播」；legacy 管线下录后转写由 `pipeline_mode` 隐含。

| 区块 | 原型分段 | `config.yaml` 键 | v1 原型 |
|------|----------|------------------|---------|
| 环境 | 环境 | 主题、`notify.sound`、doctor | ✅ 可编辑 |
| 监控 | 监控 | `monitor.*`、`platforms.*` poll | ✅ 可编辑 + 平台卡登录态 |
| 直播 | 直播 | `live.*`、`streaming_stt.*`、`summarize.*`、**`aliyundrive.*`**、`notify.*` | ✅ 可编辑（含云盘卡、飞书 Webhook） |
| AI | AI | `summarize.llm.providers`、Agent 默认 | ✅ Provider CRUD + Agent 默认 |

**AI 相关归并：**

| 用途 | 配置来源 | Desktop 展示位置 |
|------|----------|------------------|
| 直播流式 STT | `live.streaming_stt` + `DEEPGRAM_API_KEY` | **直播** · 实时转写 |
| 录后转写 | `transcribe.*`（legacy 管线） | 无独立 UI；`pipeline_mode=legacy` 时间接生效 |
| 摘要生成 | `summarize.*` + LLM Provider | **直播** · 摘要生成 |
| 云备份 | `aliyundrive.*` | **直播** · 阿里云盘平台卡 |
| 右栏 Agent 对话 | LLM Provider + `#cfg-agent-model` | **AI** · Agent 默认 + 右栏 `#agent-model-select` 覆盖 |

---

## 3. 「系统配置」视图布局（建议）

中栏 **系统配置** 使用**顶部分段**（SegmentedControl），对应 **用户 + 系统**（博主配置在「监控管理」视图）：

```
┌─ 系统配置（中栏居中 max 640px）──────────────────────────┐
│ [环境][监控][直播][AI]                    [撤销][保存]   │
├────────────────────────────────────────────────────────┤
│ 环境：界面主题 + 通知提示音 + 环境自检                               │
│ 监控：全局调度 + 媒体平台卡（抖音/B 站）                  │
│ 直播：管线·STT·摘要·云盘卡·通知（同一段）              │
│ AI：Provider 列表/详情 + Agent 默认                      │
└────────────────────────────────────────────────────────┘
```

**原型对照：** `finalized.html` → `#view-config`、`#config-form`、`PATCH /api/config`（实现期）；组件见 [UI 设计 §7.1](./2026-06-04-m2t-desktop-ui-design.md#71-系统配置视图view-config)。

### 3.1 环境（`data-config-panel="user"`）

- **界面主题**（`#cfg-theme`）：亮色（默认）/ 暗色 → 即时 `data-theme` + `localStorage` `m2t-desktop-theme`（**不必等保存**）；撤销配置时还原  
- 通知提示音（`notify.sound`）  
- Doctor：`ffmpeg` / playwright / deepgram extra + 重新检测  

**布局持久化（非配置表单，仅桌面壳）：** `localStorage` key `m2t-desktop-layout` — `leftCollapsed`、`rightCollapsed`、`sidebarW`（180–420）、`rightW`（280–50vw）、`agentH`（160–720）。见 [UI 设计 §4.4](./2026-06-04-m2t-desktop-ui-design.md#44-布局尺寸与持久化)。

### 3.2 监控

**全局调度**（`#config-panel-monitor` · `.setting-card`「全局调度」）：

| 控件 | 原型 id | 映射键 | 说明 |
|------|---------|--------|------|
| 直播检测间隔 | `#cfg-live-poll` | `live.live_poll_interval_sec` | 守护进程 LiveTick 默认间隔；**不再**分 monitor/live 两栏「回退/优先」 |
| 作品同步间隔 | `#cfg-vod-poll` | `monitor.vod_poll_interval_sec` | SlowTick VOD 轮询 |
| 每轮同步博主数 | `#cfg-vod-batch` | `monitor.max_creators_per_vod_tick` | 每轮 VOD tick 上限 |
| 并行扫描博主数 | `#cfg-scan-concurrency` | `live.scan_concurrency` | 无 active session 时并行 poll |

**媒体平台卡**（`.platform-config-card`）+ 右上角 `[data-auth-platform]` 登录态（未登录「登录」；已登录「已登录 · 重新登录」`auth-inline`）：

| 平台 | 字段 |
|------|------|
| 抖音 | 直播轮询 `#cfg-douyin-live-poll` · 作品列表轮询 `#cfg-douyin-poll` |
| B 站 | 直播 `#cfg-bili-live-poll` · 投稿 `#cfg-bili-archive-poll` · 动态 `#cfg-bili-dynamic-poll` |

段尾 `#config-panel-monitor .config-panel-footer`：「保存后将在下一轮监控周期生效；切换平台登录无需重启守护进程。」

### 3.3 直播

**录制与 STT**（`#config-panel-live` · `.setting-card`）：

| 控件 | 原型 id | 映射键 | 说明 |
|------|---------|--------|------|
| 录制管线 | `#cfg-pipeline-mode` | `live.pipeline_mode` | `legacy` \| `streaming` |
| 全局自动开录 | `#cfg-auto-record` | `live.auto_record` | 默认 true；可被博主 `auto_record_override` 覆盖 |
| 启用实时转写 | `#cfg-streaming-stt` | `live.streaming_stt.enabled` | streaming 管线专用 |
| 转写引擎 | `#cfg-streaming-engine` | `live.streaming_stt.engine` | `deepgram` \| `whisper` \| `openai` |
| 转写模型 | `#cfg-streaming-model` | 见 [架构 §4.7.3](./2026-06-04-m2t-desktop-design.md#473-ui-字段--configyaml-完整映射) | 引擎联动下拉；Deepgram 落 `transcribe.deepgram.model` |
| 片段写入间隔 | `#cfg-flush-interval` | `live.streaming_stt.flush_interval_sec` | partial flush |
| 下播确认 | `#cfg-offline-confirm` | `live.offline_confirm_sec` | finalize 前 offline 等待 |
| Deepgram API | `#cfg-deepgram-status` | `DEEPGRAM_API_KEY` | 只读 `configured`；密钥不进 PATCH |

**摘要**（同段 `.setting-card`「摘要生成」）：

| 控件 | 原型 id | 映射键 |
|------|---------|--------|
| 启用摘要 | `#cfg-summarize-enabled` | `summarize.enabled` |
| 摘要服务 | `#cfg-summarize-provider` | `summarize.llm.default_provider` |
| 摘要模型 | `#cfg-summarize-model-live` | `summarize.llm.default_model` |

**阿里云盘**（`.platform-config-card[data-platform=aliyundrive]`）：

| 控件 | 映射键 |
|------|--------|
| `#cfg-aliyun-enabled` | `aliyundrive.enabled` |
| `#cfg-aliyun-root` | `aliyundrive.root_folder` |
| `#cfg-aliyun-delete-local` | `aliyundrive.delete_local_after_upload` |
| `#cfg-aliyun-upload-sidecar` | `aliyundrive.upload_transcripts` |

**通知**（同段 `.setting-card`「通知」）：`#cfg-notify-enabled` → `notify.enabled`；`#cfg-feishu-webhook` → `notify.feishu.webhook_url`（留空不修改）。无 events 矩阵 UI。  

### 3.4 AI

- **Provider 列表**：一行一 Provider（图标、名称、URL、**连通状态**、编辑/复制/删除）；与 Agent 卡片间距加大；顶栏「添加 Provider」在撤销左侧  
- **Provider 详情**：点击编辑进入；含模型表（LLM / STT）、设为默认 Provider  
- **Agent 默认**：模型、上下文上限  

**v1 交互（桌面）：** 表单直接编辑 + **保存 / 撤销**；`PATCH /api/config` 写回配置（校验后落盘）。界面**不展示** `config.yaml`、`data/`、token 文件等路径；密钥类（Deepgram / 摘要 API）仅显示「已配置 / 未配置」，Webhook 用密码框粘贴（留空表示不修改）。平台登录走「登录 ××」按钮（嵌入终端或浏览器），非复制 CLI。  
**生效说明：** 段尾文案描述业务生效时机（下轮 poll / 重启 daemon），不写文件路径。

---

## 4. 「监控管理」视图布局（v1 原型）

**结构：** 全宽卡片列表；**点击某行**在其正下方展开**内联详情抽屉**（单例 `#manage-drawer`，随选中行移动）。再点**同一行**收起；点**其他博主**时收起上一抽屉并在新行下展开（高度 + 内容淡入，约 320ms）。**进入管理视图**时若尚无选中行，默认展开首个可见行（`showView('manage')` → `openManageDrawerForRow`）。

**顶栏：** `#manage-stats`（已登记 N · 监控中 M）· chip 筛选 `data-manage-filter="all|on|off"`（带计数）· `#manage-add-url` + `#btn-add-creator`。

**列表行：** 头像 + 状态灯 · 平台 tag · 运行时文案 · 行内 `.manage-auto-pill`（继承 / 自动 / 手动 / —）· 行尾监控 toggle（`.manage-monitor-toggle`）。

```
┌─ 监控管理 ───────────────────────────────────────────┐
│ 已登记 N · 监控中 M    [全部][已监控][未监控]          │
│                    [ URL 输入 ………… ] [添加博主]      │
├──────────────────────────────────────────────────────┤
│ ▢ 何同学 …  [继承|始终|仅手动] [监控 toggle]  ← 选中   │
│ ┌─ 详情抽屉（仅此一行下）──────────────────────────┐ │
│ │ 头像·名称 | 监控 | 开录策略 | 运维               │ │
│ └──────────────────────────────────────────────────┘ │
│ ▢ 老番茄 …                                           │
│ ▢ …                                                  │
└──────────────────────────────────────────────────────┘
```

| 操作 | API / CLI 等价 | 备注 |
|------|----------------|------|
| 添加 | `POST /api/creators` `{ url }` | 长耗时；进度 Toast |
| 监控开关 | `PATCH ... monitor_enabled` | 与左栏列表同步 |
| 同步资料 | `POST .../sync-profile` | profile / avatar |
| 同步作品 | `POST .../sync` 或包装 `creator sync` | 30–60s 级 |
| B 站动态 | `POST .../sync-dynamics` | 仅 bilibili；`#detail-sync-dynamics` |
| 打开主页 | — | `#detail-open-profile` → Tauri `open(profile_url)`；无 API |
| 移除 | `DELETE /api/creators/{id}` | 二次确认 |

**与左栏去重：** 左栏 = 已 `monitor_enabled=1` 的**快捷监控**；管理 = **全量博主** + 登记未监控者。**登记新博主**仅在管理顶栏 `#manage-add-url` + `#btn-add-creator`（原型**无**左栏「+」快捷钮）。

---

## 5. 与现有 API 的映射

| 能力 | 端点 | 备注 |
|------|------|------|
| 配置摘要 | `GET /api/config` | 非敏感子集；密钥 `configured` 占位 |
| 配置写入 | `PATCH /api/config` | 校验 + 写 `config.yaml`；响应 `requires_daemon_restart` / `requires_agent_reload` |
| 健康/Doctor | `GET /api/health`、`POST /api/doctor/run` | 环境段 `#btn-config-doctor` |
| Daemon 日志 | `GET /api/daemon/logs?tail=5` | 左栏 `#daemon-log-panel` |
| 平台登录 | `POST /api/auth/login/{platform}`、`GET /api/auth/status` | 配置卡 `[data-auth-login]`；非 PATCH |
| 博主列表（左栏） | `GET /api/creators` | `monitor_enabled=1` |
| 博主列表（管理） | `GET /api/creators?all=1` 或 `/api/creators/all` | 含未监控 |
| 博主 CRUD | `POST /api/creators`、`PATCH /api/creators/{id}`、`DELETE /api/creators/{id}` | PATCH 含 `monitor_enabled`、`auto_record_override` |
| 同步/移除 | `POST .../sync`、`.../sync-profile`、`.../sync-dynamics`、`DELETE` | 包装 CLI |
| Chat providers | `GET /api/chat/providers` | AI 段与 Composer 共用 |

完整表见 [架构 §5](./2026-06-04-m2t-desktop-design.md#5-api-端点v1)。

---

## 6. 版本切片

| 阶段 | 配置 | 管理 |
|------|------|------|
| **v1 原型（当前 HTML）** | 四段**可编辑**表单 + 保存/撤销；无 yaml 路径；主题即时生效 | 全量列表 + 内联抽屉 + 监控/开录策略/运维按钮 |
| **v1 实现** | 对齐原型 + `GET/PATCH /api/config` 真落盘 | 对齐原型 + 博主 CRUD / sync API |
| **v1.1** | workspace 快捷入口、恢复默认布局、更多 doctor 项 | 批量操作 |
| **明确不做** | 飞书 events 矩阵 UI、Playwright 扫码登录、`.env` 内联编辑明文、多 workspace | — |

---

## 7. 已锁定决策（2026-06-04）

| # | 决策 |
|---|------|
| 1 | **做博主级 `auto_record` 覆盖** — `inherit` / `on` / `off`，DB 字段 `auto_record_override`（实现期） |
| 2 | **配置子导航：顶部分段** — **环境 / 监控 / 直播 / AI**（云盘、通知、摘要均在「直播」段内，**无**独立第五段） |
| 3 | **`watch_live` + `monitor_enabled` → 单一「监控」** — 开启后检测直播即走录制·转写·后处理；用户可不打开中栏直播预览 |
| 4 | **管理列表含未开监控博主** — 左栏仅已监控，管理为全量登记 |

**daemon 读规则（实现约定）：** `effective_auto_record = override ?? global`；仅当 `monitor_enabled=1` 且平台在播时触发开录逻辑。

---

## 8. 原型

`finalized.html` 已实现：**可编辑**配置四段 + 保存/撤销 + 管理全量列表 + 博主详情（监控 / 开录策略 / 运维）。**UI 真源：** [finalized.html](../designs/m2t-desktop/finalized.html)。
