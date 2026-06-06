# m2t-desktop Agent Pane UI 细化 PR5：布局 grid 修订 + chat-only 居中

## 背景

对齐规格 §8：`transcript-chat` 右列 `minmax(280px, var(--right-w))` 与 `#resize-right` 拖动；`chat-only` 末列 `minmax(0, 1fr)` + `.agent-main` 对话列居中 `max-width: min(720px, 50vw)`。

**参考**

- 规格 §8、§11 A9–A10：[2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md](../superpowers/specs/2026-06-07-m2t-desktop-agent-pane-ui-refinements-design.md)

**依赖**：PR3 后联调体验更佳；grid/CSS 已在 #199（PR1 `layout.css`）交付，本 Issue 以勾选留痕 + 回归验证为主

## 验收标准

### Grid（`apps/m2t-desktop/src/styles/layout.css` + AppShell）

- [x] `transcript-chat`：`sidebar | grip | minmax(280px, 1fr) | grip | minmax(280px, var(--right-w))`
- [x] `chat-only`：`sidebar | grip | 0 | 0 | minmax(0, 1fr)`
- [x] `#resize-right-split` 在 `transcript-chat` 隐藏

### chat-only 居中

- [x] `.agent-main { max-width: min(720px, 50vw); margin-inline: auto; width: 100% }`（含 `#chat-scroll` + composer wrap；页签栏仍全宽）
- [x] `#resize-right`：`chat-only` 下 `display: none`（A10）
- [x] 切入 `chat-only` 时若右栏已折叠则展开（同 06-06 spec）
- [x] `#collapse-right` 在 `chat-only` 隐藏

### 列宽拖动

- [x] `useColumnResize` / `getRightWidthLimits()`：`transcript-chat` 下 `#resize-right` 有效（A9）
- [x] `chat-only` 不依赖 `--right-w` 控制可见宽度

### 持久化

- [x] `m2t-desktop-layout` 仍存 `desktopLayoutPreset`、`rightW`；行为与 §8.4 一致

### 测试

- [x] `layoutPresetClass.test.ts` / `layoutPresets.test.ts` / `uiParity.test.tsx` 覆盖 preset class

## 验证命令

```bash
source .venv/bin/activate
pnpm --filter m2t-desktop test
# 手工 A9/A10（需 Tauri）：
# pnpm --filter m2t-desktop tauri dev
# transcript-chat 拖 #resize-right；chat-only 无手柄且对话列居中 ≤720px
```

## 非目标范围

- Composer 单行/滚动条（PR6）
- 左栏 / 中栏 transcript 逻辑变更（06-06 已交付）

## 实现备注

- 分支：`issue-203-agent-layout-chatonly`
- GitHub Issue: [#203](https://github.com/oychao1988/media2text/issues/203)
- CSS 规则见 #199 合并的 `apps/m2t-desktop/src/styles/layout.css`（`desktop-layout-chat-only` 段）
