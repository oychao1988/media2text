# P7：转注 Work 运行时打包（Node + OpenClaw + media2text）

> **GitHub**：[#46](https://github.com/oychao1988/media2text/issues/46)  
> **建议分支**：`issue-46-zhuanzhu-p7-bundle-runtime`  
> **依赖**：P2 安装包流程已合并

## 背景

当前 dmg 仍依赖系统 Node、openclaw CLI、Python venv。参考 [openclaw-desktop](https://github.com/agentkernel/openclaw-desktop)，本单实现 **prepare-bundle 真实下载/打包** 与 Gateway/media2text 路径解析，向「下载即用」迈进。

## 验收标准

### prepare-bundle

- [ ] 扩展 `scripts/prepare-zhuanzhu-bundle.sh`（或 Node 脚本）：下载 pin 版本 **portable Node**（≥22.14）到 `resources/node/`。
- [ ] 安装 pin 版本 **openclaw** npm 到 `resources/openclaw/`（或 npm pack + extract）。
- [ ] **media2text**：优先方案在 PR 说明（PyInstaller onefile / 复制 venv / 文档化最小 bundle）；至少实现 **开发机可复现** 的 bundle 目录 + `resources/media2text/bin/media2text` 可执行。
- [ ] 更新 `resources/bundle-manifest.json`：`bundled: true` 与版本 pin。

### 运行时

- [ ] `lib/gateway.js` / `lib/media2text-sidecar.js` 打包后 **优先** bundled 路径（已有逻辑需验证端到端）。
- [ ] `npm run package:mac` 后，在 **无全局 openclaw / 无 repo venv** 的环境（或 `PATH` 刻意清空子集）能启动 Gateway + doctor。

### 文档

- [ ] README「开箱清单」区分 **bundled dmg** vs **开发态**。
- [ ] `docs/openclaw-integration.md` 更新 Resources 布局。

## 验证命令

```bash
cd desktop/zhuanzhu-work
npm run prepare-bundle
npm run package:mac
# 安装 dmg，无系统 openclaw 时启动应用 → Gateway ready + doctor ok
```

## 非目标范围

- Apple 公证（P8）
- Windows bundle 完整验证
- 内置 ffmpeg / playwright 浏览器二进制（仍文档引导安装）
