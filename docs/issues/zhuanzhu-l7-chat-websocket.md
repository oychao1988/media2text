# L7：转注 Work 聊天迁移 WebSocket `chat.send`（可选）

> **GitHub**：[#62](https://github.com/oychao1988/media2text/issues/62)  
> **建议分支**：`issue-62-zhuanzhu-chat-websocket`  
> **依赖**：P5 SSE 已合并；建议 **L6 之后** 或并行前在 Issue 评论确认 Gateway WS 协议  
> **背景分析**：OpenClaw 回复慢根因分析（2026-05-24 会话）

## 背景

当前聊天：`renderer → IPC → main → HTTP SSE /v1/chat/completions`。README 已列 WebSocket 为后续项。OpenClaw Gateway 支持 WS 事件（如 TUI `chat.send`）；Accio 使用 `@ali/accio-adk-ts` + WebSocket Bridge，**非** HTTP completions 路径。

本单评估并（若可行）实现 WS 路径，目标：**更低往返开销、更细粒度事件**（含可能的 thinking/tool 事件），HTTP 保留为 fallback。

## 验收标准

### 调研（PR 必须含结论段）

- [ ] 文档化 bundled openclaw Gateway WS 协议：URL、`auth`、事件名、与 HTTP 字段映射。
- [ ] 对比同 prompt 下 HTTP SSE vs WS 的 TTFT（L1 脚本扩展或 sibling `benchmark-chat-ws.sh`）。

### 实现（若调研结论为「可行且值得」）

- [ ] 新增 `lib/openclaw-chat-ws.js`（或扩展 `openclaw-chat.js`）：main 进程维护单例 WS 连接（可选 reconnect）。
- [ ] preload 暴露 `chatStream` **不变**；内部路由 WS，失败 fallback HTTP SSE（与 P5 一致）。
- [ ] 解析 WS 事件中的 content delta；thinking/tool 事件转发 renderer（供 L5 UX 消费，可选）。

### 测试

- [ ] 单元测试：mock WS server 推送分片 → IPC chunk 顺序正确。
- [ ] E2E：至少 manual 步骤写入 PR；`gui-smoke` 扩展可选。

## 验证命令

```bash
cd desktop/zhuanzhu-work && npm run dev
# Network：确认 WS 连接 127.0.0.1:18789（或文档端口）
# 流式聊天正常；断 WS 时 fallback HTTP

npm test  # WS mock tests
bash scripts/benchmark-chat-latency.sh --runs 3  # HTTP baseline
# bash scripts/benchmark-chat-latency-ws.sh --runs 3  # 若新增
```

## 非目标范围

- 不替换 Gateway 为 Accio ADK / 远程 Phoenix Agent
- 不包含模型切换
- 若 WS 协议不稳定或 TTFT 无改善，允许 PR **仅合调研文档 + benchmark**，实现部分标记为 follow-up

## 待确认问题

- Gateway WS 路径是否与 HTTP 同端口？token 传递方式？
- 打包应用是否需 `ws` npm 依赖或使用 Node 内置 `WebSocket`（Node 22+）？
