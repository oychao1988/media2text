# L6：转注 Work 双模式聊天（快速问答 vs 完整 Agent）

> **GitHub**：[#61](https://github.com/oychao1988/media2text/issues/61)  
> **建议分支**：`issue-61-zhuanzhu-dual-mode-chat`  
> **依赖**：L3 fast 配置；L1 基准；P5/P6 聊天与 lens  
> **背景分析**：OpenClaw 回复慢根因分析（2026-05-24 会话）

## 背景

转注当前 **所有消息** 均走 OpenClaw HTTP Agent 全链路（skills 扫描、session、tools 能力），简单问答 TTFT ~5s。Accio 等产品对「轻聊天」与「重 Agent」分层；转注需在 **不切换默认模型** 的前提下，提供用户可选的 **聊天模式**。

## 验收标准

### 模式定义

- [ ] 配置 + UI 两种模式（命名 PR 可微调）：
  - **快速**：最小 Agent 开销——PR 必须文档化实现（例如：专用 `session_key`、请求 flag、或 Gateway 支持的 lightweight 路径）；目标 TTFT 相对 baseline **可测量下降**（L1 脚本对比，PR 附数据；不设硬 SLA）。
  - **Agent**（默认）：现有行为不变（lens prefix、@ 引用、档案 context、tools）。

### UI

- [ ] Composer 旁模式切换（segmented control 或 dropdown）；持久化到 app config。
- [ ] 模式切换时 **不**清空聊天历史；lens 仍生效。

### 实现边界

- [ ] `openclaw-chat.js` 根据模式组装不同 body（字段在 PR 说明并对齐 Gateway 能力）。
- [ ] 快速模式下：**仍**走 Gateway（非直连 Provider API），除非 Issue 评论中人类确认可直连——默认 **非目标**。

### 文档

- [ ] README + `docs/openclaw-integration.md`：两模式差异、适用场景、与 L3 fast toggle 关系（快速模式是否隐含 fast/thinking off，PR 说明）。

## 验证命令

```bash
cd desktop/zhuanzhu-work && npm run dev
# Agent 模式：发消息，行为与现网一致
# 快速模式：同 prompt，L1 benchmark TTFT 对比

bash scripts/benchmark-chat-latency.sh --runs 5  # 两模式各跑，PR 附 jq 摘要
```

## 非目标范围

- **不包含**模型/Provider 切换 UI
- 不实现 WebSocket `chat.send`（见 L7）
- 不绕过 Gateway 直连 minimax/openai（除非人类在 Issue 显式批准）
- 不改动 OpenClaw 上游 agent 定义

## 待确认问题

- Gateway 是否已有 official「lightweight chat」参数？实现前应用 bundled openclaw `--help` / 源码检索并在 PR 描述记录。
