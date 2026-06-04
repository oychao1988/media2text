# m2t-desktop P9：`finalized.html` UI 1:1 视觉复刻

## 背景

P5–P7 已交付三栏布局与功能面板，但与 UI 真源 [`finalized.html`](../superpowers/designs/m2t-desktop/finalized.html) 仍存在系统性视觉/结构差距：约 **80 个原型 CSS class 未移植**、右栏 Agent 非 Cursor 风格 composer、历史回放 IA 与原型不一致、若干关键动效与 warning 样式缺失。

本单目标：**DOM 层级 + class/id + CSS 与 `finalized.html` 1:1 对齐**（功能接线已在 P6/P7 完成的部分保持行为不变）。对照方法：并排打开原型与 `pnpm --filter m2t-desktop tauri dev`，按下方清单勾选。

**参考**

- UI 真源：[finalized.html](../superpowers/designs/m2t-desktop/finalized.html)
- UI 规格：[ui-design.md](../superpowers/specs/2026-06-04-m2t-desktop-ui-design.md)
- 配置 IA：[config-manage-ia.md](../superpowers/specs/2026-06-04-m2t-desktop-config-manage-ia.md)
- 验收 U1–U15：[ui-review.md](../superpowers/specs/2026-06-04-m2t-desktop-ui-review.md)
- 架构（回放/预览语义）：[m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md) §8

## 验收标准

### Phase A — CSS 基础设施（P0）

- [x] 从 `finalized.html` `<style>` 移植缺失块至 `apps/m2t-desktop/src/styles/layout.css`（或按模块拆分），至少覆盖：
  - 右栏：`.agent-pane`、`.row-resize`、`.chat-scroll`、`.msg-*`、`.tool-card-header/body`、composer 全套（`.agent-mode-pill`、`.agent-send-btn` 等）
  - 直播：`.record-banner` / `.record-banner-text`（红底警告）、`.video-overlay-top`
  - 动效：`@keyframes avatar-live-breathe`、`.avatar-wrap.is-live`、`.rail-dot.is-live`
  - 历史/回放：`.breadcrumb-bar`、`.playback-meta`、`.session-main`、`.session-size`、`.merged-row`、`.merge-badge`
  - Toast：底部居中单条 `.toast` / `.toast.show`（替换或对齐现有 `.toast-host`）
- [x] 删除或收敛实现独有、与原型冲突的样式（如 `.history-layout` 分栏、`.right-agent-shell`、`.agent-msg--*`），改为原型 class 名
- [x] `tokens.css` 与原型 `:root` 变量一致（含 `--right-agent-h`、`--grip-w`、`--center-min-w: 25vw`、全局 scrollbar 变量等）

### Phase B — 右栏转写 + Agent（P0）

- [x] `AppShell` 右栏 DOM 对齐原型：
  ```
  right-content.right-split
    panel-header（折叠 ›）
    section.transcript-pane
    div#resize-right-split.row-resize
    section.agent-pane
  ```
- [x] 实现 `#resize-right-split` 拖拽，持久化 `--right-agent-h` / store `agentH`（与原型 `SIZE_LIMITS.agent` 一致）
- [x] `SidePanelHeader`：左栏 `‹`、右栏 `›`
- [x] `AgentPanel`：`.agent-header` + `.model-pill`；消息区 `.chat-scroll` + `.msg-user` / `.msg-assistant` + `.thinking` + `.tool-card`
- [x] `AgentComposer`：textarea 在上、toolbar 在下；`∞ Agent` pill、model select、上下文/附件 icon、圆形 SVG send（非文字「发送」按钮）
- [x] `ToolResultCard` 改为 `.tool-card-header` + `.tool-card-body` 布局（可保留折叠，但视觉与原型一致）

### Phase C — 中栏直播 + 录制条（P0）

- [x] `LivePlayer`：`video-overlay-top` 包裹 `flv-badge`，文案含 API 路径提示（与原型同类，非仅 `FLV`）
- [x] 无 session / 在播未录：占位态（▶ + 双行说明）视觉对齐 `#view-live` placeholder，而非仅 error 卡片
- [x] `.record-banner` 使用原型红底/红字样式（`rgba(239,68,68,0.08)`、`#fca5a5` 标题）

### Phase D — 历史与回放 IA（P0）

- [x] 移除 `.history-layout` 左右分栏；`#view-history` 为**全宽列表**（含 `.session-size`、完整 `.tag` 体系：`ok`/`miss`/`fail`/`cloud`、`streaming` 等）
- [x] 合并组：日期标题内 `.merge-badge` + `.merged-row` + `#btn-open-merged`（对齐原型 DOM）
- [x] 新增独立 `#view-playback`：`breadcrumb-bar`（`#back-to-history`）+ `.playback-meta` + 全宽播放器；Esc / 返回按钮回到历史列表
- [x] 选中历史场次时切换 center view 至 playback（非内嵌 side panel）

### Phase E — 左栏与全局细节（P1）

- [x] `.is-live` 呼吸环在 `CreatorList` / `LeftRail` 可见且与原型一致
- [x] Daemon：日志按钮 `▤` + `.daemon-log-toggle`；meta 文案含 `LiveTick` 间隔与队列计数（字段来自 API 已有数据）
- [x] 用户栏：去除硬编码「Oychao」；`.user-meta` / `.user-chevron` 样式对齐（`userDisplay.ts` + 菜单宽度随侧栏）
- [x] Toast 位置与动画：底部居中、单条、`translateX(-50%)`

### Phase F — 配置与监控管理 UI shell（P1，可先静态后接线）

- [x] `#view-config`：`settings-head-inner`、`.settings-save-hint`、`config-panel-footer`、各段 `.field-row` + `.hint`
- [x] 配置段缺失块 UI shell：platform 卡片、streaming STT、summarize、aliyundrive、LLM Provider CRUD（`#btn-add-llm-provider`、`.provider-detail`；`connected` 探测见 API）
- [x] `#view-manage`：`.manage-row-pills` / `.manage-auto-pill`、`.manage-drawer-collapse`、radio 副标题 `<span>`；抽屉单例 + 窄栏 `@container` 响应式

### 质量

- [x] `pnpm --filter m2t-desktop test` 全绿；更新/新增 Vitest 覆盖：`SidePanelHeader` 折叠方向、`ViewPlayback` 路由、composer / layout smoke（28 tests）
- [ ] PR 描述附 **before/after 截图**（右栏 Agent、record-banner、历史/playback、is-live 四处至少各 1 张）— 建议合并前 `tauri dev` 人工补图
- [ ] [ui-review.md](../superpowers/specs/2026-06-04-m2t-desktop-ui-review.md) U1–U15 中与布局/视觉相关项重新勾选（后续专项）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pnpm install

pnpm --filter m2t-desktop test
pytest tests/unit/test_api_config_dto.py tests/unit/test_api_health.py -m desktop -q
pnpm --filter m2t-desktop tauri dev

# 原型对照（另开终端）
cd docs/superpowers/designs/m2t-desktop && python3 -m http.server 8766
# http://127.0.0.1:8766/finalized.html
```

**人工对照清单（PR 必附勾选结果）**

1. [x] 右栏：composer 布局、send 按钮、tool-card、row-resize 拖拽
2. [x] 直播：record-banner 颜色、flv-badge 位置、placeholder
3. [x] 历史：行 tag/size/merged-row；点击进入 playback 全屏视图
4. [x] 左栏：is-live 红环呼吸、daemon ▤
5. [x] Toast：底部居中

## 非目标范围

- **不**在本单新增后端 API（红态 creator 级预览流若缺 API，playback placeholder 先做 UI shell，另开 API issue）
- **不**重写 Agent sidecar 协议或 tool 语义（仅 UI 呈现对齐）
- **不**改 `AppBootstrap` 启动流程逻辑（样式可微调但不删除 Tauri 特有 boot）
- **不**在本单完成 config/manage 全部字段的业务校验与保存（Phase F 允许先 UI shell + 已有字段接线）
- **不**强制 pixel-perfect 于不同 OS 字体渲染；以 class/DOM/色值/spacing 一致为准

## 依赖与顺序

- **依赖**：[#130](https://github.com/oychao1988/media2text/issues/130) 布局壳、[#131](https://github.com/oychao1988/media2text/issues/131) 功能面板、[#132](https://github.com/oychao1988/media2text/issues/132) Agent UI（均已交付）
- **联调**：[#133](https://github.com/oychao1988/media2text/issues/133) P8 冒烟可在本 PR 合并后继续

## 待确认问题

- [ ] 红态「在播未录」预览：是否已有 creator 级 stream API？若无，Issue 是否拆 `#preview-stream-api` 子任务？
- [x] Toast：保留多 toast 队列还是严格单条替换？→ **已采用单条**（与原型一致）

## 交付摘要（2026-06-05）

**视觉 / 结构**

- `layout.css` 大规模对齐 `finalized.html`：右栏 Agent、直播 overlay/record-banner、历史 playback、配置/管理 shell、全局 scrollbar、列/行 resize 手柄
- `AppShell` / `CenterToolbar` / `HistoryPanel` / `ViewPlayback` / `ManagePage` / `ConfigForm` + `ConfigAiPanel` DOM & class 对齐
- `useRowResize` / `useColumnResize`：持久化 `--right-agent-h`、侧栏/中栏/右栏宽度；中栏 `min-width: 25vw`

**联调修复**

- 配置/管理/回放 → 点左栏博主回直播或历史（离线默认历史 Tab）
- `CreatorsContext` 静默 refresh，消除 daemon/列表闪烁
- `HistoryPanel` per-creator 缓存，切换博主无整页「加载历史…」
- `ManagePage` 抽屉：flex 下列表内联展开、`@container` 窄栏重排、监控开关乐观更新 + silent reload
- `desktopInputGuards`：壳层禁用框选/右键；输入框与右栏转写/Agent 区保留原生文本交互
- Sidecar：`cors.py` loopback CORS；`config_dto` LLM provider `connected` GET 探测 + 单测

**测试**

- `pnpm --filter m2t-desktop test` — 28/28
- `pytest tests/unit/test_api_config_dto.py tests/unit/test_api_health.py -m desktop` — 9 passed

## 实现备注

- GitHub Issue: [#143](https://github.com/oychao1988/media2text/issues/143)
- 分支：`issue-143-m2t-desktop-p9-ui-parity`
