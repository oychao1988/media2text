# 转注 Work — Electron 桌面壳

Issue [#35](https://github.com/oychao1988/media2text/issues/35)（P0）+ [#37](https://github.com/oychao1988/media2text/issues/37)（P1）：聊天 UI + **自动拉起 OpenClaw Gateway** + 首次向导。

## 普通用户

1. 安装 **Node.js ≥ 22.14**（推荐 [nvm](https://github.com/nvm-sh/nvm)）与 **OpenClaw CLI**（YonClaw 或 `npm i -g openclaw`）。
2. 在项目目录执行一次 `npm install`（见下方「开发者」）。
3. 双击或运行 `npm run dev` — 应用会：
   - 检测 `127.0.0.1:18789` 是否已有 Gateway；
   - 若无则自动执行 `openclaw gateway run --port 18789 --bind loopback`；
   - 显示「正在启动 OpenClaw Gateway…」直至就绪（最长 60 秒）；
   - 首次运行引导免责声明与 OpenClaw 配置说明。
4. 在聊天框发送消息即可，**无需**单独开终端起 Gateway。
5. 退出应用时，仅终止**本应用启动**的 Gateway 子进程，不影响你手动启动的 Gateway。

若系统找不到 `openclaw`：安装 YonClaw 或 `npm i -g openclaw`，并确保 `openclaw` 在 `PATH` 中。

Gateway 日志（可选）：`~/Library/Logs/转注Work/gateway.log`（macOS）。

## 开发者

### 前置条件

| 项 | 要求 |
|----|------|
| Node.js | **≥ 22.14**（OpenClaw 硬性要求；子进程 PATH 会优先 bundled `resources/node` 若存在） |
| OpenClaw CLI | `which openclaw` 可用 |
| 配置 | `~/.openclaw/openclaw.json` 含 `gateway.auth.token` 与模型 Provider API Key |

Token 读取顺序：

1. 环境变量 `OPENCLAW_GATEWAY_TOKEN`
2. `OPENCLAW_CONFIG_PATH` 或 `~/.openclaw/openclaw.json` → `gateway.auth.token`

**勿**将 token 提交到 git。

### 运行

```bash
source ~/.nvm/nvm.sh
cd desktop/zhuanzhu-work
npm install
npm run dev
```

环境变量：

| 变量 | 说明 |
|------|------|
| `ZHUANZHU_SKIP_SPAWN=1` | 不自动 spawn Gateway（Gateway 已手动运行时使用，E2E 默认） |
| `OPENCLAW_CONFIG_PATH` | 覆盖 openclaw.json 路径 |
| `OPENCLAW_BIN` | 覆盖 openclaw 可执行文件路径 |
| `ZHUANZU_WORKSPACE` | 覆盖合规文件 workspace（默认 `userData/data`） |

若在 Cursor / CI 等环境中设置了 `ELECTRON_RUN_AS_NODE=1`，请先 `unset ELECTRON_RUN_AS_NODE` 再运行 `npm run dev` 或 E2E。

### 验证

1. 停止已有 Gateway 后 `npm run dev` → 应自动起 Gateway 并进入聊天。
2. 发送：`回复两个字：收到` → 应出现助手回复。
3. 对照 HTTP PoC：

```bash
./scripts/openclaw-gateway-http-chat.sh "回复两个字：收到"
```

### E2E 冒烟

```bash
# Gateway 已手动运行，或 SKIP_SPAWN 等待外部 Gateway
ZHUANZHU_SKIP_SPAWN=1 node e2e/gui-smoke.mjs
```

截图参考：`docs/zhuanzhu-e2e-screenshots/`。

## Preload API

```javascript
await window.zhuanzhu.openclaw.chat({
  message: "你好",
  sessionKey: "agent:main:main",
});

await window.zhuanzhu.app.getBootstrap();
await window.zhuanzhu.app.acceptCompliance();
await window.zhuanzhu.app.openConfigDir();
await window.zhuanzhu.app.enterMain();
```

## 目录

```
desktop/zhuanzhu-work/
├── main.js              # Electron main + 启动引导 + IPC
├── lib/
│   ├── gateway.js       # Gateway 健康检查 / spawn / 退出清理
│   ├── config.js        # openclaw.json 读取与向导判定
│   └── paths.js         # 配置路径、合规文件、日志
├── preload.js
├── e2e/gui-smoke.mjs
└── renderer/
    ├── splash.html      # 启动页
    ├── wizard.html      # 首次向导
    ├── index.html       # 聊天主界面
    └── ...
```

## 非目标（P1 不做）

- electron-builder `.dmg` / 内置完整 OpenClaw npm 包（见 P2 Issue #38）
- WebSocket 流式、media2text CLI 集成（P3 Issue #39）

详见 [docs/openclaw-integration.md](../../docs/openclaw-integration.md) 与 [docs/issues/zhuanzhu-p1-bundled-gateway.md](../../docs/issues/zhuanzhu-p1-bundled-gateway.md)。
