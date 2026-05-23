# P5：转注 Work 聊天增强（流式 + @ 引用 + 检索上下文）

> **GitHub**：[#44](https://github.com/oychao1988/media2text/issues/44)  
> **建议分支**：`issue-44-zhuanzhu-p5-chat-stream`  
> **依赖**：P4 UI 壳已合并

## 背景

当前聊天走 HTTP `POST /v1/chat/completions` 且 `stream: false`，无 `@` 转写引用、无档案检索结果注入。本单提升 **聊天体验**，对齐 IA 中 composer 与复盘工作流。

## 验收标准

### Gateway 对接

- [ ] preload/main 支持 **SSE 流式** 或 **WebSocket `chat.send`**（二选一，PR 说明选型）；UI 逐字/逐块更新 assistant 气泡。
- [ ] 流式失败时 fallback 到现有非流式 HTTP（不白屏）。

### Composer

- [ ] 输入 `@` 弹出简易 picker（本地 manifest / 最近 transcript 路径列表即可，无需完整文件浏览器）。
- [ ] 选中后在发送前将路径或 excerpt 拼入 message（格式在 PR 说明，便于 OpenClaw agent 解析）。

### 档案上下文

- [ ] 档案检索页「发送到聊天」或聊天内 `/search 关键词` 快捷方式：将 top N 命中 excerpt 作为 user 消息前缀或单独 context 块（PR 文档化格式）。
- [ ] 合规未 accept 时行为与 CLI 一致。

### 文档

- [ ] README + `docs/openclaw-integration.md` 更新聊天路径说明。

## 验证命令

```bash
cd desktop/zhuanzhu-work && npm run dev
# 1. 发送长回复，观察流式输出
# 2. @ 某 transcript 路径后发消息，Gateway 收到含路径内容
# 3. 从档案检索注入上下文后聊天

ZHUANZHU_SKIP_SPAWN=1 node e2e/gui-smoke.mjs   # 若扩展 E2E，在 PR 说明
```

## 非目标范围

- 出处块 `offset_sec` 可点击跳转（后续）
- 多 Agent lens 切换（P6）
- 修改 OpenClaw agent 本体配置
