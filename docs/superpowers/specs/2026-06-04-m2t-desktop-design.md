# media2text Desktop — Tauri 监控控制台

**日期:** 2026-06-04  
**状态:** 已批准（开放项 1–4 已锁定，2026-06-04；实现逻辑与 [finalized.html](../designs/m2t-desktop/finalized.html) 同步）  
**前置:** [media2text README](../../../README.md)、[streaming STT 规格](./2026-06-03-live-streaming-stt-design.md)  
**用户:** 个人自用（本机单 workspace）

**UI 设计（已入库）：**

| 文档 | 说明 |
|------|------|
| [UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md) | Tokens、组件、视图状态机 |
| [UI 设计审视](./2026-06-04-m2t-desktop-ui-review.md) | 对齐度、问题清单、验收建议 |
| [可交互原型](../designs/m2t-desktop/finalized.html) | 本地：`cd docs/superpowers/designs/m2t-desktop && python3 -m http.server 8766` |
| [配置/管理 IA](./2026-06-04-m2t-desktop-config-manage-ia.md) | 用户 / 博主 / 系统三层 + 两 Tab 分工 |

---

## 0. 已锁定决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 集成方式 | **FastAPI HTTP + WebSocket sidecar**，Tauri **不调 CLI** | 实时推送、流代理、AI 聊天需长连接与细粒度控制 |
| 页面结构 | **单页三栏**（类 Cursor），左右栏可折叠 | 监控态 + 视频 + 字幕同屏 |
| 左栏 | 博主列表 + 状态灯 + **底栏 Daemon** | 一眼识别谁在录 |
| 中栏 | **直播 / 历史** Tab + WebView 内嵌直播·录播；**系统配置 / 监控管理**经左栏用户菜单 | 主操作区 |
| 右栏 | 上：转写/摘要 Markdown；下：**AI 对话框** | 边看边读边问 |
| 直播画面 | **flv.js + API 反向代理 HTTP-FLV**（不转 HLS、不重编码） | 浏览器不支持原生 FLV；代理解决 Referer/Cookie |
| 本地 growing FLV | **不播放** | 未完成文件无法可靠解码；与 ffmpeg 录制文件解耦 |
| 实时字幕 | 读 `.transcript.partial.json` + **WebSocket 推送** | streaming 模式默认 30s flush；segment 级更新 |
| 录播回放 | 完整 `.flv`（flv.js）或 `.mp4`（`<video>`）经 API 静态提供 | 与现有 sidecar 路径一致 |
| AI | 复用 `summarize.llm` OpenAI 兼容端点；**系统配置 · AI 段**可编辑 Provider；上下文注入当前 session transcript/summary | 配置经 `PATCH /api/config`；Agent sidecar env 热更新 |
| 平台 v1 | 抖音 + B 站（读现有 DB / manifest） | 用户已在用双平台 |
| 打包 v1 | **macOS 开发机**优先；Windows/Linux defer | 个人自用 |
| API 端口 | **`127.0.0.1:8765`**（固定默认） | 用户确认 |
| 🔴 在播未录 | **v1 必须**；中栏提供 **手动开始录制** | 现实状态；非每场都自动录 |
| 自动开录 | **`live.auto_record: true`（默认）** | 与现网 daemon 一致；手动录制为补充 |
| AI 历史 | **SQLite 持久化**（按 chat thread） | 重启后保留 |
| AI 参考实现 | **scmclaw-v2** Agent 模式（pi-sidecar + skills + tools） | 非纯 chat SSE；预留 skill 扩展 |
| AI 运行时 | **Node `m2t-agent-sidecar`**（`@earendil-works/pi-coding-agent`） | 与 scmclaw `packages/pi-sidecar` 同构 |

未选方案（备查）：

- **CLI 子进程封装** — 无法优雅做 WS、FLV 代理、AI 流式响应  
- **Tauri Rust 直读 SQLite** — 业务逻辑重复、与 daemon 漂移  
- **ffmpeg → 本地 HLS** — 非必要转封装，延迟与复杂度更高  
- **Growing 本地 FLV 播放** — 不稳定  
- **外链平台 iframe 播放器** — 登录/CORS/合规 fragile  

---

## 1. 问题陈述

现有 media2text 能力完整但 **交互分散在终端**：

1. daemon 是否在跑、谁在录、队列是否积压 — 需记命令组合  
2. 实时转写落在磁盘 partial 文件 — 无同屏可视化  
3. HTTP-FLV 直播源无法直接在浏览器 `<video>` 播放  
4. 摘要/转写与 LLM 问答割裂  

用户期望：**单窗口**完成监控总览、内嵌直播、实时字幕、AI 追问。

---

## 2. 目标（Success Criteria）

| ID | 指标 | 验收 |
|----|------|------|
| D1 | 打开 app ≤ 3s 内看到 daemon 状态与博主列表 | 冷启动 sidecar + 首屏 API |
| D2 | 选中「录制中」博主 ≤ 5s 内中栏出画面 | FLV 代理 + flv.js 首帧 |
| D3 | partial 更新后 ≤ 5s 右栏转写刷新（默认 flush 30s + WS） | 对比 partial mtime |
| D4 | Agent 首 token ≤ 10s | PiEvent `message.assistant.delta` |
| D4b | 「帮我总结这场直播」类请求可触发 tool 读 transcript | 集成测试 mock LLM + tool |
| D5 | 左右栏折叠状态重启后保留 | localStorage |
| D6 | API 不破坏现有 CLI / daemon 行为 | 写操作经 API 复用 core（配置 PATCH、博主 CRUD），不绕过 daemon 语义 |
| D7 | 🔴 状态下点击「开始录制」≤ 10s 进入 🟢 | `POST .../recording/start` + session 出现在 DB |
| D8 | 重启 app 后恢复上次 session 的 AI 对话 | `desktop_chat_*` 表可读 |
| D9 | 离线博主历史 Tab ≤ 2s 列出最近 20 场 | `GET .../sessions` |
| D10 | 点击历史场次 ≤ 3s 右栏 final 转写首屏 | `/api/media` + transcript GET |

---

## 3. 非目标（v1 不做）

- 替代 `monitor watch` 守护进程逻辑（仍独立进程）  
- 在 app **WebView 内嵌** Playwright 扫码（仍通过 API/Tauri **spawn** `media2text auth login` 或等价子进程）  
- 编辑/保存转写或摘要正文  
- 内嵌全文检索（archive search / FTS）  
- 飞书 **events 矩阵** UI（v1 仅有总开关 + Webhook 字段，见 [配置 IA §3.3](./2026-06-04-m2t-desktop-config-manage-ia.md#33-直播)）  
- 多 workspace / 远程部署  
- App Store 签名与自动更新  

---

## 4. 架构

### 4.1 进程模型（双 Sidecar + Agent）

```
┌──────────────────────────────────────────────────────────────────┐
│  Tauri App (WebView + Rust)                                       │
│  · 启动/停止 Python API + Node Agent sidecar                        │
│  · fetch/WS → :8765 ；stdin/stdout NDJSON → Agent sidecar          │
│  · emit("agent-event") 转发 PiEvent → React                         │
└────────────┬───────────────────────────────┬───────────────────────┘
             │ HTTP/WS :8765                  │ NDJSON stdin/stdout
┌────────────▼──────────────┐    ┌───────────▼──────────────────────┐
│  media2text API (Python)   │    │  m2t-agent-sidecar (Node)         │
│  FastAPI + uvicorn         │◀───│  pi-coding-agent + skills + tools │
│  · creators/daemon/live    │    │  tools → HTTP 调 :8765            │
│  · FLV proxy / media       │    │  skills → packages/agent-skills/  │
│  · transcript WS           │    │  buildSystemPrompt + 当前 session  │
│  · chat threads 持久化      │    │  无业务 REST（不做 chat 推理）     │
└────────────┬──────────────┘    └──────────────────────────────────┘
             │ import
┌────────────▼──────────────┐    ┌──────────────────────────────────┐
│  media2text.core.*         │    │  monitor watch --daemon（已有）    │
└────────────┬──────────────┘    └──────────────────────────────────┘
             │
┌────────────▼──────────────────────────────────────────────────────┐
│  data/ — media2text.db, sessions/, creators/*, partial transcripts   │
└─────────────────────────────────────────────────────────────────────┘
```

**职责拆分（重要）：**

| 组件 | 职责 | 不做 |
|------|------|------|
| **Python API** | 业务状态、文件、FLV 代理、daemon、**chat thread/message 落库** | LLM 推理、tool 循环 |
| **Agent sidecar** | LLM + **skill 加载** + **tool 执行** + 流式 PiEvent | 直接读 DB / 写磁盘（经 tools 调 API） |
| **Tauri** | 双 sidecar 生命周期、IPC 桥接 | 业务逻辑 |

**启动顺序：**

1. Tauri spawn Python API → `GET /api/health` OK  
2. Tauri spawn `m2t-agent-sidecar`（env：`M2T_API_BASE_URL=http://127.0.0.1:8765`、LLM profiles/keys、当前 creator/session context）  
3. Agent emit `ready` → UI 可发消息  

**Sidecar 启动：**

- Python：`{venv}/python -m media2text.api`（或 `media2text serve`），`127.0.0.1:8765`  
- Agent：`node packages/m2t-agent-sidecar/dist/main.js`（开发态 via `resources/agent/start-sidecar.mjs`，对齐 scmclaw `pi_sidecar.rs`）  

**与 daemon 关系：** 不变 — API 读/写 DB；daemon 独立进程；Agent tools 可 `POST /api/daemon/start`、`POST .../recording/start` 等。

### 4.2 UI 布局（单页三栏）

**UI 真源：** [finalized.html](../designs/m2t-desktop/finalized.html) · 细节见 [UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md)。

```
┌─[◀]──────────────────────────────────────────────────[▶]─┐
│ ┌──────────┐ ┌─────────────────────┐ ┌──────────────────┐ │
│ │ 监控列表  │ │ 博主 + badge        │ │ 内容 [转写|摘要]  │ │
│ │ (avatar) │ │ Tab: 直播|历史       │ │ Markdown 只读     │ │
│ │   🟢     │ │ 16:9 视窗 + 竖屏流   │ ├──────────────────┤ │
│ ├──────────┤ │                     │ │ Agent Composer   │ │
│ │ Daemon   │ │ （配置/管理←菜单）   │ │ ∞ Agent ▾ Auto ▾ │ │
│ │ 用户栏   │ │                     │ │ [输入区] [发送]   │ │
│ └──────────┘ └─────────────────────┘ └──────────────────┘ │
└───────────────────────────────────────────────────────────┘
  grip 列可拖：左 180–420px；右 280px–min(50vw, 剩余)
```

| 区域 | 行为 |
|------|------|
| 左栏顶 | 标题「监控」+ 折叠；博主列表 |
| 左栏底 | **Daemon**（`#daemon-card`，用户栏**上方**）：PID、post_process 摘要；`#btn-daemon-stop` **单钮** ⏹/▶ 启停；`#btn-daemon-log` 切换 5 行 `#daemon-log-panel` |
| 左栏底 | 用户栏 → 系统配置 / 监控管理 |
| 左 rail | 圆形博主点（40px）；直播 `.is-live` 红环呼吸；`#rail-daemon` 展开左栏；`#rail-user-menu` 只开菜单；rail 博主点只 `selectCreator` |
| 状态灯 | 见 §4.4；red/green → `.is-live` 呼吸环；yellow 无红环 |
| 中栏 | **直播 / 历史** Tab；配置/管理经用户菜单；直播：16:9 视窗 + 🔴 横幅；历史 → 回放 |
| 右栏上 | Tab 转写/摘要；直播 WS 增量；历史 session 读 final |
| 右栏下 | **Cursor 式 Composer** + `.agent-header` / `.model-pill` + chat；`#agent-model-select`、`#agent-ctx-btn`、`#agent-attach-btn`；上下分界 `#resize-right-split` |
| 折叠 / 尺寸 | 左/右折叠；`localStorage` `m2t-desktop-layout`：`leftCollapsed`、`rightCollapsed`、`sidebarW`、`rightW`、`agentH` |
| 主题 | 默认亮色 `data-theme="light"`；`#cfg-theme` 即时生效 + `m2t-desktop-theme`；撤销配置可还原 |
| 响应式 | `≤1024px` 默认 200/300 列宽；`≤768px` 强制双 rail（见 UI 设计 §4.5） |

### 4.3 直播播放（WebView + flv.js）

```
WebView (flv.js)
    GET /api/sessions/{id}/stream/proxy
         │
         ▼
FastAPI ──httpx stream──▶ 平台 HTTP-FLV URL
         （注入 Referer / Cookie from sessions）
```

| 场景 | 源 | 播放器 |
|------|-----|--------|
| 直播中 | 平台 `stream_url`（API 代理） | flv.js |
| 录播 FLV | `GET /api/media?path=...` 静态只读 | flv.js |
| 录播 MP4 | 同上 | `<video>` 原生 |

**stream_url 刷新：** 代理 403/404 时 API 调 `resolve_stream_url(room_id, sec_uid)` 重试；仍失败则 UI 降级为「仅字幕」+ 提示。

**带宽：** 代理为第二路拉流（与 ffmpeg 录制并行）；个人可接受。

### 4.4 博主状态灯与手动录制

| 灯 | 语义 | 判定 |
|----|------|------|
| 🟢 绿 | 正在录制 | `live_sessions` 活跃且 `ffmpeg_pid` 存活 |
| 🟡 黄 | 直播相关中间态 | `offline_since_at` 已设（收尾中）；或 STT degraded |
| 🔴 红 | **平台在播但未录** | `creator_live_snapshots.is_live=1` 且无 active recording |
| ⚫ 灰 | 离线 | `is_live=0` 或无 snapshot |

**在播快照（新增 DB 表 `creator_live_snapshots`）：**

- daemon LiveTick 每次 poll 后 upsert（`creator_id`, `is_live`, `room_id`, `title`, `checked_at`）  
- sidecar 在 daemon 未跑时，`GET /api/creators` 可对 `monitor_enabled` 博主 **按需 refresh**（调 `get_live_room`，限流 ≥30s/creator）  
- 经 `WS /api/events` 推送灯变更  

**手动录制（v1 必须）：**

| 项 | 说明 |
|----|------|
| 触发 | 选中 🔴 博主 → 中栏主按钮 **「开始录制」** |
| API | `POST /api/creators/{id}/recording/start` |
| 实现 | 复用 `LiveRecordingCore`：`get_live_room` → `_start_recording`（封装为公开 `start_recording_for_creator`） |
| 前置 | 博主已登记；平台 `is_live`；无 active session；平台 session 有效 |
| daemon | **必须运行**（或 API 先 `daemon/start`）：finalize / offline 检测仍靠 LiveTick `poll_active_recordings` |
| 冲突 | 若已有 active session → 409；若未 live → 409 + `not_live` |
| 可选停止 | `POST /api/creators/{id}/recording/stop` → 触发 finalize（等价提前下播）；**v1 中栏无停止按钮**（Agent tool `m2t_stop_recording` 或 v1.1 UI） |

**与自动录制的 coexistence：**

- 全局配置 `live.auto_record`（默认 **`true`**，与现网一致）  
- `false` 时：daemon poll 只更新 `creator_live_snapshots`，**不**调用 `_start_recording`；用户仅通过 Desktop 手动开录  
- `true` 时：行为与 today 相同；🔴 仍可能出现（daemon 未开、开录失败、刚开播尚未 poll）  

**博主级覆盖（v1，DB + 管理 UI）：**

| 字段 | 值 | 含义 |
|------|-----|------|
| `creators.auto_record_override` | `inherit`（默认） | 跟随全局 `live.auto_record` |
| | `on` | 检测到直播即开录（即使全局为 false） |
| | `off` | 仅手动 `recording/start` |

**daemon 开录决策（实现约定）：**

```python
def effective_auto_record(creator, config) -> bool:
    o = creator.auto_record_override  # inherit | on | off
    if o == "on":
        return True
    if o == "off":
        return False
    return bool(config.live.auto_record)
```

仅当 `monitor_enabled=1` 且平台在播时调用；手动开录不受 `off` 限制（用户显式触发）。

**🔴 态 UI：**

- 中栏可 **flv.js 预览**（仅代理流，无本地文件）  
- 右栏转写区显示「未开始录制」；开录后切 partial WS  

### 4.5 实时转写

- 源文件：`{media}.transcript.partial.json`（streaming）或 final `.transcript.md`  
- `TranscriptWriter` 默认 `flush_interval_sec: 30`（用户 config）  
- API：`GET /api/sessions/{id}/transcript`  
- WS：`/api/sessions/{id}/transcript/stream` — watchdog 或 2s mtime poll，payload `{ segments[], text, partial: true }`  
- finalize 后自动切 final md/json  

### 4.5a 历史直播浏览（v1 必须）

**数据源（已有，不新造索引）：**

| 来源 | 字段 | 用途 |
|------|------|------|
| `live_sessions` | `id`, `started_at`, `ended_at`, `status`, `local_path`, `pipeline_mode`, `transcribe_status` | 场次列表、时长、状态 |
| `agent-manifest.json` → `live[]` | `media_path`, `transcript_path`, `summary_path` | sidecar 路径、转写/摘要有无 |
| `live_groups[]` | `date`, `summary_path`, `session_ids[]` | 跨段合并摘要（`summarize merge` 产物） |

**中栏 Tab：直播 | 历史**（配置 / 管理 **不在 Tab**，经左栏用户菜单；默认选中博主时：**有 active session → 直播**，否则 **历史**）

```
历史 Tab（选中博主后）
┌─────────────────────────────────────────────────────────┐
│ [全部] [仅有转写] [仅有摘要]          🔍 搜索日期…        │
├─────────────────────────────────────────────────────────┤
│ ▼ 2026-06-03  合并组 · 3 段                              │
│   ├─ 📄 20260603_merged.summary.md          [打开摘要]   │
│ ▼ 2026-06-02                                             │
│   ● 21:04–23:22 · 2h18m · completed · ✓转写 ✓摘要 · 1.2GB│
│   ○ 19:10–19:45 · 35m · completed · ✓转写 · 480MB        │
│   ○ 14:02–14:08 · 6m · failed · 无媒体                   │
└─────────────────────────────────────────────────────────┘
```

**选中历史场次后（同页，不换路由）：**

| 区域 | 行为 |
|------|------|
| 中栏顶 | 面包屑 `博主名 › 2026-06-02 21:04` + 「返回列表」 |
| 中栏主 | `GET /api/media?path=…` 播 **MP4**（`<video>`）或 FLV（flv.js）；显示 duration、文件大小、云备份状态 |
| 右栏 | 加载该 session 的 `.transcript.md` / `.summary.md`（只读）；Agent `context.refresh` 绑定 `sessionId` |
| 左栏灯 | 仍反映**当前** live/recording 态，与历史浏览无关 |

**交互规则：**

- 列表按 `started_at DESC`；同日内多场用时间范围 + 时长一行展示  
- `live_groups` 折叠组置顶（按 `date` 降序）；组内 `session_ids` 可展开看多段  
- 无 `local_path` 或文件已删（云备份后 `delete_local_after_upload`）：行显示「仅云端」或「媒体不可用」，仍可看转写/摘要若 sidecar 在  
- 搜索 v1：客户端 filter（日期字符串 + session id）；**不做** archive FTS（仍非目标）  
- 双击 / Enter：进入回放；Esc / 「返回列表」：回到历史列表  

**API（增补）：**

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/creators/{id}/sessions` | `?limit=50&offset=0&has_transcript=&has_summary=&status=`；合并 manifest + DB 字段 |
| GET | `/api/creators/{id}/live-groups` | `agent-manifest.json` 的 `live_groups`（或合入上者 `groups` 字段） |

**Agent tool（增补）：** `m2t_list_sessions` → `GET /api/creators/{id}/sessions`；`m2t_read_transcript` 已支持按 session。

**Success criteria 增补：** D9 — 选中离线博主 → 历史 Tab ≤ 2s 列出最近 20 场；D10 — 点击场次 ≤ 3s 右栏出现 final 转写首屏。

### 4.6 AI Agent（pi-sidecar + Skills，对齐 scmclaw-v2）

**模式：Agent（非纯 Chat SSE）。** v1 即采用 `@earendil-works/pi-coding-agent` 工具循环，便于后续挂载 **SKILL.md**。

**参考项目：** `/Users/Oychao/Documents/Projects/scmclaw-v2` — 直接复用其 IPC / 事件 / sidecar 生命周期模式。

| scmclaw-v2 | media2text desktop |
|------------|-------------------|
| `packages/pi-sidecar` | `packages/m2t-agent-sidecar`（fork 适配） |
| `packages/agent-skills/{ozon,erp}` | `packages/agent-skills/media2text/`（+ 后续子 skill） |
| `scmclaw_*` tools → Nest API | `m2t_*` tools → **Python API :8765** |
| `buildSystemPrompt()` org/shop | `buildSystemPrompt()` creator/session/transcript 路径 |
| Tauri `pi_sidecar.rs` NDJSON | Tauri `agent_sidecar.rs`（同构） |
| `usePiSidecar` + `PiEvent` | `useM2tAgent` + 共享 `PiEvent` schema |
| UI 消息 localStorage | **SQLite** `desktop_chat_*`（经 Python API 同步） |

#### 4.6.1 Skills 目录（v1 起）

```
packages/agent-skills/
  media2text/
    SKILL.md              # 总览：monitor、creator、transcript、manifest、合规
    references/
      cli-cheatsheet.md   # 常用 API 映射（非 CLI 直调说明）
  monitor/SKILL.md        # v1 可选拆分：daemon、录制、状态灯
  transcript/SKILL.md     # 读转写/摘要、merge、suggested_groups
```

- 加载：`DefaultResourceLoader` + `agent.json` → `defaultSkills: ["media2text"]`（与 scmclaw `config.ts` 同模式）  
- 打包：Tauri `resources/agent-skills/` 随 app 分发（对齐 scmclaw desktop resources）  
- **Skill 只描述能力与 tool 用法**；执行一律走 `m2t_*` tools，不在 skill 内复制业务规则  

#### 4.6.2 Agent Tools（v1）

Tools 定义于 `packages/m2t-agent-sidecar/src/m2t-tools.ts`，内部 `fetch(M2T_API_BASE_URL + ...)`：

| Tool | 说明 |
|------|------|
| `m2t_get_live_status` | `GET /api/live/status` |
| `m2t_list_creators` | `GET /api/creators` |
| `m2t_get_creator` | `GET /api/creators/{id}` |
| `m2t_start_recording` | `POST /api/creators/{id}/recording/start` |
| `m2t_stop_recording` | `POST /api/creators/{id}/recording/stop` |
| `m2t_daemon_start` / `m2t_daemon_stop` | daemon 启停 |
| `m2t_read_transcript` | `GET /api/sessions/{id}/transcript` |
| `m2t_read_summary` | 读 session 对应 `.summary.md`（API 封装） |
| `m2t_read_manifest` | `GET /api/creators/{id}/manifest` |
| `m2t_list_sessions` | `GET /api/creators/{id}/sessions` |

每个 tool `execute` 后 `emitToolResult`（scmclaw 同构），UI 可展示 **ToolResultCard**（v1 简版 text；v2 富 UI）。

#### 4.6.3 IPC 与 PiEvent

**Desktop → Agent（stdin NDJSON）：**

```json
{ "type": "message.user", "payload": { "text": "...", "providerId": "...", "model": "auto" } }
{ "type": "context.refresh", "payload": { "creatorId": "...", "sessionId": "...", "threadId": "..." } }
```

**Agent → Desktop（stdout NDJSON → Tauri `agent-event`）：**

复用 scmclaw `PiEvent` 子集：`turn.start` / `turn.phase` / `message.thinking` / `message.assistant.delta` / `tool.result` / `turn.end` / `error` / `ready`。

#### 4.6.4 上下文注入

`context.refresh` 或每条 user message 前 `reloadContext()`：

- 环境：`M2T_WORKSPACE`、`M2T_CREATOR_ID`、`M2T_SESSION_ID`、`M2T_API_BASE_URL`  
- System prompt：博主名、session 时间、transcript/summary **路径**（大正文由 tool 按需读取，避免撑爆 context）  
- 合规：个人研究档案、非投资咨询（与 README 免责声明一致）  

#### 4.6.5 消息持久化（SQLite + Agent 内存）

| 层 | 存储 | 说明 |
|----|------|------|
| UI 可见历史 | SQLite `desktop_chat_messages` | 用户要求重启保留 |
| Pi agent 内部 turn | sidecar 进程内存 | 与 scmclaw 相同；sidecar 重启后靠 SQLite 历史 + system prompt 续聊 |
| 同步时机 | `turn.end` | `useM2tAgent` 将 user/assistant（含 `thinkingText`）POST 到 Python API |

Thread CRUD 仅走 **Python API**（Agent 不直接写 chat 表）。

#### 4.6.6 Provider / 模型

- LLM 配置：**系统配置 · AI 段**编辑 `summarize.llm.providers`（`PATCH /api/config` 落盘）→ Tauri 在保存成功后 **reload Agent sidecar env**（`M2T_LLM_PROFILES`、`M2T_LLM_KEYS`，对齐 `SCMCLAW_LLM_*`）  
- Agent 默认模型 / 上下文上限：`desktop.chat.default_model`、`desktop.chat.max_context_chars`（与 `#cfg-agent-model`、`#cfg-max-context` 对应）  
- Per-thread / Composer：`#agent-model-select` 覆盖当前 thread（`PATCH /api/chat/threads/{id}`）；`auto` 时用 scmclaw `resolveAutoModel`  
- v1 API key：`.env` / `api_key_envs`；表单密码框**留空表示不修改**；v2 可选 Tauri keyring  

#### 4.6.7 前端 UI

| 组件 | 参考 scmclaw | media2text |
|------|--------------|------------|
| Hook | `usePiSidecar.ts` | `useM2tAgent.ts` |
| 布局 | `ChatThread.tsx` chat-foot | 右栏底部 **AgentComposer**（Cursor 式） |
| 流式 | `activeTurn` | 同构 |
| Tool UI | `ToolResultCard.tsx` | v1 折叠 JSON/text |
| Markdown | `ChatMarkdown` | assistant 消息渲染 |

#### 4.6.8 DB 表（chat 持久化 + live snapshot）

```sql
-- 由 daemon / API poll 写入
CREATE TABLE creator_live_snapshots (
  creator_id TEXT PRIMARY KEY,
  is_live INTEGER NOT NULL DEFAULT 0,
  room_id TEXT,
  title TEXT,
  checked_at TEXT NOT NULL,
  FOREIGN KEY (creator_id) REFERENCES creators(id)
);

CREATE TABLE desktop_chat_threads (
  id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  session_id TEXT,
  title TEXT,
  provider_name TEXT,           -- maps summarize.llm.providers[].name
  model TEXT DEFAULT 'auto',    -- 'auto' or concrete model id
  context_mode TEXT DEFAULT 'both',  -- transcript | summary | both
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (creator_id) REFERENCES creators(id),
  FOREIGN KEY (session_id) REFERENCES live_sessions(id)
);
CREATE INDEX idx_dct_session ON desktop_chat_threads(session_id);

CREATE TABLE desktop_chat_messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  role TEXT NOT NULL,           -- user | assistant | system | tool
  content TEXT NOT NULL,        -- user/assistant 文本；tool 为 JSON 摘要
  thinking_text TEXT,           -- optional, from thinking models
  duration_ms INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY (thread_id) REFERENCES desktop_chat_threads(id)
);
CREATE INDEX idx_dcm_thread ON desktop_chat_messages(thread_id, created_at);
```

**`creators` 表增补（同批 migrate）：**

```sql
ALTER TABLE creators ADD COLUMN auto_record_override TEXT NOT NULL DEFAULT 'inherit';
-- CHECK (auto_record_override IN ('inherit','on','off'))  — 应用层校验即可
```

迁移：在 `storage/db.py` 现有 migrate 链追加 `_migrate_desktop_v1`。

### 4.7 配置增补（`config.yaml` / `config.example.yaml`）

字段映射以 [配置 IA §3](./2026-06-04-m2t-desktop-config-manage-ia.md#3-系统配置视图布局建议) 与 [finalized.html](../designs/m2t-desktop/finalized.html) 为准。Desktop 新增/暴露：

```yaml
live:
  auto_record: true   # 默认 true；false = 仅手动开录（可被博主 override 覆盖）

desktop:
  api_port: 8765
  theme: light        # light | dark；与 localStorage m2t-desktop-theme 双写
  chat:
    default_model: auto
    max_context_chars: 24000
```

`live.auto_record` **默认 `true`**（代码 default + example 显式写出）。

#### 4.7.1 `GET` / `PATCH /api/config`

**GET** 返回 UI 表单所需**非敏感**子集 + 占位状态：

| 类别 | 示例键 | GET 行为 |
|------|--------|----------|
| 监控调度 | `live.live_poll_interval_sec`、`monitor.vod_*`、`live.scan_concurrency` | 数值 |
| 平台 poll | `platforms.douyin.*`、`platforms.bilibili.*` | 数值 |
| 直播管线 | `live.pipeline_mode`、`live.streaming_stt.*`、`live.auto_record` | 值 + 枚举 |
| 摘要 / 云盘 | `summarize.*`、`aliyundrive.*` | 开关 + provider 名；**不**返回 api key 明文 |
| 通知 | `notify.enabled`、`notify.sound` | 布尔 |
| 飞书 | `notify.feishu.webhook_url` | 若已配置返回 `"***"` 或 `configured: true` |
| 密钥 env | `DEEPGRAM_API_KEY` 等 | `configured: true/false` |
| LLM | `summarize.llm.providers[]` | name、base_url、models[]；**不含** key |
| Desktop | `desktop.theme`、`desktop.chat.*` | 值 |

**PATCH** body：与 GET 同结构的**部分更新**（deep merge 到内存 config → 校验 → 写 `config.yaml` + 必要时 `.env` 占位键）。

| 规则 | 说明 |
|------|------|
| 密码 / Webhook 留空 | **不修改**磁盘上已有值 |
| Webhook 空字符串且显式 `clear_feishu_webhook: true` 或专用 sentinel | 清空飞书 URL |
| 校验失败 | 400 + 字段级 error；**不写盘** |
| 成功响应 | `{ ok, requires_daemon_restart?: string[], requires_agent_reload?: string[] }` |

**`requires_daemon_restart`（非 exhaustive，实现以 diff 为准）：**

- `live.pipeline_mode`
- `live.streaming_stt.enabled` / `engine`（若 daemon 已跑 streaming session）

**`requires_agent_reload`：**

- `summarize.llm.providers` 任意变更
- `desktop.chat.default_model` / `max_context_chars`

#### 4.7.2 配置生效矩阵（与 UI 文案一致）

| UI 控件 / 键 | 存储 | 生效时机 |
|--------------|------|----------|
| `#cfg-theme` | `desktop.theme` + `localStorage` `m2t-desktop-theme` | **立即** UI；保存时落盘；撤销还原 |
| `notify.sound` | `config.yaml` | 保存后下一通知 |
| 监控全局 poll / VOD batch / `scan_concurrency` | `config.yaml` | 下一轮 daemon tick |
| 平台卡 poll | `platforms.*` | 下一轮对应 tick |
| `live.auto_record` | `config.yaml` | 下一次 poll 开录决策 |
| `auto_record_override` | **DB** `creators` | 下一次 poll（该博主） |
| `pipeline_mode`、streaming STT 大改 | `config.yaml` | **重启 daemon**（UI callout） |
| `flushIntervalSec`、`offlineConfirmSec` | `live.streaming_stt.*` / `live.offline_confirm_sec` | 下一场录制 / 下一轮 offline 判定 |
| `streamingSttModel` | `transcribe.*.model` | 下一场 streaming STT 连接 |
| `summarizeProviderId` / `summarizeModel` | `summarize.llm.default_*` | 下一场 summarize 任务 |
| `summarize.*`、`aliyundrive.*` | `config.yaml` | 下一场后处理 / 下次 upload |
| `notify.enabled`、飞书 Webhook | `config.yaml` / env | 保存后下一事件 |
| LLM Provider / Agent 默认 | `config.yaml` | 保存后 **reload Agent sidecar** |
| 列宽 / 折叠 | `localStorage` only | 立即；**不经 API** |

平台登录（`[data-auth-login]`）：**不**经 PATCH；`POST /api/auth/login/{platform}`  spawn CLI 或打开终端（见 §5）。

#### 4.7.3 UI 字段 ↔ `config.yaml` 完整映射

`GET/PATCH /api/config` JSON 使用与 [finalized.html](../designs/m2t-desktop/finalized.html) `CONFIG_DEFAULTS` **相同的 camelCase 键**；服务端读写时映射下表 yaml 路径。完整控件 id 见 [配置 IA §3](./2026-06-04-m2t-desktop-config-manage-ia.md#3-系统配置视图布局建议)。

| API / `data-cfg` 键 | `config.yaml` 路径 | 备注 |
|---------------------|-------------------|------|
| `theme` | `desktop.theme` | 与 `localStorage` `m2t-desktop-theme` 双写 |
| `notifySound` | `notify.sound` | |
| `livePollInterval` | `live.live_poll_interval_sec` | 0 时读 `monitor.live_poll_interval_sec` |
| `vodPollInterval` | `monitor.vod_poll_interval_sec` | |
| `maxCreatorsPerVodTick` | `monitor.max_creators_per_vod_tick` | |
| `scanConcurrency` | `live.scan_concurrency` | |
| `douyinLivePoll` | `platforms.douyin.live_poll_interval_sec` | **Desktop 新增**；0 = 回退 `live.live_poll_interval_sec`（与 B 站对称） |
| `douyinPollInterval` | `platforms.douyin.poll_interval_sec` | VOD / catalog |
| `biliLivePoll` | `platforms.bilibili.live_poll_interval_sec` | 0 = 回退 global live poll |
| `biliArchivePoll` | `platforms.bilibili.archive_poll_interval_sec` | |
| `biliDynamicPoll` | `platforms.bilibili.dynamic_poll_interval_sec` | |
| `pipelineMode` | `live.pipeline_mode` | |
| `autoRecord` | `live.auto_record` | **Desktop 新增** |
| `streamingSttEnabled` | `live.streaming_stt.enabled` | |
| `streamingSttEngine` | `live.streaming_stt.engine` | |
| `streamingSttModel` | 按引擎：`transcribe.deepgram.model` / `transcribe.whisper.model` / `transcribe.openai.model` | UI 单一下拉；PATCH 写对应引擎段 |
| `flushIntervalSec` | `live.streaming_stt.flush_interval_sec` | |
| `offlineConfirmSec` | `live.offline_confirm_sec` | |
| `summarizeEnabled` | `summarize.enabled` | |
| `summarizeProviderId` | `summarize.llm.default_provider` | **Desktop 新增**；值为 `providers[].name` |
| `summarizeModel` | `summarize.llm.default_model` | **Desktop 新增** |
| `aliyunEnabled` | `aliyundrive.enabled` | |
| `aliyunRootFolder` | `aliyundrive.root_folder` | |
| `aliyunDeleteLocal` | `aliyundrive.delete_local_after_upload` | |
| `aliyunUploadSidecar` | `aliyundrive.upload_transcripts` | |
| `notifyEnabled` | `notify.enabled` | |
| `feishuWebhookUrl` | `notify.feishu.webhook_url` 或 env | PATCH 留空不修改 |
| `llmProviders[]` | `summarize.llm.providers[]` | `name`, `base_url`, `api_key_envs`, `models[]` |
| `activeProviderId` | `summarize.llm.default_provider` | Provider 详情「设为默认」与摘要服务下拉同源 |
| `agentModel` | `desktop.chat.default_model` | |
| `maxContextChars` | `desktop.chat.max_context_chars` | |

**只读 / 非 PATCH：** `authDouyin` 等 → `GET /api/auth/status`；`cfg-deepgram-status` / Doctor 行 → `GET /api/health`、`POST /api/doctor/run`。

**实现期 core 增补（与 UI 对齐，非 Desktop 独有语义）：**

- `platforms.douyin.live_poll_interval_sec` + `LiveTick` 读平台 poll（现仅 global）  
- `summarize.llm.default_provider`、`summarize.llm.default_model`（现 summarize 用 providers 首项）  
- `live.auto_record`（见 §4.4）

#### 4.7.4 纯客户端 UI（不经 PATCH）

| 原型控件 | 行为 |
|----------|------|
| `#manage-filter` chips | 客户端筛选 `GET /api/creators?all=1` 结果（`monitor_enabled`） |
| `#detail-open-profile` | `shell.open(creator.profile_url)` |
| `#btn-copy-transcript` | 复制右栏 Markdown 到剪贴板 |
| `#btn-open-merged` | `GET /api/media?path=` 打开合并 `.summary.md` 或系统默认应用 |
| `#agent-model-select` | `PATCH /api/chat/threads/{id}` `{ model }`；与 `#cfg-agent-model` 默认值独立 |
| 布局 / 折叠 | `localStorage` `m2t-desktop-layout`（§4.7.2） |

---

## 5. API 端点（v1）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/health` | sidecar 就绪 + **Doctor 摘要**（ffmpeg / playwright / deepgram extra） |
| POST | `/api/doctor/run` | 重新跑 doctor；更新 health 缓存 |
| GET | `/api/daemon` | lock PID、存活、post_process / running 计数、LiveTick 间隔摘要 |
| GET | `/api/daemon/logs` | `?tail=5` — 读 `data/monitor-watch.log` 末尾行（Daemon 卡 `#daemon-log-panel`） |
| POST | `/api/daemon/start` | spawn `monitor watch --daemon` |
| POST | `/api/daemon/stop` | kill lock PID |
| GET | `/api/creators` | 列表 + 状态灯 + avatar + `live_snapshot`；左栏仅 `monitor_enabled=1` |
| GET | `/api/creators/all` | **可选**：管理列表全量（含未监控）；或 `GET /api/creators?all=1` |
| POST | `/api/creators` | body `{ url, platform? }` → add（长耗时；202 + job id 或 blocking） |
| PATCH | `/api/creators/{id}` | `{ monitor_enabled?, auto_record_override? }` |
| DELETE | `/api/creators/{id}` | `?delete_media=` 可选；二次确认由 UI 负责 |
| GET | `/api/creators/{id}` | 详情 + latest session + live_snapshot + override |
| POST | `/api/creators/{id}/sync-profile` | 包装 profile refresh |
| POST | `/api/creators/{id}/sync` | 包装 `creator sync`（catalog） |
| POST | `/api/creators/{id}/sync-dynamics` | 仅 bilibili |
| POST | `/api/creators/{id}/recording/start` | 手动开录（🔴→🟢） |
| POST | `/api/creators/{id}/recording/stop` | 手动结束当前 active session |
| POST | `/api/creators/{id}/live/refresh` | 强制刷新 live_snapshot |
| GET | `/api/creators/{id}/manifest` | agent-manifest.json |
| GET | `/api/creators/{id}/sessions` | 历史直播列表（分页 + filter） |
| GET | `/api/creators/{id}/live-groups` | 合并摘要组（可选，或合入 sessions 响应） |
| GET | `/api/live/status` | 同 CLI `live status` 字段 |
| GET | `/api/sessions/{id}` | session 元数据 + paths |
| GET | `/api/sessions/{id}/transcript` | partial 或 final |
| WS | `/api/sessions/{id}/transcript/stream` | 转写增量 |
| GET | `/api/sessions/{id}/stream/proxy` | FLV 反向代理 |
| GET | `/api/media` | `?path=` workspace 内相对路径，Range 支持 |
| GET | `/api/config` | 非敏感配置摘要（§4.7.1） |
| PATCH | `/api/config` | 部分更新 + 校验 + 写盘；响应 `requires_daemon_restart` / `requires_agent_reload` |
| POST | `/api/auth/login/{platform}` | `douyin` \| `bilibili` \| `aliyundrive` — spawn `media2text auth login`（Tauri 终端或子进程） |
| GET | `/api/auth/status` | 各平台 session 是否有效（配置卡 `[data-auth-platform]`） |
| GET | `/api/chat/providers` | 从 `summarize.llm` 解析（AI 段 + Composer 下拉） |
| GET | `/api/chat/threads` | 列表 / 按 session 查询 |
| POST | `/api/chat/threads` | 创建 thread |
| PATCH | `/api/chat/threads/{id}` | provider / model / title |
| GET | `/api/chat/threads/{id}/messages` | 历史消息 |
| POST | `/api/chat/threads/{id}/messages` | **落库** user/assistant/tool（非 LLM 推理） |
| DELETE | `/api/chat/threads/{id}` | 删除 thread |
| WS | `/api/events` | daemon / 灯 / 录制状态广播 |

**LLM 推理不在 Python API** — 由 Tauri → Agent sidecar stdin；上表 `/messages` POST 仅持久化。

**安全：** 仅监听 `127.0.0.1`；`/api/media` 与文件读路径校验必须在 `workspace` 下，防 `../` 穿越。

---

## 6. 工程结构

```
apps/m2t-desktop/
  src/
    features/agent/         # useM2tAgent, Composer, ToolResultCard
    features/config/        # 四段配置表单、PATCH 脏检测
    features/manage/        # 全量列表、内联抽屉
    agent/                  # start-agent-sidecar.ts（对齐 scmclaw pi-sidecar.ts）
  src-tauri/
    src/agent_sidecar.rs    # NDJSON IPC（fork pi_sidecar.rs）
    resources/agent/
packages/
  m2t-agent-sidecar/        # Node：session, tools, context, emit
  agent-skills/
    media2text/SKILL.md
  shared/                   # PiEvent, LlmProfile（可从 scmclaw shared 精简复制）
src/media2text/api/         # Python FastAPI（config PATCH、daemon logs、auth spawn）
```

**依赖：**

- Python extra `desktop`：`fastapi`, `uvicorn`, `watchdog`（或 `sse-starlette` 若 WS 辅助）  
- Node：`@earendil-works/pi-coding-agent`, `@earendil-works/pi-ai`（与 scmclaw 同版本锁定）  
- 根目录 `pnpm-workspace.yaml` 管理 `packages/*`（或 npm workspaces）

**CLI 入口（可选）：** `media2text serve --port 8765` 便于单独调试 API。

---

## 7. 前端技术栈

| 层 | 选择 |
|----|------|
| 框架 | Tauri 2 + React 18 + TypeScript |
| 样式 | Tailwind CSS |
| 视频 | flv.js + `<video>` |
| Markdown | react-markdown + remark-gfm |
| 状态 | Zustand 或 React Query（API 缓存 + WS 合并） |
| AI 流 | Tauri `listen("agent-event")` + PiEvent 解析 |

**消息类型（含 tool）：**

```typescript
type ChatMessage =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'assistant'; text: string; durationMs?: number; thinkingText?: string }
  | { id: string; role: 'tool'; result: ToolResultPayload };
```

---

## 8. 错误处理

| 场景 | UI |
|------|-----|
| sidecar 未启动 | 全屏「正在启动服务…」/ 重试 |
| daemon 未运行 | `#daemon-card.stopped`；`#btn-daemon-stop` 显示 ▶「启动 monitor watch」 |
| daemon 已运行 | 同钮显示 ⏹「停止 monitor watch」（**非** disabled；原型 `toggleDaemon` 切换） |
| FLV 代理失败 | 中栏占位 +「流不可用，字幕仍更新」 |
| 无 DEEPGRAM / 无 partial | 右栏转写 Tab 显示「等待转写」或 final |
| LLM 失败 | chat 区 toast + 原始 error |
| 未登录平台 | 配置卡 / 管理区「登录 ××」→ `POST /api/auth/login/{platform}`；左栏 stale 标记 |
| PATCH config 校验失败 | 400 toast + 字段高亮；保持 `configDraft` |
| 需重启 daemon | 保存成功 toast +「请重启守护进程」；可选一键 `POST /api/daemon/stop` + start |

---

## 9. 测试

| 层 | 范围 |
|----|------|
| API unit | 路径校验、状态灯聚合、transcript 读 partial/final、`effective_auto_record`、PATCH config merge |
| API integration | mock FLV upstream；fixture DB + manifest |
| 前端 | 组件测试（Markdown、折叠）；E2E 可选 Playwright against sidecar |
| 手工 | 真实 daemon 录制一场；验证 flv.js + partial WS + chat |

不阻塞 CI：desktop extra 测试标记 `@pytest.mark.desktop`。

---

## 10. 实现顺序（单版本交付，内部分步）

1. **API 骨架** — health/doctor、creators、live/status、`GET/PATCH /api/config`、path-safe media read  
2. **Tauri 壳** — sidecar 生命周期、三栏布局、折叠态、`localStorage` 布局  
3. **左栏** — daemon 启停 + log tail、头像列表、状态灯、WS events  
4. **右栏转写** — transcript REST + WS、Markdown 预览  
5. **中栏视频** — FLV proxy + flv.js；录播 media endpoint  
6. **Agent sidecar** — fork scmclaw pi-sidecar、`m2t_*` tools、首个 `media2text/SKILL.md`  
7. **右栏 Agent UI** — `useM2tAgent`、PiEvent、ToolResultCard、SQLite 同步、Composer  
8. **手动录制** — `creator_live_snapshots`、`auto_record_override`、🔴 态、`recording/start|stop`  
9. **历史直播** — `GET .../sessions`、历史 Tab、录播回放 + final 转写/摘要  
10. **系统配置 UI** — 四段表单、`PATCH /api/config`、主题即时 + 保存落盘、Provider CRUD、auth login 按钮  
11. **监控管理** — 全量列表、筛选、添加博主、内联抽屉、sync/remove、monitor + 开录策略  

估时：**3–4 周**（含 Node agent 包与 Tauri 双 sidecar）。

---

## 11. 风险

| 风险 | 缓解 |
|------|------|
| 平台 FLV URL 鉴权变更 | 代理层集中适配；失败降级字幕-only |
| 双路拉流带宽 | 个人网络；可配置关闭中栏播放 |
| partial 30s 延迟 | 文档说明；可调低 `flush_interval_sec` |
| 🔴 灯需 poll 缓存 | `creator_live_snapshots` + daemon/API 双写 |
| 手动开录无 daemon | UI 提示先启 daemon；或 API 连带 `daemon/start` |
| 双 sidecar 运维 | Tauri 统一 health；API 挂则 Agent tools 失败有明确 PiEvent error |
| Agent 重启丢内存 | SQLite 历史 + context.refresh 续聊 |
| Node + Python 双栈 | pnpm workspace；CI 分别 lint/test |

---

## 12. 已锁定开放项（2026-06-04）

| # | 决定 |
|---|------|
| 1 | API 默认端口 **`8765`** |
| 2 | 🔴 **在播未录** 为 v1 一等状态；中栏 **手动开始录制**；**`live.auto_record` 默认 `true`** |
| 3 | AI **Agent 模式**（pi-sidecar + skills + tools）；对话 **SQLite 持久化** |
| 4 | **配置可写**：`PATCH /api/config` + 博主 **`auto_record_override`**；UI 以 [finalized.html](../designs/m2t-desktop/finalized.html) 为准 |

---

**下一步：** 写 implementation plan（`writing-plans`）；实现 UI 时以 [UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md) + 原型为准。
