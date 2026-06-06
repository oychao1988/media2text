# m2t-desktop Agent Pane UI 细化 PR4：页签 Agent 头像

## 背景

`AgentTabsBar` 每个页签在标题前显示 18px 圆头像（灵犀渐变 / 博主 abbr），与原型 `.agent-tab-avatar` 一致。

**参考**

- 规格 §2.1、§6、§11 A4：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md)

**依赖**：PR3（draft tab 需 `draft.agentId`）；creators 列表已有

## 验收标准

### 数据

- [ ] `AGENT_GLOBAL_PROFILE` 常量（灵犀 name/abbr/渐变 class）
- [ ] 博主 profile 来自 `CreatorsContext` + `threadAgentId(thread)`

### UI

- [ ] `.agent-tab` 布局：`[.agent-tab-avatar][label]`，`gap: 6px`
- [ ] `.agent-tab-avatar.global` 与灵犀历史组头像视觉一致
- [ ] thread 页签：`getAgentProfile(threadAgentId(thread))`
- [ ] draft 页签：用 `draft.agentId` 解析 profile

### 测试

- [ ] 组件测试：global vs creator avatar class / abbr 文案

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 手工 A4：多 tab 各显示对应头像；draft 切换 picker 后 avatar 更新
```

## 非目标范围

- 消息区头像（PR1 已含 message head）
- 页签拖拽排序
- API-4 `creator_display_name` on threads（P3）

## 实现备注

- 分支：`issue-202-agent-tab-avatars`
- GitHub Issue: [#202](https://github.com/oychao1988/media2text/issues/202)
