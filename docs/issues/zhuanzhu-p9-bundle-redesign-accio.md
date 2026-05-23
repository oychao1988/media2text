# P9：转注 Work 运行时压缩包改造（Accio 同构）

> **GitHub**：[#53](https://github.com/oychao1988/media2text/issues/53)  
> **建议分支**：`issue-53-zhuanzhu-p9-runtime-archive`  
> **依赖**：P7 [#46](https://github.com/oychao1988/media2text/issues/46) 已合并；`prune_node_bundle` 修复建议先合入 main  
> **设计参考**：[docs/zhuanzhu-bundle-redesign-accio.md](../zhuanzhu-bundle-redesign-accio.md)

## 背景

P7 将 Node、openclaw、media2text 明文展开到 `extraResources/resources/`，prune 后仍约 **761 MB**，DMG 下载约 **990 MB**。对标本机 **Accio Work**（`external-tools.tar.gz` ~94 MB + 首次启动解压到 `Application Support`），安装包可降至 **~210 MB** 量级。

本单将运行时改为 **压缩包进 .app、首次启动解压到用户目录**，并 prune openclaw / slim media2text，使 DMG **< 280 MB**、`.app` **< 550 MB**，同时保持无全局 openclaw/node 时可 Gateway + doctor。

## 验收标准

### P9a — 压缩包与延迟解压（必做）

- [x] 新增 `desktop/zhuanzhu-work/lib/runtime-bundle.js`：`resolveRuntimeRoot(app)`、`ensureExtracted(app)`（读 `runtime-bundle.version` hash，解压到 `userData/runtime/{hash}/`）。
- [x] `scripts/prepare-zhuanzhu-bundle.sh`：staging → prune → 产出 `resources/runtime-bundle.tar.gz` + `resources/runtime-bundle.version`；**不再**将展开目录提交/打进 dmg（开发态 `ZHUANZHU_RUNTIME_MODE=expanded` 可保留展开目录）。
- [x] `electron-builder` `extraResources` 仅打包 `runtime-bundle.tar.gz`、`runtime-bundle.version`、`bundle-manifest.json`。
- [x] `lib/gateway.js`、`lib/media2text-sidecar.js`、`main.js` 改为通过 `resolveRuntimeRoot` 解析 node/openclaw/media2text 路径。
- [x] 首次启动 splash 显示解压进度；hash 不匹配时重新解压；解压失败给出明确错误（含磁盘空间提示）。
- [x] 更新 `scripts/verify-zhuanzhu-bundle.sh`：解压 temp 目录验证 node/openclaw/m2t + `resolveRuntimeRoot`。

### P9b — openclaw prune（必做）

- [x] `prepare-zhuanzhu-bundle.sh` 增加 `prune_openclaw_bundle`：删除 dev/test/docs/maps 等；`npm prune --omit=dev`（若适用）。
- [ ] 打包后 openclaw 解压体积 **< 280 MB**（PR 描述附 `du -sh` 截图或日志）。→ 实测 **318 MB**，略超目标

### P9c — media2text slim（必做）

- [x] 默认 `ZHUANZHU_M2T_SLIM=1`：`pip install` playwright 包但不含 browser driver（site-packages ~38 MB）。
- [x] `media2text doctor --json` 在无 Chromium 时返回可解析字段；应用/wizard 或文档引导 `playwright install chromium`（不要求 UI 一键安装，但需可发现）。
- [x] wrapper 仍支持系统 Python 3.12+；P9c **不**强制内嵌 python（内嵌列为待确认，见下）。

### 文档

- [x] `desktop/zhuanzhu-work/README.md`：磁盘占用（.app + 首次解压 + data）、首次启动说明。
- [x] `docs/openclaw-integration.md`：Resources 布局改为 tar.gz + Application Support/runtime。

### 体积门禁（PR 必须报告）

- [x] `runtime-bundle.tar.gz` **< 200 MB** → 128 MB
- [x] 未签名 `dist/*.dmg` **< 280 MB** → 216 MB
- [x] 打包后 `.app` **< 550 MB** → 381 MB

## 验证命令

```bash
cd desktop/zhuanzhu-work
export ZHUANZHU_RUNTIME_MODE=archive
npm run prepare-bundle && npm run verify-bundle
npm run package:mac:unsigned
ls -lh dist/*.dmg
du -sh dist/mac/*.app
du -sh resources/runtime-bundle.tar.gz

# E2E（无 spawn 网关时）
ZHUANZHU_SKIP_SPAWN=1 node e2e/gui-smoke.mjs

# 模拟干净 PATH（需已安装 dmg 或 open dist/mac/*.app）
env -i HOME="$HOME" USER="$USER" PATH="/usr/bin:/bin" \
  open dist/mac/转注\ Work.app
# → 首次 splash 解压 → Gateway ready → 侧栏 doctor 无致命错误
```

## 非目标范围

- **P9d** 按需组件安装器（`components/playwright`、`ffmpeg` 一键下载 UI）— 可另开 Issue
- 内嵌 python.org 3.12 前缀（Accio 有 python ~63 MB）— 本单不强制；若实现需 PR 单独说明体积影响
- Windows NSIS bundle 验证
- Apple 公证 / 自动更新逻辑变更（P8 已有）
- 内嵌 Whisper 模型、ffmpeg 二进制、Playwright 浏览器进 dmg
- Fork Accio 源码

## 待确认问题

1. **内嵌 Python**：本单默认继续依赖系统 Python 3.12+；若验收要求「完全零依赖 Python」，需人类确认是否纳入 P9 或另开 P9c+。
2. **解压后是否删除 .app 内 tar.gz**：Accio 保留双份；本单建议保留 tar 以便 repair，PR 可讨论。
