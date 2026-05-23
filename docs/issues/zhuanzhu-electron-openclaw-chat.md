# P0 转注 Work Electron 最小壳 + OpenClaw 聊天联调

> **类型**：功能（Spike / P0）  
> **GitHub**：[#35](https://github.com/oychao1988/media2text/issues/35)  
> **建议分支**：`issue-35-zhuanzhu-electron-chat`（实现中）  
> **规格来源**：[docs/openclaw-integration.md](../openclaw-integration.md)、转注 Work 原型 `zhuanzhu-work-20260523/finalized.html`（gstack，保留版）

## 背景

转注 Work 需要验证 **对话框 ↔ 本地 OpenClaw Gateway** 的端到端链路，为后续与 OpenClaw 打包桌面端打基础。Gateway RPC 与 HTTP `/v1/chat/completions` 已通过脚本验证（见 `scripts/openclaw-gateway-*.sh`）。

本单交付 **开发态 Electron 最小壳**：加载转注聊天 UI，经 **preload 代理** 调用 Gateway（避免 Renderer 跨域），用户可发送一条消息并看到助手回复。

## 验收标准

### Electron 壳

- [ ] 新增 `desktop/zhuanzhu-work/`（或等价路径），含 `package.json`、Electron **main**、**preload**、Renderer HTML/CSS/JS。
- [ ] `npm install && npm run dev`（或文档等价命令）可启动桌面窗口；**不**要求本单 bundled OpenClaw / 自动拉起 Gateway。
- [ ] Renderer 为转注 Work **聊天页最小子集**（会话列表可静态占位；composer + 消息区可交互），视觉与 gstack `finalized.html` 聊天区风格一致即可，不必搬全站 IA。
- [ ] 窗口标题含「转注 Work」；footer 保留合规免责声明一句。

### OpenClaw 桥接（preload）

- [ ] preload 暴露 `window.zhuanzhu.openclaw.chat({ message, sessionKey? })`（命名可微调，须在 Issue PR 说明）。
- [ ] 实现走 **HTTP** `POST http://127.0.0.1:18789/v1/chat/completions`（main/preload 发请求，Bearer token）；**不**要求本单 WebSocket `chat.send` 流式。
- [ ] Token 读取顺序：`process.env.OPENCLAW_GATEWAY_TOKEN` → 读 `~/.openclaw/openclaw.json` 的 `gateway.auth.token`（**勿**提交 token 到 git）。
- [ ] Gateway 不可达时 UI 显示可读错误（如「请先启动 openclaw gateway run」），不白屏崩溃。

### 聊天联调

- [ ] 用户在 composer 输入文字并发送 → 界面追加 user 气泡 → 等待后追加 assistant 气泡（可非流式）。
- [ ] 默认 `sessionKey`：`agent:main:main`（常量或 preload 可配置即可）。

### 文档

- [ ] `desktop/zhuanzhu-work/README.md`：前置条件（nvm Node ≥22.14、Gateway 启动命令）、开发运行、验证步骤。
- [ ] 在 [docs/openclaw-integration.md](../openclaw-integration.md) 增加一节「Electron 开发壳」指向上述 README（简短链接即可）。

## 验证命令

```bash
# 终端 1：Gateway（需 nvm Node ≥22.14）
source ~/.nvm/nvm.sh
openclaw gateway run --port 18789 --bind loopback

# 终端 2：Electron
cd desktop/zhuanzhu-work
npm install
npm run dev
# 手动：窗口内发送「回复两个字：收到」，应看到助手回复

# 可选：对照 HTTP PoC
cd ../.. && ./scripts/openclaw-gateway-http-chat.sh "回复两个字：收到"
```

## 非目标范围

- bundled OpenClaw、安装包 `.dmg` / `.exe`、LaunchAgent 修复（见 openclaw-integration 另开单）。
- WebSocket `chat.send` 流式、多 agent 切换、万战/档案 skill 映射。
- 搬移 gstack 全量 `finalized.html` 非聊天页面（监控守护、档案检索等）。
- preload 调用 `media2text` CLI。
- CI 必须跑 Electron（本单可不加上游 CI job；本地验证即可）。

## 待确认问题

- 无（P0 spike 范围已收窄；若 gstack 原型路径不可读，用 Issue 内最小聊天 HTML 自建）。

## 实现提示（给修单 Agent）

- 参考 [openclaw-desktop](https://github.com/agentkernel/openclaw-desktop) 的 preload/loopback 模式，但 **最小 diff**，勿 fork 整仓。
- `contextIsolation: true`，禁用 nodeIntegration in renderer。
- 将 UI 资产放在 repo 内（`desktop/zhuanzhu-work/renderer/`），勿依赖 `~/.gstack/...` 运行时路径。
- PR 正文：`Fixes #<N>`；不提交 `node_modules/`、`.env`、gateway token。
