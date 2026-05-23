# P6：转注 Work 智能体 Lens（多 session + 画廊联动）

> **GitHub**：[#45](https://github.com/oychao1988/media2text/issues/45)  
> **建议分支**：`issue-45-zhuanzhu-p6-agent-lens`  
> **依赖**：P4 UI 壳已合并（P5 可并行但建议 P5 后再做 @ 联动）

## 背景

IA 定义 4 个智能体（档案 / 万战 / 女娲 / 默认），原型画廊「+ 对话」应进入不同复盘 lens。当前固定 `agent:main:main`。

## 验收标准

### Session 映射

- [ ] 定义 lens 配置表（JSON 或 JS 常量）：`archive` | `wanzhan` | `nuwa` | `default` → `sessionKey` 与/或 **system 前缀**（PR 说明与 OpenClaw 配置对齐方式）。
- [ ] 画廊「+ 对话」设置当前 lens 并切到聊天 view；composer 显示当前 lens 名称。
- [ ] 侧栏会话列表（最小）：展示 4 个固定条目或最近使用的 lens（静态 + localStorage 即可）。

### OpenClaw

- [ ] 若 Gateway 支持多 agent id，文档化如何在 `~/.openclaw/openclaw.json` 配置；若仅 sessionKey 区分，在 PR 中明确。
- [ ] 万战 lens 发送消息时附带简短角色说明（可拼在 message 前，不修改 Gateway 配置亦可）。

### 文档

- [ ] `docs/zhuanzhu-work-ia.md` 或 README 补充 lens → session 对照表。

## 验证命令

```bash
cd desktop/zhuanzhu-work && npm run dev
# 从画廊分别进入万战/档案，发送消息，确认 sessionKey 或 message 前缀不同（Network/preload 日志或 Gateway history）
```

## 非目标范围

- 自动加载 wanzhanxundao / huashu-nuwa skill 文件到 Gateway
- 新建智能体 CRUD
- 女娲蒸馏自动化
