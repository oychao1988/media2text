# P3：转注 Work 内置 media2text 能力（sidecar）

> **GitHub**：[#39](https://github.com/oychao1988/media2text/issues/39)  
> **建议分支**：`issue-39-zhuanzhu-p3-m2t-sidecar`  
> **依赖**：[#38](https://github.com/oychao1988/media2text/issues/38) 已合并

## 背景

聊天壳 + 安装包就绪后，把 **media2text** 核心 CLI 能力接入桌面：档案检索、监控状态、合规门禁，使「转注 Work」成为完整工作站而非仅 OpenClaw 聊天窗口。

## 验收标准

### Sidecar 调用

- [ ] `main` 进程提供 IPC：`media2text.run(argv: string[])` 或封装命令（`archive search`、`doctor --json`、`compliance status`）。
- [ ] 解析使用项目已安装的 venv 或打包后的 `media2text` 可执行文件路径（开发态：`repo/.venv/bin/media2text`；发布态：文档 + `resources/media2text` 占位或 PyInstaller 路径）。
- [ ] 超时与 stderr 透传；JSON 命令返回解析后的对象给 renderer。

### UI 集成（最小）

- [ ] 「档案检索」页或侧栏入口：输入关键词 → 调用 `archive search --json` → 列表展示 excerpt + 路径（静态样式即可）。
- [ ] 未 `compliance accept` 时检索被拒绝，UI 显示与 CLI 一致的指引。
- [ ] 「环境检查」：展示 `doctor --json` 关键字段（ffmpeg、playwright、磁盘、compliance）。

### 工作区

- [ ] 默认 `workspace` 指向 `~/Library/Application Support/转注Work/data`（或沿用 `config.yaml` 逻辑）；首次启动创建目录。
- [ ] 不提交 `data/` 内容。

### 文档

- [ ] README：完整开箱清单（ffmpeg、可选 GPU、抖音登录仍引导 `auth login` 或应用内按钮调 CLI）。

## 验证命令

```bash
source .venv/bin/activate
cd desktop/zhuanzhu-work && npm run dev

# 应用内：档案检索「半导体」应返回 JSON 命中（需先 index + compliance）
media2text compliance accept --json
media2text archive index --json
media2text archive search "半导体" --json
```

## 非目标范围

- 完整迁移 gstack `finalized.html` 所有页面（可后续单开 UI Issue）
- 守护进程 `monitor watch` 内置自动启动（仅状态查询或文档引导）
- Windows 全功能 parity 测试
