# L3：转注 Work 聊天 fast 模式可配置（非仅环境变量）

> **GitHub**：[#58](https://github.com/oychao1988/media2text/issues/58)  
> **建议分支**：`issue-58-zhuanzhu-chat-fast-config`  
> **依赖**：L1 基准脚本（验证）；P5 流式聊天已合并  
> **背景分析**：OpenClaw 回复慢根因分析（2026-05-24 会话）

## 背景

`lib/openclaw-chat.js` 在 `ZHUANZHU_CHAT_FAST=1` 时向 Gateway 附加 `thinking: "off"`、`fast: true`。打包应用默认 **未设置**，用户无法从 UI 开启。

实测 MiniMax-M2.7 上 thinking 参数对 TTFT 改善有限，但该开关对 **其他模型 / 未来 Gateway 行为** 仍有价值，且应与「模型切换」解耦，作为 **聊天模式** 配置项。

## 验收标准

### 配置

- [ ] 在转注应用配置（`~/Library/Application Support/zhuanzhu-work/config.json` 或现有 `ensureAppConfig` 结构）增加：

  ```json
  {
    "chat": {
      "fastMode": false
    }
  }
  ```

- [ ] `buildChatBody()` 优先级：`ZHUANZHU_CHAT_FAST=1` env **覆盖** config（便于 CI/dev）；否则读 `chat.fastMode`。
- [ ] 默认 `fastMode: false`（不改变现有行为）。

### UI（最小）

- [ ] 设置页或聊天 composer 旁增加 toggle「快速回复（关闭深度思考）」；切换后立即生效（下一消息起）。
- [ ] toggle 状态持久化到上述 config；bootstrap JSON 可暴露给 renderer（若已有 settings 面板则接入）。

### 文档

- [ ] `desktop/zhuanzhu-work/README.md` 更新：说明 fast 模式、与 env 关系、Gateway 需支持 `thinking`/`fast` 字段。

### 验证（与 L1 联动）

- [ ] PR 描述附：`benchmark-chat-latency.sh` 在 fast on/off 各 3 次的 TTFT 对比（本机快照即可，不作硬门禁）。

## 验证命令

```bash
cd desktop/zhuanzhu-work
npm run dev
# UI 打开 fast toggle，发消息；gateway.log 或请求体可见 thinking/fast 字段

node -e "const {buildChatBody}=require('./lib/openclaw-chat'); ..."  # 若导出测试 hook，PR 说明

bash ../../scripts/benchmark-chat-latency.sh --thinking off --runs 2
```

## 非目标范围

- **不包含**默认模型切换或 Provider 选择（另规划）
- 不保证 MiniMax-M2.7 TTFT 必降（仅保证请求字段与 UI 正确）
- 不实现「双模式聊天 / 直连模型」（见 L6）
