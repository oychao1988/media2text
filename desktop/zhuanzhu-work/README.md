# 转注 Work — Electron 桌面壳

Issue [#35](https://github.com/oychao1988/media2text/issues/35)（P0）+ [#37](https://github.com/oychao1988/media2text/issues/37)（P1）+ [#38](https://github.com/oychao1988/media2text/issues/38)（P2）+ [#39](https://github.com/oychao1988/media2text/issues/39)（P3）+ [#43](https://github.com/oychao1988/media2text/issues/43)（P4）：聊天 UI、Gateway、安装包、media2text sidecar、**finalized.html IA 壳**。

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
| `ZHUANZU_WORKSPACE` | 覆盖 media2text workspace（默认 `userData/data`） |
| `MEDIA2TEXT_BIN` | 覆盖 media2text 可执行文件 |
| `MEDIA2TEXT_CONFIG` | 覆盖 `config.yaml`（默认 `userData/config.yaml`） |

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

## 发布构建（P2 / Issue #38）

将应用打成 macOS `.dmg` 安装包（Windows `.exe` 可选）。**本阶段不内置**完整 OpenClaw npm / portable Node，安装后仍依赖系统 `openclaw` CLI 与 Node ≥22.14；`resources/bundle-manifest.json` 记录未来 pin 版本。

### 前提

| 项 | 要求 |
|----|------|
| Node.js | **≥ 22.14**（与 OpenClaw 一致） |
| macOS | 用于 `package:mac`（本机或 CI macOS runner） |
| 签名 | 未做 Apple 公证；首次打开可能需右键 → 打开 |

### 命令

```bash
source ~/.nvm/nvm.sh
cd desktop/zhuanzhu-work
npm install
npm run prepare-bundle   # 生成 resources/bundle-manifest.json + build/icon.png
npm run package:mac        # 产出 dist/转注 Work-<version>.dmg
# Windows（可选）：npm run package:win
```

若 `npm install` 或 Electron 下载很慢，可开本地代理并配国内镜像：

```bash
export HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890
export ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
export ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
```

产物：`desktop/zhuanzhu-work/dist/转注 Work-0.1.0.dmg`（版本号随 `package.json`）。

### 安装后冒烟

1. 打开 dmg，将「转注 Work」拖入「应用程序」。
2. 确保 `openclaw` 在 PATH 且 `~/.openclaw/openclaw.json` 已配置。
3. 启动应用 → 完成向导 → 发送 `回复两个字：收到`。
4. Gateway 日志：`~/Library/Logs/转注Work/gateway.log`。

打包后 bundled 资源路径：`Contents/Resources/resources/`（见 `lib/gateway.js` 的 `bundledResourcesRoot()`）。

## media2text 集成（P3 / Issue #39）

侧栏 **档案检索**、**环境检查** 通过 main 进程调用 `media2text` CLI（JSON 透传）。

### 开箱清单

| 项 | 要求 |
|----|------|
| Python 环境 | 仓库根 `pip install -e ".[dev]"`，或 PATH 中有 `media2text` |
| ffmpeg | `doctor` 检查；转写/录制依赖 |
| Playwright | `playwright install chromium`（抖音 sync / 登录） |
| 合规 | 首次向导勾选 → 同步 `compliance accept` |
| 抖音登录 | 仍用 CLI：`media2text auth login --platform douyin`（或终端执行） |
| 索引 | 有转写文件后：`media2text archive index --json` |

工作区：`~/Library/Application Support/转注 Work/data`（与 `config.yaml` 中 `workspace` 一致）。

### 验证

```bash
source .venv/bin/activate
media2text compliance accept --json
media2text archive index --json
media2text archive search "半导体" --json

cd desktop/zhuanzhu-work && npm run dev
# 侧栏 → 档案检索 / 环境检查
```

## UI 壳（P4 / Issue #43）

主界面 IA 对齐 gstack `finalized.html`（原型文件不删改，仅迁入 `renderer/`）。

| 页面 | 状态 |
|------|------|
| 聊天 | ✅ OpenClaw HTTP + **SSE 流式**（P5），失败 fallback 非流式 |
| 档案检索 | ✅ `media2text archive search`（P3）；**发送到聊天**（P5） |
| 环境检查 | ✅ `media2text doctor`（P3） |
| 智能体画廊 | 4 个 lens（P6）；「+ 对话」切换 sessionKey + 角色前缀 |
| 监控守护 / 平台登录 / 技能库 / 流水线 / 通知渠道 | 静态占位，按钮 disabled 或「即将接入 CLI」 |
| 合规声明 | 静态文案；状态联动 doctor 的 compliance 字段 |

Composer（P5）：输入 `@` 弹出最近转写路径；`/search 关键词 [问题]` 注入档案上下文块。

智能体 Lens（P6）：见 [docs/zhuanzhu-work-ia.md](../../docs/zhuanzhu-work-ia.md)。侧栏与会话 pill 显示当前 lens 与 `sessionKey`。

## Preload API

```javascript
await window.zhuanzhu.openclaw.chat({
  message: "你好",
  sessionKey: "agent:main:main",
});

await window.zhuanzhu.openclaw.chatStream({
  message: "你好",
  sessionKey: "agent:main:main",
  onDelta(chunk) {
    console.log(chunk);
  },
});

await window.zhuanzhu.media2text.listTranscriptRefs({ limit: 40 });

await window.zhuanzhu.app.getBootstrap();
await window.zhuanzhu.app.acceptCompliance();
await window.zhuanzhu.app.openConfigDir();
await window.zhuanzhu.app.enterMain();

await window.zhuanzhu.media2text.archiveSearch("半导体");
await window.zhuanzhu.media2text.doctor();
await window.zhuanzhu.media2text.run(["archive", "index", "--json"]);
```

## 目录

```
desktop/zhuanzhu-work/
├── main.js              # Electron main + 启动引导 + IPC
├── lib/
│   ├── gateway.js       # Gateway 健康检查 / spawn / 退出清理
│   ├── config.js        # openclaw.json 读取与向导判定
│   ├── paths.js         # 配置路径、合规文件、日志
│   ├── media2text-config.js
│   └── media2text-sidecar.js
├── preload.js
├── e2e/gui-smoke.mjs
├── build/               # 打包图标（generate-icon.js）
├── resources/           # bundle-manifest + 未来 bundled node/openclaw
└── renderer/
    ├── splash.html      # 启动页
    ├── wizard.html      # 首次向导
    ├── index.html       # 聊天主界面
    └── ...
```

## 非目标（本仓库当前阶段）

- Apple 公证 / 开发者 ID 签名（见上方「发布构建」）
- 应用内自动更新（GitHub Releases）
- 内置完整 OpenClaw npm 包（`prepare-bundle` 仅占位 manifest）
- WebSocket 流式
- 多 Agent sessionKey / lens prompt（P6）→ 见 [zhuanzhu-work-ia.md](./zhuanzhu-work-ia.md)
- 能力页真正调用 monitor/auth/pipeline CLI（后续 Issue）
- 打包内置 Python / PyInstaller media2text（`resources/media2text` 仅占位）
- 应用内自动启动 `monitor watch` 守护进程

详见 [docs/openclaw-integration.md](../../docs/openclaw-integration.md) 与 [docs/issues/zhuanzhu-p1-bundled-gateway.md](../../docs/issues/zhuanzhu-p1-bundled-gateway.md)。
