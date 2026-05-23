# 转注 Work 运行时打包改造方案（参考 Accio Work）

> **状态**：设计稿（P9）  
> **参考**：本机 `Accio.app` v0.7.1、`YonClaw.app`、Accio CDN `beta-mac.yml`（0.11.0 zip ~210 MB）  
> **前置**：P7 bundle + `prune_node_bundle` 已合并或即将合并

## 1. 目标

| 指标 | 当前（prune 后） | 目标（Accio 同构） |
|------|------------------|-------------------|
| DMG 下载 | ~990 MB | **200–280 MB** |
| `.app` 安装体积 | ~900 MB–1 GB | **450–550 MB** |
| 首次可用总磁盘 | ~1 GB（全在 .app 内） | **~900 MB–1.1 GB**（.app + 解压目录） |
| 开箱 | 拖进 Applications 即用 | 拖进 Applications → **首次启动解压 30–60s** → 即用 |

原则：**安装包只带压缩运行时；重资产延迟解压或按需下载**，与 Accio 的 `external-tools.tar.gz` 策略一致。

---

## 2. Accio 结构对照

### 2.1 Accio `.app` 内（v0.7.1，本机实测）

```
Accio.app/  (~743 MB)
├── Frameworks/Electron Framework.framework   ~210 MB
└── Resources/
    ├── app.asar                                ~375 MB   # UI + 主进程 + OpenClaw 集成
    ├── app.asar.unpacked/node_modules          ~58 MB    # 原生模块
    ├── external-tools.tar.gz                   ~94 MB    # 压缩工具链
    └── external-tools.version                  # 内容 hash（如 ce414221fe50）
```

### 2.2 Accio 首次运行后（用户目录）

```
~/Library/Application Support/Accio/
├── external-tools/{hash}/                      ~300 MB   # 解压：node/python/bun/git/gh/jq
└── Cache/                                      ~289 MB   # Electron 缓存（可清）

~/.accio/                                       ~259 MB   # 账号/配置
~/.openclaw/                                    ~405 MB   # Gateway 状态（与转注共用）
```

### 2.3 Accio 设计要点

1. **DMG 里不展开工具链** — 只放 94 MB 的 tar.gz，安装包小。
2. **版本 hash 驱动解压** — `external-tools.version` 变更才重新解压。
3. **重逻辑进 asar** — OpenClaw 聊天/Gateway 集成在 375 MB asar，不在 Resources 散目录。
4. **按需下载** — asar 内有 `chromium-downloader` 等，浏览器不全量打进包。
5. **用户数据与运行时分离** — `Application Support` 只管解压产物 + 缓存；`~/.openclaw` 管 Gateway。

---

## 3. 转注 Work 现状与问题

### 3.1 当前 `extraResources` 布局（prune 后 ~761 MB）

```
resources/
├── node/           ~109 MB   # portable Node（已 prune）
├── openclaw/       ~482 MB   # npm prefix 全量 node_modules
├── media2text/     ~170 MB   # site-packages + wrapper（依赖**系统** Python 3.12+）
└── bundle-manifest.json
```

### 3.2 主要问题

| 问题 | 影响 |
|------|------|
| 运行时**明文展开**在 `.app` 内 | DMG 无法有效压缩，下载 ~1 GB |
| `media2text` 带 **playwright 137 MB** 但 wrapper 用系统 Python | 体积大且行为不一致 |
| `openclaw` 未做 npm prune | pdfjs、koffi、多 SDK 等占 ~200 MB+ |
| 无「按需组件」层 | ffmpeg、Chromium 要么全带要么全不带 |
| 路径解析写死 `resources/node` | 无法指向 `Application Support` 解压目录 |

---

## 4. 目标架构（Accio 同构）

### 4.1 目录布局

```
转注 Work.app/  (目标 ~450–550 MB)
├── Frameworks/ …                               ~210 MB  # Electron（不变）
├── app.asar                                    ~30–50 MB # main/lib/renderer（已较薄）
└── Resources/
    ├── runtime-bundle.tar.gz                   ~120–180 MB  # 压缩运行时（见 §4.2）
    ├── runtime-bundle.version                  # sha256 前 12 位，与 Accio 同思路
    └── bundle-manifest.json                    # pin + 组件清单 + bundled 标志

~/Library/Application Support/转注Work/
├── runtime/{hash}/                             # 首次启动 skip 若 hash 匹配
│   ├── node/bin/node
│   ├── openclaw/node_modules/.bin/openclojure
│   ├── media2text/bin/media2text
│   └── media2text/site-packages/…
├── components/                                 # Phase 2：按需组件（可选）
│   ├── playwright-chromium/…
│   └── ffmpeg/…
└── data/                                       # 已有：media2text workspace

~/.openclaw/openclaw.json                       # 不变，与 Accio/YonClaw 共用
```

**与 Accio 的差异（有意保留）**：

- 转注 **必须** 内嵌 media2text（核心 SKU），Accio 的 tar.gz 主要是 node/python/bun。
- 转注可 **Phase 2** 才把 playwright/ffmpeg 放进 `components/` 按需拉取；Accio 用 chromium-downloader。

### 4.2 `runtime-bundle.tar.gz` 内容（解压前 staging）

prepare 阶段在临时目录组装，**prune 后再打包**：

```
runtime-bundle/
├── manifest.json           # pins: node, openclaw, media2text, build_id
├── node/                   # ~40 MB  pruned portable Node 22.x
├── openclaw/               # ~200–250 MB  npm prefix + prune（见 §5.2）
└── media2text/
    ├── bin/media2text      # wrapper：优先 bundled python，fallback 系统 3.12+
    └── site-packages/      # ~30–40 MB  slim install（无 playwright，见 §5.3）
```

压缩后目标 **120–180 MB**（gzip 与 Accio 类似；可选 `tar.zst` 更小，首版用 gzip 兼容 macOS `tar`）。

### 4.3 运行时解析链（新模块）

新增 `lib/runtime-bundle.js`，统一入口：

```text
bundledResourcesRoot()
  → isPackaged ? process.resourcesPath : APP_ROOT/resources

resolveRuntimeRoot(app)
  1. dev + ZHUANZHU_RUNTIME_EXPANDED=1 → resources/（展开目录，开发态）
  2. packaged → ensureExtracted(app)
       a. read runtime-bundle.version
       b. target = userData/runtime/{hash}/
       c. 若不存在或 manifest 不匹配 → 解压 tar.gz（splash 进度）
       d. return target
  3. gateway.js / media2text-sidecar.js 只认 resolveRuntimeRoot()，不再直读 resources/node
```

`main.js` 启动顺序调整为：

```text
app.ready
  → ensureExtracted (可阻塞 splash)
  → ensureAppConfig
  → ensureGateway(resolveRuntimeRoot())
  → bootstrap UI
```

---

## 5. 体积优化（打包前 prune）

### 5.1 Node（已有，保持）

- 删除 `lib/node_modules`、headers、多余 bin symlink。
- 目标：**~40 MB** 解压 / **~15 MB** 在 tar.gz 内。

### 5.2 OpenClaw npm prefix

在 `install_openclaw` 之后增加 `prune_openclaw_bundle`：

| 动作 | 预估节省 |
|------|----------|
| `npm prune --omit=dev` | 视依赖而定 |
| 删除 `**/test`、`**/*.md`、`**/*.map`（保留 license） | ~20–40 MB |
| 可选：剥离 `@mariozechner/*` 等非 gateway 必需（需 openclaw doctor 验证） | 风险项，P9b |
| 保留 `playwright-core` 在 openclaw 侧仅当 gateway 需要；否则删 | ~11 MB |

目标：**482 MB → 200–250 MB** 解压。

### 5.3 media2text slim

| 方案 | 说明 | 体积 |
|------|------|------|
| **P9 默认** | `pip install . --no-deps` + 手动列核心依赖；**不含 playwright** | ~30 MB |
| **P9c 可选** | 内嵌 python.org 3.12 最小前缀（Accio/YonClaw 有 python ~63 MB） | +63 MB 解压 |
| **按需** | 首次 `creator sync` / `monitor watch` 前提示安装 Chromium | 0（包内） |

wrapper 改造优先级：

1. `runtime/{hash}/media2text/bin/media2text` 使用 `runtime/{hash}/python/bin/python3`（若 P9c 启用）。
2. 否则保持系统 Python 3.12+，但 **site-packages 不再含 playwright**。
3. `doctor --json` 返回 `playwright_browser: missing` + 一键 `media2text doctor --install-browser`（调 playwright install）。

### 5.4 Phase 2：`components/` 按需

| 组件 | 触发 | 来源 |
|------|------|------|
| Playwright Chromium | 首次 sync/live 或 doctor 修复 | `playwright install chromium` 到 `components/playwright/` |
| ffmpeg | transcribe / download | 文档引导 brew；或静态二进制 ~20 MB |
| Whisper 模型 | transcribe | **永不内嵌**，用户 config 下载 |

Accio 参考：`chromium-downloader` 模块在 main 进程按需拉取；转注可在 `lib/component-installer.js` 封装，UI 走 wizard/splash。

---

## 6. 构建与 CI 改造

### 6.1 `prepare-zhuanzhu-bundle.sh` 重构

```bash
# 伪流程
STAGE=$(mktemp -d)
download_node → $STAGE/node && prune_node
install_openclaw → $STAGE/openclaw && prune_openclaw
bundle_media2text_slim → $STAGE/media2text
write $STAGE/manifest.json

HASH=$(sha256sum runtime-bundle | cut -c1-12)
tar -czf resources/runtime-bundle.tar.gz -C $STAGE .
echo "$HASH" > resources/runtime-bundle.version
rm -rf resources/node resources/openclaw resources/media2text  # 不再提交展开目录

write_manifest  # bundled=true 当 tar.gz + version 存在
```

环境变量：

| 变量 | 作用 |
|------|------|
| `ZHUANZHU_RUNTIME_MODE=archive` | 默认：只产出 tar.gz |
| `ZHUANZHU_RUNTIME_MODE=expanded` | 开发：保留展开目录，跳过 tar（`resolveRuntimeRoot` 直读 resources/） |
| `ZHUANZHU_M2T_SLIM=1` | 默认开：不带 playwright |
| `ZHUANZHU_EMBED_PYTHON=0` | P9c：设为 1 时打入 python 前缀 |

### 6.2 `electron-builder` `extraResources`

```json
"extraResources": [
  {
    "from": "resources",
    "to": "resources",
    "filter": [
      "runtime-bundle.tar.gz",
      "runtime-bundle.version",
      "bundle-manifest.json"
    ]
  }
]
```

开发态 `expanded` 时可额外 filter `node/**`、`openclaw/**` 等（本地 package 脚本分支）。

### 6.3 `verify-zhuanzhu-bundle.sh`

1. 解压 tar.gz 到 temp。
2.  .node -v` / `openclaw --version` / `media2text version`。
3. Node 脚本：`require('./lib/runtime-bundle').ensureExtracted(mockApp)` → 路径含 `runtime/`。
4. `gateway.resolveOpenClawBin` 指向解压目录。

---

## 7. 用户体验

### 7.1 首次启动

1. Splash 显示：「正在准备运行环境（首次约 1 分钟）…」
2. 解压进度：`tar` 流式或 `tar -xzf` + 已解压字节 / 总大小。
3. 完成后写 `userData/runtime/.extracted` 标记（hash 不一致则重做）。
4. 失败：磁盘空间不足 / 权限 → 明确错误 + 打开日志目录。

### 7.2 升级

- 新版本 DMG 替换 `.app`；`runtime-bundle.version` 变化 → 解压到新 `{hash}` 目录。
- **可选优化**：成功后删除旧 hash 目录（Accio 会保留 tar.gz + 解压双份，我们可解压后删 `.app` 内 tar 不行，tar 必须在 .app 内用于 repair）。

### 7.3 磁盘占用说明（README）

| 位置 | 大约 |
|------|------|
| 应用程序 | ~500 MB |
| 运行环境（首次解压） | ~400 MB |
| 用户数据 `data/` | 随录制/作品增长 |
| 可选 Chromium | ~150 MB |

---

## 8. 分阶段实施

### P9a — 核心（必做，1–2 PR）

- [ ] `lib/runtime-bundle.js`：`ensureExtracted`、`resolveRuntimeRoot`
- [ ] 改 `gateway.js`、`media2text-sidecar.js`、`main.js` 路径
- [ ] `prepare-zhuanzhu-bundle.sh` 产出 tar.gz + version
- [ ] electron-builder filter 仅打包压缩包
- [ ] splash 解压进度
- [ ] verify-bundle + e2e 更新

**验收**：无全局 openclaw/node 的机器，装 dmg → 首次启动解压 → Gateway + `doctor --json` ok；DMG **< 350 MB**。

### P9b — OpenClaw / npm prune（必做）

- [ ] `prune_openclaw_bundle` 脚本
- [ ] 对照 `openclaw gateway run` + 聊天 smoke

**验收**：openclaw 解压体积 **< 280 MB**；DMG **< 280 MB**。

### P9c — media2text slim + 可选 Python（推荐）

- [ ] `ZHUANZHU_M2T_SLIM=1` 默认；playwright 移出 bundle
- [ ] doctor 引导 `playwright install chromium`
- [ ] 可选：embed python 3.12 前缀（对齐 Accio external-tools 里的 python）

**验收**：m2t site-packages **< 50 MB**；sync 前 doctor 提示装 browser。

### P9d — 按需组件安装器（可选）

- [ ] `lib/component-installer.js` + wizard 步骤
- [ ] ffmpeg 检测与文档链接

---

## 9. 体积预算（P9c 完成后）

| 部分 | 解压 | 在 tar.gz 中 |
|------|------|--------------|
| Electron avatar Electron | 210 MB | （framework，不在 tar） |
| app.asar | 40 MB | — |
| node | 40 MB | ~12 MB |
| openclaw (pruned) | 220 MB | ~70 MB |
| media2text slim | 35 MB | ~12 MB |
| manifest + 脚本 | 1 MB | — |
| **tar.gz 小计** | **~296 MB** | **~120–180 MB** |
| **.app 合计** | | **~450–550 MB** |
| **DMG（压缩）** | | **~200–280 MB** |

与 Accio 0.11.0 arm64 zip **210 MB** 同量级。

---

## 10. 风险与对策

| 风险 | 对策 |
|------|------|
| 解压失败（磁盘满） | 启动前 `fs.statfs` 检查 ≥ 600 MB 可用 |
| tar 路径过长 / 符号链接 | staging 用相对路径；`tar --no-same-owner` |
| 开发态与打包态路径不一致 | `ZHUANZHU_RUNTIME_MODE=expanded` 统一 dev |
| openclaw prune 过狠导致 gateway 崩 | verify-bundle 跑 gateway health；CI smoke |
| 无 Python 3.12 且未 embed python | wizard 明确引导安装或启用 P9c |
| 用户误删 `Application Support/.../runtime` | 下次启动自动从 .app 内 tar 重建 |

---

## 11. 非目标（本方案不做）

- Windows NSIS 完整验证（P9 仅 macOS dmg）
- 内嵌 Whisper / 大模型
- 替换 Electron 为 Tauri 等
- Fork Accio 源码\`app.asar\`（仅借鉴打包策略）

---

## 12. 相关文件（实施时改）

| 文件 | 变更 |
|------|------|
| `scripts/prepare-zhuanzhu-bundle.sh` | staging + tar.gz + prune |
| `scripts/verify-zhuanzhu-bundle.sh` | 解压验证 |
| `desktop/zhuanzhu-work/lib/runtime-bundle.js` | **新建** |
| `desktop/zhuanzhu-work/lib/gateway.js` | 用 `resolveRuntimeRoot` |
| `desktop/zhuanzhu-work/lib/media2text-sidecar.js` | 同上 |
| `desktop/zhuanzhu-work/main.js` | 启动前 `ensureExtracted` |
| `desktop/zhuanzhu-work/renderer/splash.js` | 解压进度 UI |
| `desktop/zhuanzhu-work/package.json` | extraResources filter |
| `docs/openclaw-integration.md` | Resources 布局更新 |
| `desktop/zhuanzhu-work/README.md` | 磁盘占用 / 首次启动说明 |

---

## 13. 验证命令（P9 完成后）

```bash
cd desktop/zhuanzhu-work
export ZHUANZHU_RUNTIME_MODE=archive
npm run prepare-bundle && npm run verify-bundle
npm run package:mac:unsigned
ls -lh dist/*.dmg   # 目标 < 280M

# 模拟干净用户：PATH 无 node/openclaw，无 repo venv
env -i HOME="$HOME" USER="$USER" PATH="/usr/bin:/bin" \
  open dist/mac/转注\ Work.app
# → splash 解压 → Gateway ready → doctor ok
```
