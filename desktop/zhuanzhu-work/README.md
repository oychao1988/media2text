# 转注 Work — Electron 开发壳

Issue [#35](https://github.com/oychao1988/media2text/issues/35) 交付：最小 Electron 窗口 + 转注聊天 UI + OpenClaw Gateway HTTP 联调。

## 前置条件

| 项 | 要求 |
|----|------|
| Node.js | **≥ 22.14**（推荐 `nvm`） |
| OpenClaw CLI | 已安装（如 YonClaw / `npm i -g openclaw`） |
| Gateway 配置 | `~/.openclaw/openclaw.json` 含 `gateway.auth.token` |

Token 读取顺序（与脚本一致）：

1. 环境变量 `OPENCLAW_GATEWAY_TOKEN`
2. `~/.openclaw/openclaw.json` → `gateway.auth.token`

**勿**将 token 提交到 git。

## 启动 Gateway

终端 1：

```bash
source ~/.nvm/nvm.sh
openclaw gateway run --port 18789 --bind loopback
```

可选健康检查：

```bash
openclaw health
```

## 启动 Electron 开发壳

终端 2（项目根目录）：

```bash
source ~/.nvm/nvm.sh
cd desktop/zhuanzhu-work
npm install
npm run dev
```

窗口标题为 **转注 Work**。在 composer 输入消息并发送（Enter），应看到 user / assistant 气泡。

## 验证

1. 发送：`回复两个字：收到` → 应出现助手回复。
2. 停止 Gateway 后再发送 → 应显示可读错误（如「请先启动 openclaw gateway run…」），窗口不崩溃。
3. 对照 HTTP PoC（项目根）：

```bash
./scripts/openclaw-gateway-http-chat.sh "回复两个字：收到"
```

## Preload API

Renderer 通过 preload 调用（`contextIsolation: true`，renderer 无 Node 集成）：

```javascript
const result = await window.zhuanzhu.openclaw.chat({
  message: "你好",
  sessionKey: "agent:main:main", // 可选，默认 agent:main:main
});
// { ok: true, content: "..." } 或 { ok: false, error: "..." }
```

实现：`POST http://127.0.0.1:18789/v1/chat/completions`，Bearer token，非流式。

## 目录

```
desktop/zhuanzhu-work/
├── main.js          # Electron main + IPC + HTTP 代理
├── preload.js       # contextBridge → window.zhuanzhu.openclaw.chat
├── package.json
└── renderer/        # 聊天 UI（源自 finalized.html 聊天区子集）
    ├── index.html
    ├── styles.css
    └── app.js
```

## 非目标（本壳不做）

- bundled OpenClaw、安装包、自动拉起 Gateway
- WebSocket 流式、完整 IA、media2text CLI 集成

详见 [docs/openclaw-integration.md](../../docs/openclaw-integration.md)。
