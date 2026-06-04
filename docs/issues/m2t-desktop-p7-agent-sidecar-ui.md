# m2t-desktop P7：Agent sidecar（Node）+ Tauri IPC + Composer UI

## 背景

桌面右栏 Agent 复用 scmclaw **pi-coding-agent** 模式：Node `m2t-agent-sidecar` 经 NDJSON 与 Tauri 通信，tools 调 `:8765`；对话持久化在 Python API（P3 chat 路由）。

**参考**

- 架构 §4.6：[2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- 计划 Phase 8–9 Task 33–37：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)
- 参考：`/Users/Oychao/Documents/Projects/scmclaw-v2` — `pi-sidecar`、`usePiSidecar.ts`、`pi_sidecar.rs`

## 验收标准

### Task 33 — m2t-agent-sidecar 脚手架

- [ ] `packages/m2t-agent-sidecar`；pin 与 scmclaw 相同 `@earendil-works/pi-coding-agent` 版本
- [ ] NDJSON stdin 循环：`message.user`、`context.refresh`

### Task 34 — `m2t_*` tools

- [ ] 实现 design §4.6.2 全部 tools → `M2T_API_BASE_URL`（含 `m2t_read_manifest` → #127 manifest；`m2t_read_summary` → #127 `/summary`）
- [ ] 单测：MockAgent / nock

### Task 35 — skill + system prompt

- [ ] `packages/agent-skills/media2text/SKILL.md`
- [ ] `buildSystemPrompt` 含 creator/session/transcript 路径 + README 合规声明

### Task 36 — `agent_sidecar.rs`

- [ ] spawn Node；stdout → `emit("agent-event")`；stdin 写用户消息
- [ ] config PATCH 触发 reload：**默认** 等 in-flight `turn.end` 后再重启 sidecar

### Task 37 — React Agent UI

- [ ] `useM2tAgent` 解析 PiEvent；`turn.end` → `POST` 落库
- [ ] Composer + `ToolResultCard` + `ChatMarkdown`；`#agent-model-select` PATCH thread
- [ ] Agent 启动失败：右栏 error，**不**阻塞左栏监控
- [ ] Vitest：PiEvent parser

### 质量

- [ ] D4：首 token ≤10s（手工，需 LLM key）
- [ ] D4b：「总结这场直播」类 prompt 触发 tool 读 transcript（mock 集成测优先）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pnpm install
pnpm --filter m2t-agent-sidecar test
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 右栏发送消息，观察 tool-card 与 DB desktop_chat_* 行
```

## 非目标范围

- 富 tool-card UI（v1 JSON）
- OpenAPI codegen（v1.1）
- Agent 在 Python API 内推理

## 依赖与顺序

- **依赖**：[#128](https://github.com/oychao1988/media2text/issues/128) chat、[#129](https://github.com/oychao1988/media2text/issues/129) Tauri、[#130](https://github.com/oychao1988/media2text/issues/130) layout
- **建议** [#131](https://github.com/oychao1988/media2text/issues/131) 合并后再开 PR，便于联调三栏+Agent

## 实现备注

- GitHub Issue: [#132](https://github.com/oychao1988/media2text/issues/132)
- 分支：`issue-132-m2t-desktop-p7-agent`
- `.env` / `summarize.llm` 与 `M2T_API_BASE_URL` 文档写入 README Desktop 节（可部分放 P8）
