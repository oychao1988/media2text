# P4：转注 Work UI 壳迁移（finalized.html IA）

> **GitHub**：[#43](https://github.com/oychao1988/media2text/issues/43)  
> **建议分支**：`issue-43-zhuanzhu-p4-ui-shell`  
> **依赖**：[#39](https://github.com/oychao1988/media2text/issues/39) 已合并

## 背景

P0–P3 交付了 Electron 聊天 + Gateway + dmg + 档案检索/环境检查最小页。产品 IA 仍以 gstack **`finalized.html`** 为源（用户要求保留该版本）。本单把 **侧栏信息架构 + 各能力主区静态页** 迁入 `desktop/zhuanzhu-work/renderer/`，聊天/档案/ doctor 继续可用，其余页面先静态占位并预留 IPC 挂载点。

原型路径：`~/.gstack/projects/oychao1988-media2text/designs/zhuanzhu-work-20260523/finalized.html`  
IA 文档：[docs/zhuanzhu-work-ia.md](../zhuanzhu-work-ia.md)

## 验收标准

### 侧栏与路由

- [ ] 侧栏结构对齐原型：**+ 新消息**、**智能体**（画廊入口）、**能力 ▸** 子菜单（监控守护 / 平台登录 / 技能库 / 流水线 / 通知渠道 / 档案检索 / 合规声明）、底部用户区占位。
- [ ] 点击导航切换主区 `view`；当前项高亮；URL hash 可选（非必须）。
- [ ] **聊天**、**档案检索**、**环境检查（doctor）** 行为不回归：现有 OpenClaw 聊天与 P3 sidecar 功能仍可用。

### 主区页面（静态可交互）

- [ ] **智能体画廊**：4 张卡片（档案助手 / 万战寻道 / 女娲蒸馏 / 默认协调）+「新建智能体」占位；「+ 对话」按钮切到聊天 view（可带 `data-agent` 属性，P6 再接 session）。
- [ ] **监控守护**、**平台登录**、**技能库**、**流水线**、**通知渠道**、**合规声明**：从原型迁移布局与文案；按钮可 disabled 或显示「即将接入 CLI」。
- [ ] **档案检索**：沿用 P3 检索逻辑，视觉对齐原型该页（搜索栏 + 结果列表）。
- [ ] **环境检查**：沿用 P3 doctor 面板，可从「能力」或独立入口进入（与原型「合规/ doctor」语义一致即可）。

### 样式

- [ ] 复用/合并 `finalized.html` 的 CSS 变量与组件类（traffic lights、sidebar、card-agent、config-page 等）到 `renderer/styles.css` 或拆分 `renderer/zhuanzhu.css`；禁止引入构建工具（保持 vanilla HTML/JS）。
- [ ] 窗口圆角/阴影等与原型视觉一致（macOS titlebar 区域可保留 Electron 原生）。

### 文档

- [ ] `desktop/zhuanzhu-work/README.md` 增加「UI 壳（P4）」说明：哪些页已接 CLI、哪些为占位。
- [ ] `docs/issues/README.md` 索引更新。

## 验证命令

```bash
cd desktop/zhuanzhu-work
npm install   # 若未安装
npm run dev

# 手动：
# 1. 侧栏逐项切换，10+ 主区无 JS 报错
# 2. 聊天发「回复两个字：收到」仍成功（Gateway 已配置时）
# 3. 档案检索有 index 数据时能出结果
# 4. 环境检查展示 doctor checks

node --check renderer/app.js
```

## 非目标范围

- WebSocket 流式聊天（P5）
- 多 Agent sessionKey / lens prompt（P6）
- 能力页真正调用 monitor/auth/pipeline CLI（后续 Issue）
- bundled Node/OpenClaw/Python（P7）
- Apple 公证 / 自动更新（P8）
- 删除或替换 gstack 磁盘上的 `finalized.html`
