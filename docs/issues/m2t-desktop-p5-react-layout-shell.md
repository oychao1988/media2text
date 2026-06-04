# m2t-desktop P5：React 三栏布局壳（tokens / AppBootstrap / rails）

## 背景

对齐已批准原型 `finalized.html`：五列 grid、折叠 rail、主题切换、sidecar 启动遮罩；v1 字体 **Geist Sans**（方案 A）。

**参考**

- [ui-design.md](../superpowers/specs/2026-06-04-m2t-desktop-ui-design.md) §4、§5
- [finalized.html](../superpowers/designs/m2t-desktop/finalized.html)
- 计划 Phase 6 Task 24–26：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)

## 验收标准

### Task 24 — Tokens + AppBootstrap

- [ ] `tokens.css` 移植 `--*` 与 `data-theme`；默认亮色
- [ ] `@fontsource/geist-sans` + JetBrains Mono；**禁止** v1 默认 Inter
- [ ] `AppBootstrap`：`loading` / `error+重试` / `ready`（架构 §8 第 1 行）
- [ ] `useLayoutStore` + `localStorage` `m2t-desktop-layout`（列宽与折叠）
- [ ] Vitest：`AppBootstrap.test.tsx`

### Task 25 — Rails + 空列表

- [ ] `LeftRail` / `RightRail`：rail 点、`#rail-daemon` 展开左栏、`#rail-user-menu` 仅开菜单
- [ ] `CreatorListEmpty`：无监控博主时 CTA → 管理视图（可用 MSW 测）
- [ ] 左栏 loading：skeleton ×3

### Task 26 — 中栏视图路由

- [ ] `CenterToolbar` + `ViewLive` / `ViewHistory` / `ViewConfig` / `ViewManage` 壳（可先静态）
- [ ] 用户菜单切换 config/manage；Tab 切换 live/history

### 质量

- [ ] `pnpm --filter m2t-desktop test` 通过（本 PR 可仅 bootstrap 测例）
- [ ] 视觉与原型布局偏差须在 PR 说明

## 验证命令

```bash
pnpm install
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 原型对照
cd docs/superpowers/designs/m2t-desktop && python3 -m http.server 8766
# http://127.0.0.1:8766/finalized.html
```

## 非目标范围

- 真实 API 接线（P6）
- flv.js / Agent Composer（P6/P7）
- `≤768px` Vitest（P8 单收）

## 依赖与顺序

- **依赖**：[#129](https://github.com/oychao1988/media2text/issues/129) Tauri shell
- **可与** [#126](https://github.com/oychao1988/media2text/issues/126)–[#128](https://github.com/oychao1988/media2text/issues/128) 并行（MSW mock）

## 实现备注

- GitHub Issue: [#130](https://github.com/oychao1988/media2text/issues/130)
- 分支：`issue-130-m2t-desktop-p5-layout-shell`
