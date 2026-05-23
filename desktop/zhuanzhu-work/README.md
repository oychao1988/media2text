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
| `ZHUANZHU_CHAT_FAST=1` | 聊天请求尝试 `thinking=off` / `fast=true`（需 Gateway 支持） |
| `OPENCLAW_CONFIG_PATH` | 覆盖 openclaw.json 路径 |
| `OPENCLAW_BIN` | 覆盖 openclaw 可执行文件路径 |
| `ZHUANZU_WORKSPACE` | 覆盖 media2text workspace（默认 `userData/data`） |
| `MEDIA2TEXT_BIN` | 覆盖 media2text 可执行文件 |
| `MEDIA2TEXT_CONFIG` | 覆盖 `config.yaml`（默认 `userData/config.yaml`） |
| `ZHUANZHU_RUNTIME_MODE` | `archive`（默认 prepare）或 `expanded`（开发展开目录） |
| `ZHUANZHU_M2T_SLIM` | prepare 时默认 `1`：media2text 不带 playwright |
| `ZHUANZHU_KEEP_EXPANDED` | archive 模式下仍复制展开目录到 `resources/`（本地调试） |

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

## 发布构建（P2 / Issue #38 + P7 bundle）

将应用打成 macOS `.dmg` 安装包（Windows `.exe` 可选）。

### 开箱清单：bundled dmg vs 开发态

| 项 | **bundled dmg**（P9 archive） | **开发态**（`npm run dev`） |
|----|------------------------------|------------------------------|
| Node ≥22.14 | ✅ 首次启动从 tar.gz 解压到 `userData/runtime/` | 系统 nvm / Node，或 `ZHUANZHU_RUNTIME_MODE=expanded` |
| OpenClaw CLI | ✅ 同上 | 系统 `openclaw` / YonClaw |
| media2text | ✅ slim bundle（**需系统 Python 3.12+**；无 playwright） | 仓库 `.venv/bin/media2text` |
| OpenClaw 配置 | `~/.openclaw/openclaw.json` | 同左 |
| Chromium / ffmpeg | 用户执行 `playwright install chromium`；ffmpeg 自行安装 | 同左 |

**磁盘占用（bundled）**：

| 位置 | 大约 |
|------|------|
| 应用程序 `.app` | ~450–550 MB（含压缩 runtime-bundle） |
| 首次解压 `Application Support/转注Work/runtime/` | ~300–400 MB |
| 用户数据 `data/` | 随录制/作品增长 |
| 可选 Chromium | ~150 MB |

**首次启动**：拖入应用程序后，首次打开会显示「正在解压运行环境（首次约 1 分钟）…」，完成后自动启动 Gateway。

打包后 **无需** 全局 `openclaw` 或 repo venv 即可启动 Gateway；档案/doctor 走解压后的 `media2text` wrapper。

**prepare-bundle（P9）** 默认 `ZHUANZHU_RUNTIME_MODE=archive`：产出 `runtime-bundle.tar.gz`，dmg 不再内嵌展开的 node/openclaw 目录。开发可 `ZHUANZHU_RUNTIME_MODE=expanded` 或 `ZHUANZHU_KEEP_EXPANDED=1` 保留展开目录便于调试。

### 前提

| 项 | 要求 |
|----|------|
| Node.js | **≥ 22.14**（prepare-bundle 会下载到 `resources/node`；开发态用系统 Node） |
| macOS | 用于 `package:mac`（本机或 CI macOS runner） |
| 签名 | 见下方「签名与公证」；无证书时用 `package:mac:unsigned` |

### 命令

```bash
source ~/.nvm/nvm.sh
cd desktop/zhuanzhu-work
npm install
npm run prepare-bundle   # 下载 node/openclaw + pip media2text → resources/
npm run verify-bundle    # 验证 bundled 路径（无需全局 openclaw）
```

若 npm / curl 很慢，先开本地代理再执行：

```bash
export HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890
npm run prepare-bundle
```

```bash
npm run package:mac        # 产出 dist/转注 Work-<version>.dmg
# Windows（可选）：npm run package:win
```

若 `npm install` 或 Electron 下载很慢，可开本地代理并配国内镜像：

```bash
export HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890
export ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
export ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
```

产物：`desktop/zhuanzhu-work/dist/zhuanzhu-work-0.1.0.dmg`（版本号随 `package.json`；`productName` 仍为「转注 Work」）。

### 签名与公证（P8 / Issue #47）

证书与 Apple 账号**仅通过环境变量**注入，勿提交仓库。

| 变量 | 说明 |
|------|------|
| `CSC_LINK` | Developer ID `.p12` 路径，或 base64 内容 |
| `CSC_KEY_PASSWORD` | 证书密码 |
| `APPLE_ID` | Apple ID 邮箱 |
| `APPLE_APP_SPECIFIC_PASSWORD` | 应用专用密码 |
| `APPLE_TEAM_ID` | Team ID |

**无证书**（默认本地 / CI 无 secrets）：

```bash
npm run package:mac:unsigned
```

**有证书**：

```bash
export CSC_LINK="$HOME/certs/zhuanzhu.p12"
export CSC_KEY_PASSWORD="***"
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="****"
export APPLE_TEAM_ID="XXXXXXXXXX"
npm run package:mac
spctl -a -vv -t install "dist/mac/转注 Work.app"
```

发布清单与 Release 资产说明：[docs/zhuanzhu-release-checklist.md](../../docs/zhuanzhu-release-checklist.md)。

### 自动更新（P8）

打包版集成 `electron-updater`，启动约 8s 后静默检查 GitHub Releases；侧栏底部 **升级** 可手动检查 / 下载 / 重启安装。

Release tag 约定：`zhuanzhu-v<version>`（例 `zhuanzhu-v0.1.0`）。需上传 `latest-mac.yml` 与 `.blockmap`（`electron-builder` 自动生成）。

推送 tag 触发 CI：`.github/workflows/zhuanzhu-release.yml`（无 Apple secrets 时产出未签名 dmg）。

```bash
npm run package:publish:mac   # 本地发布到 GitHub（需 GH_TOKEN）
```

### 安装后冒烟（bundled dmg）

1. 打开 dmg，将「转注 Work」拖入「应用程序」。
2. 配置 `~/.openclaw/openclaw.json`（token + 模型 API Key）；**无需**全局 `openclaw`。
3. 安装 **Python 3.12+**（仅档案/doctor 需要；聊天/Gateway 不依赖）。
4. 启动应用 → 完成向导 → 发送 `回复两个字：收到`。
5. Gateway 日志：`~/Library/Logs/转注Work/gateway.log`。
6. 侧栏 → 环境检查（doctor）应能调用 bundled `media2text`；缺 Chromium 时 doctor 会提示 `playwright install chromium`。

打包后运行时：首次启动解压到 `Application Support/转注Work/runtime/{hash}/`；`.app` 内仅 `runtime-bundle.tar.gz`（见 `lib/runtime-bundle.js`）。

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
│   ├── runtime-bundle.js # P9：tar.gz 解压与 runtime 路径
│   ├── gateway.js       # Gateway 健康检查 / spawn / 退出清理
│   ├── config.js        # openclaw.json 读取与向导判定
│   ├── paths.js         # 配置路径、合规文件、日志
│   ├── media2text-config.js
│   └── media2text-sidecar.js
├── preload.js
├── e2e/gui-smoke.mjs
├── build/               # 打包图标（generate-icon.js）
├── resources/           # bundle-manifest + runtime-bundle.tar.gz (P9)
└── renderer/
    ├── splash.html      # 启动页
    ├── wizard.html      # 首次向导
    ├── index.html       # 聊天主界面
    └── ...
```

## 非目标（本仓库当前阶段）

- Mac App Store / Microsoft Store 上架
- 差分更新优化、beta/stable 多 channel UI
- WebSocket 流式
- 能力页真正调用 monitor/auth/pipeline CLI（后续 Issue）
- 内置 Python 运行时 / PyInstaller onefile（P7 使用 site-packages + 系统 python3）
- 应用内自动启动 `monitor watch` 守护进程

详见 [docs/openclaw-integration.md](../../docs/openclaw-integration.md) 与 [docs/issues/zhuanzhu-p1-bundled-gateway.md](../../docs/issues/zhuanzhu-p1-bundled-gateway.md)。
