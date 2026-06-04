# media2text Desktop — UI 设计审视

**日期:** 2026-06-04  
**审视对象:** [finalized.html](../designs/m2t-desktop/finalized.html) · [UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md)  
**对照:** [架构规格](./2026-06-04-m2t-desktop-design.md)

**总评：** 与已批准架构高度一致，信息架构清晰，适合作为 Tauri v1 的视觉与交互蓝本。主要改进点集中在字体辨识度、无障碍与实现期组件边界。**UI 真源为 [finalized.html](../designs/m2t-desktop/finalized.html)**；实现逻辑以 [架构规格 §4.7–§5](./2026-06-04-m2t-desktop-design.md) 为准（2026-06-04 第三轮：配置 PATCH、override、daemon 日志 API）。

---

## 1. 与架构规格对齐度

| 架构要求 | 原型体现 | 评分 |
|----------|----------|------|
| 单页三栏 + 折叠 | ✅ 5 列 grid + left/right collapsed + `both-collapsed` | 10/10 |
| Daemon 摘要 + 启停 | ✅ `#daemon-card` 在 **左栏底**；`#btn-daemon-stop` ⏹/▶ 单钮切换；`#btn-daemon-log` + 5 行 `#daemon-log-panel` | 10/10 |
| 博主灯 🟢🟡🔴⚫ | ✅ `.light.*` + 直播 `.is-live` 红环呼吸 | 10/10 |
| 🔴 手动开始录制 | ✅ `#record-banner` + `#btn-start-record` | 10/10 |
| 中栏 直播/历史 | ✅ Tab + 直播/历史/回放视图（配置/管理经用户菜单） | 9/10 |
| 16:9 视窗 + 竖屏流 | ✅ `.video-viewport` + `.video-frame` | 10/10 |
| 历史场次 + 合并组 | ✅ session rows + merged row | 10/10 |
| 回放面包屑 + 媒体区 | ✅ playback view + 同视窗结构 | 9/10（播放器仍为占位） |
| 右栏转写/摘要 + Agent | ✅ 上下分栏 + **Cursor Composer** + tool-card | 10/10 |
| 列宽拖动 + 持久化 | ✅ `#resize-left/right/right-split` + `m2t-desktop-layout` | 10/10 |
| 右栏 ≤ 半屏 | ✅ `RIGHT_MAX_VIEWPORT_RATIO = 0.5` | 10/10 |
| 亮色/暗色主题 | ✅ `data-theme` + `#cfg-theme` 即时生效 | 10/10 |
| 系统配置可编辑 | ✅ 四段表单 + 保存/撤销/脏检测 | 10/10 |
| 监控管理 | ✅ 全量列表 + chip 筛选 + 顶栏 `#btn-add-creator` + 行下 `#manage-drawer`（默认展开首行）+ 行内开录 pill | 10/10 |
| 直播/回放上下文切换 | ✅ `setLiveContext` / `setPlaybackContext` | 10/10 |

**结论：** 无结构性遗漏；D9/D10 历史路径在原型中可走完。

---

## 2. 做得好的地方

### 2.1 信息层次

- 左栏「**先选博主、底栏确认 daemon**」顺序合理：主任务区在上，全局守护进程与用户入口在下，不抢列表视线。
- 中栏标题 + badge 与左栏选中联动，减少「我在看谁」的认知负担。
- 右栏 **转写在上、Agent 在下** 固定了「先读材料再提问」的节奏；`#resize-right-split` 可拖 Agent 高度（160–720px）。

### 2.2 状态设计

- 🔴 + 录制横幅组合表达「能预览但未落盘」，与规格 §4.4 一致，比单纯灰显列表项更易发现。
- 历史列表用 tag（转写/摘要/失败/云端）+ chip 筛选，信息密度合理，不挤占主时间轴。
- 合并组单独一行（紫色强调）与单场 rows 区分清楚，利于后续 `summarize merge` 心智。

### 2.3 工程友好

- CSS 变量集中，便于一键映射到 React/Tailwind theme。
- 原型交互与普通 script 分离，避免 `file://` 下 module 失败（已修复）。
- `data-*` 属性（creator、session、filter）为 React 组件 props 提供了清晰契约。

### 2.4 容错与降级（原型已暗示）

- 失败场次 `data-failed` + toast 拦截回放，对应规格「无媒体不可播」。
- 直播时点击右栏「摘要」有 toast 说明，避免用户以为实时有 final summary。

---

## 3. 问题与建议

### 3.1 高优先级（实现前建议处理）

| # | 问题 | 建议 |
|---|------|------|
| H1 | **Inter 作主字体** 偏「AI 默认审美」，工具感略弱 | 实现阶段改用 **Geist** 或 **DM Sans** 作 UI，保留 JetBrains Mono 作 meta；或在 DESIGN 中明确「接受 Inter 以降低加载成本」 |
| H2 | ~~配置 / 管理 Tab 无内容~~ | **已解决（2026-06-04）**：用户菜单 → `view-config` / `view-manage`；配置为**四段可编辑表单** + 保存/撤销；管理为全宽列表 + 内联抽屉。实现期对齐 `GET/PATCH /api/config` |
| H3 | **状态仅靠颜色点** 红绿色盲不友好 | 加 `aria-label` / 文案缩写（录/播/离）或图标；规格灯表增加无障碍列 |
| H4 | ~~**右栏高度分配** 未在原型标明 min-height~~ | **已在原型实现**：`--right-agent-h` 默认 320px；`#resize-right-split` 160–720px；转写区 `flex:1; min-height:0` |

### 3.2 中优先级（v1 或 v1.1）

| # | 问题 | 建议 |
|---|------|------|
| M1 | `flv-badge` 技术路径对终端用户噪音大 | 默认隐藏，仅 `debug` 或设置开启 |
| M2 | 左栏仅 4 个博主时尚无搜索 | 博主 >8 时加 filter；与历史搜索 pattern 统一 |
| M3 | Daemon「停止」与博主「停止录制」易混 | 停止 daemon 用「停止守护」；录制用「结束本场」 |
| M4 | Agent tool-card 仅 JSON 文本 | v1 可保持；v2 对齐 scmclaw 折叠/展开与 status |
| M5 | 窄屏响应式 | 原型：`≤1024px` 默认侧栏 200/右栏 300；`≤768px` 强制双 rail、隐藏 grip 与展开内容。Tauri 最小窗口建议 ≥1024 |

### 3.3 低优先级 / 审美

| # | 观察 | 建议 |
|---|------|------|
| L1 | 默认**亮色** + 可选暗色，辨识度优于纯暗色 | 暗色仍偏 Linear/VS Code；RISK 向 accent 或字重微调可选 |
| L2 | 录制按钮全红块略抢眼 | 改为 outline 红 + 实心 hover，或仅图标+文字 |
| L3 | 合并组紫色与 accent 蓝两套强调 | 统一为 accent 系或 `--merge: #a78bfa` token 写入设计系统 |

---

## 4. AI slop 自检

| 反模式 | 原型 |
|--------|------|
| 紫色渐变 hero | ❌ 无 |
| 三列 icon 功能介绍 | ❌ 无 |
| 居中一切 | ❌ 左对齐工具布局 |
| 全圆角 bubble UI | ❌ 8px 克制圆角 |
| Inter + 蓝 accent  cliché | ⚠️ 轻微（见 H1） |

**判定：** 未落入典型 slop；主要风险是 Inter 与蓝 accent 组合的常见度，对自用工具可接受。

---

## 5. 可用性走查（任务流）

| 任务 | 原型步骤 | 摩擦 |
|------|----------|------|
| 确认 daemon 在跑 | 看左栏底 Daemon 卡 + 绿点 | 低 |
| 发现谁在播未录 | 红角标 + 中栏横幅 | 低 |
| 开始录制 | 点「开始录制」 | 低 |
| 看实时转写 | 右栏默认转写 | 低（实现靠 WS） |
| 问 Agent | 底部输入 | 低 |
| 查昨天场次 | 历史 Tab → 筛选 → 点行 | 低 |
| 看合并摘要 | 合并组 / 打开摘要 | 低 |
| 改全局配置 | 用户菜单 → 系统配置 → 编辑 → 保存/撤销 | **低**（四段表单；主题即时生效） |
| 加博主 | 用户菜单 → 监控管理 | **低**（URL + 列表 + 详情抽屉） |

---

## 6. 实现验收建议（UI 专项）

在架构 D1–D10 之外，建议增加 UI 检查项：

| ID | 检查 |
|----|------|
| U1 | 折叠态 rail 可键盘聚焦并切换博主 |
| U2 | 🔴 态录制横幅在 `recording` 开始后 300ms 内消失 |
| U3 | 回放时面包屑与 `session_id` 一致 |
| U4 | `prefers-reduced-motion` 关闭折叠动画 |
| U5 | 右栏 WS 追加转写时不整体闪屏（增量 DOM） |
| U6 | Agent streaming 时 composer 禁用但不丢输入 |
| U7 | 右栏宽度不超过视口 50%；竖屏直播时中栏仍保留 16:9 视窗 |
| U8 | 主题切换即时生效且刷新后保持（`m2t-desktop-theme`） |
| U9 | 直播 red/green 灯时头像与 rail 同步 `.is-live` 呼吸环 |
| U10 | 折叠 rail：`#rail-user-menu` 只开菜单；`#rail-daemon` 展开左栏；rail 博主点只切换选中 |
| U11 | 配置撤销后主题与表单一并还原 |
| U12 | `PATCH /api/config` 落盘后 GET 一致；密码/Webhook 留空不覆盖 |
| U13 | `pipeline_mode` 保存后提示重启 daemon（或 `requires_daemon_restart`） |
| U14 | 管理抽屉 `auto_record_override` 保存后 daemon 下一 poll 生效 |
| U15 | Daemon 卡 `#daemon-log-panel` 与 `GET /api/daemon/logs?tail=5` 同步 |

---

## 7. 审视结论

| 维度 | 分数 | 说明 |
|------|------|------|
| 架构一致性 | 10/10 | 与 finalized.html 同步 |
| 信息架构 | 9/10 | 三栏职责清晰 |
| 视觉一致性 | 9/10 | 双主题 token + 直播动效 |
| 交互完备度（原型） | 9/10 | 拖动/主题/Composer 可点通 |
| 无障碍 | 6/10 | 需补 label/非色依赖 |
| 可实现性 | 9/10 | 组件边界清楚 |

**建议决策：**

- **批准** 本 UI 作为 `apps/m2t-desktop` 实现参照（以 finalized.html 为准）。
- **实现前** 补齐 a11y 灯文案（H3）；字体升级（H1）不阻塞首版。

---

## 8. 相关文件

| 文件 | 用途 |
|------|------|
| [2026-06-04-m2t-desktop-ui-design.md](./2026-06-04-m2t-desktop-ui-design.md) | Tokens、组件、状态机 |
| [designs/m2t-desktop/finalized.html](../designs/m2t-desktop/finalized.html) | 可交互原型 |
| [designs/m2t-desktop/manifest.json](../designs/m2t-desktop/manifest.json) | 产物索引 |
| [2026-06-04-m2t-desktop-design.md](./2026-06-04-m2t-desktop-design.md) | API / sidecar / 行为真源 |
