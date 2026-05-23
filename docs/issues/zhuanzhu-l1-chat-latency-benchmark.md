# L1：转注 Work 聊天延迟基准脚本（可重复迭代）

> **GitHub**：[#56](https://github.com/oychao1988/media2text/issues/56)  
> **建议分支**：`issue-56-zhuanzhu-chat-latency-bench`  
> **依赖**：本地 Gateway 可访问（`http://127.0.0.1:18789/health` 为 live）  
> **背景分析**：OpenClaw 回复慢根因分析（2026-05-24 会话）

## 背景

转注 Work 聊天经 `POST /v1/chat/completions`（SSE）走本地 OpenClaw Gateway。实测简单问答 **TTFT（首字）约 4.5–5.8s**，需可重复、可对比的基准工具，支撑后续优化（fast 模式、双模式聊天、Gateway 改造等）的 **before/after** 验证。

当前无仓库内脚本；手工 `curl` 无法稳定输出 `ttfb_ms` / `ttft_ms` / `total_ms`。

## 验收标准

### 脚本

- [ ] 新增 `scripts/benchmark-chat-latency.sh`（或 `desktop/zhuanzhu-work/scripts/` 二选一，PR 说明选型；优先仓库根 `scripts/` 与现有 openclaw 脚本并列）。
- [ ] 从 `~/.openclaw/openclaw.json` 读取 `gateway.auth.token`（或通过 env `OPENCLAW_GATEWAY_TOKEN` 覆盖）；**不得**在脚本/日志中打印完整 token。
- [ ] 默认探测 `http://127.0.0.1:18789/v1/chat/completions`，支持 env 覆盖 URL。
- [ ] 对固定短 prompt（如 `回复一个字：好`）跑 **N 次**（默认 3，可 `--runs N`），输出 **JSON 行** 或 **JSON 对象**，字段至少包含：
  - `ttfb_ms`：HTTP 响应头到达
  - `ttft_ms`：首个 `choices[0].delta.content` 非空
  - `total_ms`：流结束或 `[DONE]`
  - `session_key`、`stream`、`thinking`（若传入）
  - `ok`、`error`（失败时）
- [ ] 支持 CLI 参数：`--session-key`、`--thinking off|low|medium|high`、`--no-stream`、`--message`。
- [ ] 退出码：Gateway 不可达 → `1`；部分 run 失败 → `4`（与 CLI 惯例一致）；全成功 → `0`。

### 文档

- [ ] `desktop/zhuanzhu-work/README.md` 增加「延迟基准」小节：前置条件（Gateway 已 ready）、示例命令、如何解读 TTFT。
- [ ] 可选：`docs/issues/` 本文件末尾补充 **baseline 快照**（实现 PR 附一次本机 P50 示例，非门禁）。

## 验证命令

```bash
# Gateway 已运行（转注 Work 或 openclaw gateway run）
curl -sf http://127.0.0.1:18789/health | jq .

bash scripts/benchmark-chat-latency.sh --runs 3 --json
bash scripts/benchmark-chat-latency.sh --thinking off --runs 2

# 无 Gateway 时应非 0 退出
bash scripts/benchmark-chat-latency.sh; echo exit=$?
```

## 非目标范围

- 不修改 Gateway / OpenClaw 本体行为
- 不包含模型切换或多 Provider 对比 UI
- 不强制接入 CI（可选手动/ nightly 文档说明）

## 待确认问题

- 脚本依赖 `python3` + stdlib 即可，还是纯 `bash`+`curl`？（PR 选型并说明 macOS 兼容性）
