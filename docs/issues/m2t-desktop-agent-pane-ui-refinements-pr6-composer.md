# m2t-desktop Agent Pane UI 细化 PR6：Composer 高度 + 滚动条

## 背景

修复 `useAutoResizeTextarea` mount 时将空 textarea 设为 ~203px 的问题；对齐原型 §7：`field-sizing: content`、1 行起增至 10 行、超出后悬停/聚焦显示 5px 细滚动条。

**参考**

- 规格 §7、§11 A7–A8：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md)

**依赖**：可与 PR5 并行；系列最后一单，合并后跑 Epic 验收表

## 验收标准

### 高度行为（§7.1）

- [ ] 默认 **单行**（`min-height: calc(13px * 1.45 + 14px)`）；mount 且 value 为空时 **不写** inline `height`
- [ ] `field-sizing: content`；JS 仅在 `input` 事件 sync
- [ ] 最大 10 行 `max-height`；发送清空后收回单行
- [ ] 无 `field-sizing` 回退：空内容清除 height；有内容 clamp scrollHeight

### 滚动条（§7.2）

- [ ] 默认 thumb 透明；`.agent-composer:hover` 或 textarea `:focus` 显示 5px 圆角 scrollbar
- [ ] 浅/深主题 thumb 色值与 spec 一致

### Bug 修复

- [ ] 修复现状：`useAutoResizeTextarea.ts` mount 设 `height: 0px` / 空内容撑满问题（A7）

### 测试

- [ ] `useAutoResizeTextarea.test.ts`：**CRITICAL** mount 空值单行、10 行 clamp、send 清空

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 手工 A7/A8：打开 Agent 面板初始单行；粘贴长文增至 10 行后滚动条；发送收回
```

## 非目标范围

- 附件 / @ 引用真实能力
- 布局 grid（PR5）

## 实现备注

- 分支：`issue-204-agent-composer`
- GitHub Issue: [#204](https://github.com/oychao1988/media2text/issues/204)
- 系列合并完成后更新：[2026-06-06-m2t-desktop-agent-pane-acceptance.md](../superpowers/verification/2026-06-06-m2t-desktop-agent-pane-acceptance.md) 或新建 06-07 UI 细化验收表（A1–A10）
