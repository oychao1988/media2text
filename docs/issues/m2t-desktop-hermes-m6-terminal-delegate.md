# m2t-desktop Hermes M6：Terminal（local）+ delegate_task + approval

## 背景

v2.1 引入 Hermes **terminal / delegation** 生态（D14），vendor 拷贝 + profile 沙箱（§24.2）。Desktop 写操作与 `m2t_start_recording` 等 **并行 approval**（H16）。

**参考**：Hermes §24.2、H14–H16

**依赖**：M5a（profile `enabled_toolsets` 白名单）。M5b/M5c 非硬依赖。

## 验收标准

### Task 1 — Vendor 移植

- [x] `agent/vendor/hermes/` — `local.py` environment + `terminal.py` registry
- [x] `agent/tools/delegate.py` — `delegate_task` 同步子 agent summary
- [x] `agent/approval.py` — 危险命令检测；Desktop Tauri 确认对话框桥接

### Task 2 — Toolsets

- [x] `m2t-terminal`（file/search/patch/terminal local）、`m2t-delegation`
- [x] 默认 profile **不**启用；`profile.yaml` 显式勾选（O7）
- [x] `terminal.cwd` 限制在 `data/creators/{sec_uid}`（path guard）

### Task 3 — 行为

- [x] H14：`terminal` 在 creator cwd 执行；测试写入 `data/creators/{sec_uid}/`
- [x] H15：`delegate_task` 子 agent 继承父 thread creator profile
- [x] H16：危险 shell + `m2t_start_recording` 均弹 approval

### Task 4 — 配置

- [x] `config.example.yaml` — `terminal.*`、`delegation.*`、`security.allowlist` 段

### 测试

- [x] `pytest tests/unit/test_agent_terminal.py tests/unit/test_agent_delegate.py -v -m agent`（mock subprocess）

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_agent_terminal.py tests/unit/test_agent_delegate.py -v -m agent
pnpm --filter m2t-desktop test
# 手工：开启博主 profile terminal toolset → 确认框 → 本地命令
```

## 非目标范围

- docker/ssh terminal backend（v3）
- Gateway / cron 调度
- Orchestrator 多 agent 看板

## 实现备注

- 分支：`issue-188-hermes-m6-terminal-delegate`
- GitHub Issue: [#188](https://github.com/oychao1988/media2text/issues/188)
