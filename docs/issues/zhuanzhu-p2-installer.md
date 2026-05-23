# P2：转注 Work 安装包（electron-builder）

> **GitHub**：[#38](https://github.com/oychao1988/media2text/issues/38)  
> **建议分支**：`issue-38-zhuanzhu-p2-installer`  
> **依赖**：[#37](https://github.com/oychao1988/media2text/issues/37) 已合并

## 背景

P1 实现一键启动后，需要把应用打成 **用户可下载的安装包**，实现「下载 → 安装 → 打开即用」。参考 [openclaw-desktop](https://github.com/agentkernel/openclaw-desktop) 的 `electron-builder` 流程。

## 验收标准

### 打包配置

- [ ] `desktop/zhuanzhu-work` 增加 `electron-builder` 配置（`package.json` build 段或 `electron-builder.yml`）。
- [ ] **macOS**：产出 `dist/转注 Work-<version>.dmg`（或英文文件名 + 中文 productName）。
- [ ] **Windows**（可选本单）：`nsis` 安装包；若仅 Mac，在 Issue/PR 说明 Windows 延后。
- [ ] `files` 包含 `main.js`、`preload.js`、`renderer/`；**排除** `node_modules` 中 dev 冗余（使用 `files` 白名单或 `asar`）。
- [ ] 应用 `appId`、图标占位（`.icns` / `.ico` 可用简单默认图）。

### prepare-bundle 占位（不要求完整 openclaw npm）

- [ ] 脚本 `scripts/prepare-zhuanzhu-bundle.sh` 或 `npm run prepare-bundle`：文档化未来将下载 portable Node + openclaw；本单可 **仅创建** `resources/bundle-manifest.json` 说明 pin 版本。
- [ ] P1 的 Gateway spawn 在打包后仍可用（使用打包内的 `openclaw` 路径或 fallback 文档）。

### 文档

- [ ] `desktop/zhuanzhu-work/README.md` 增加 **发布构建** 章节：`npm run package` 前提（Node ≥22.14）。
- [ ] `docs/openclaw-integration.md` 补充「发布与安装」：数据目录、卸载不删 `~/.openclaw`、升级策略。

### 验证

- [ ] 本地 `npm run package`（或 `package:mac`）成功生成 dmg。
- [ ] 从 dmg 安装后启动应用，完成 P1 同款聊天冒烟（手动或 `e2e` 文档步骤）。

## 验证命令

```bash
source ~/.nvm/nvm.sh
cd desktop/zhuanzhu-work
npm install
npm run package:mac   # 或 package 脚本名以 PR 为准
# 打开 dist/*.dmg 安装并冒烟
```

## 非目标范围

- Apple 公证 / 开发者 ID 签名（可文档说明「未签名需右键打开」）
- 应用内自动更新（GitHub Releases）
- 内置 media2text Python（P3）
- Linux AppImage
