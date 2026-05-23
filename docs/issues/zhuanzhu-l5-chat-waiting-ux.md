# L5：转注 Work 聊天等待态 UX（TTFT 空窗期）

> **GitHub**：[#60](https://github.com/oychao1988/media2text/issues/60)  
> **建议分支**：`issue-60-zhuanzhu-chat-waiting-ux`  
> **依赖**：P5 流式 UI；可选 L1 基准  
> **背景分析**：OpenClaw 回复慢根因分析（2026-05-24 会话）

## 背景

SSE 在 ~0.3s 即返回 `role: assistant`，但 **首个 `content` delta 约 5s 后**才到达。UI 显示静态「正在思考…」+ 光标动画，用户感知为「卡住」。

Gateway 当前对 MiniMax-M2.7 **不推送 reasoning/thinking 中间 token**；UX 改进应聚焦 **可感知的进度反馈**，而非假设模型会变快。

## 验收标准

### 等待态

- [ ] 流式 assistant 气泡在 **无 content delta** 期间：
  - 显示分阶段文案（例如：「连接 Gateway…」→「Agent 处理中…」），按 elapsed 阈值切换（如 0.5s / 2s / 5s）。
  - 可选：显示已等待秒数（`已等待 3s`），收到首字后清除。
- [ ] 收到首个 `content` delta 后立即切换为正常流式文本（现有行为保留）。

### SSE 扩展（若 Gateway 将来推送）

- [ ] `parseSseLines` / renderer **忽略未知 delta 字段但不报错**；若 delta 含 `reasoning_content` / `thinking` 等（PR 实测字段名），在折叠区或副文案展示 **摘要**（≤200 字），不阻塞主 content。

### 样式

- [ ] `styles.css`：waiting 态与 streaming 态视觉区分（不要求大改 IA）。

### 文档

- [ ] README 说明：TTFT 受模型/Gateway 影响，UI 等待态仅为体验优化。

## 验证命令

```bash
cd desktop/zhuanzhu-work && npm run dev
# 1. 发短消息，观察 0–5s 内文案/计时变化
# 2. 首字到达后光标动画停止、内容正常追加

# 可选录屏或 PR 附 gif
```

## 非目标范围

- 不修改 Gateway 以强制推送 reasoning token
- 不包含模型切换或 fast 模式（见 L3）
- 不做「假流式」逐字动画（无 content 时不伪造文字）
