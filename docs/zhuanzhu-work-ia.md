# 转注 Work 信息架构 — 智能体 Lens

画廊与侧栏「会话」共用同一套 lens 配置（`desktop/zhuanzhu-work/renderer/lenses.js`）。

## Lens → OpenClaw session

当前 Gateway **仅通过 `sessionKey` 区分会话**（同一 `main` agent，无需在 `openclaw.json` 新建 agent）。每条用户消息可附带 `[lens:…]` 角色前缀，便于在 history 中识别 lens。

| Lens ID | 显示名 | sessionKey | message 前缀 |
|---------|--------|------------|--------------|
| `default` | 默认协调 | `agent:main:main` | （无） |
| `archive` | 档案助手 | `agent:main:archive` | `[lens:archive] …` |
| `wanzhan` | 万战寻道 | `agent:main:wanzhan` | `[lens:wanzhan] …` |
| `nuwa` | 女娲蒸馏 | `agent:main:nuwa` | `[lens:nuwa] …` |

## 交互

- 智能体画廊「+ 对话」→ 切换 lens、清空当前 UI 消息、进入聊天页。
- 侧栏四个固定会话入口 → 同上（切换到不同 lens 时清空 UI 消息）。
- 「+ 新消息」→ 保持当前 lens，清空 UI 消息。
- 档案页「发送到聊天」→ 切换到 `archive` lens（保留已有 UI 消息），预填 `[archive context]` 块。
- 当前 lens 与最近使用顺序写入 `localStorage`（`zhuanzhu.currentLens` / `zhuanzhu.recentLenses`）。

## 多 Agent（可选）

若日后在 `~/.openclaw/openclaw.json` 的 `agents` 中注册独立 agent（如 `wanzhan`），可将对应 lens 的 `sessionKey` 改为 `agent:wanzhan:main`，并在 PR/文档中同步。P6 不依赖该配置即可工作。
