# m2t-desktop P8：验收冒烟、文档与 Vitest a11y/响应式

## 背景

P0–P7 合并后，集中完成 D1–D10 手工验收、架构 §8 逐条勾选、README/CLAUDE 桌面章节，以及 `≤768px` 双 rail 与 `StatusLight` 的 Vitest 冒烟。

**参考**

- 目标 D1–D10：design §2
- UI 验收 U1–U15：[ui-review.md](../superpowers/specs/2026-06-04-m2t-desktop-ui-review.md)
- 计划 Task 38–39：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)

## 验收标准

### Task 38 — Smoke + 文档

- [ ] `README.md` Desktop 小节：`serve`、Tauri dev、环境（ffmpeg、playwright、DEEPGRAM 可选）
- [ ] `CLAUDE.md` 命令速查补充 desktop 相关
- [ ] 手工清单（PR 或 `docs/superpowers/verification/` 记录）：
  - [ ] D1–D10 各一条证据（命令输出或截图路径）
  - [ ] **U1–U15**（[ui-review.md](../superpowers/specs/2026-06-04-m2t-desktop-ui-review.md)）逐条勾选或注明 N/A
  - [ ] §8 错误表每一行 UI 表现
  - [ ] 空列表、AppBootstrap 重试、色盲模拟（Chrome 去饱和）各 1 项
- [ ] `pytest tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop`
- [ ] `ruff check src tests`；`pyright`

### Task 39 — Vitest

- [ ] `vitest.config.ts` + `responsive.test.ts`：`≤768px` 双 rail 行为（ui-design §4.5）
- [ ] `StatusLight`：各灯色 `aria-label` + abbr
- [ ] `pnpm --filter m2t-desktop test` 全绿

### 质量

- [ ] 无新增 `@pytest.mark.desktop` 测试在默认 `pytest tests/` 中失败（未装 desktop extra 时 skip 或 CI 文档一致）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
ruff check src tests
pyright
pytest tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop
pnpm --filter m2t-desktop test
media2text doctor --json
```

## 非目标范围

- Playwright E2E 进 CI
- Windows/Linux 打包验证
- 新功能 scope

## 依赖与顺序

- **依赖**：[#131](https://github.com/oychao1988/media2text/issues/131)、[#132](https://github.com/oychao1988/media2text/issues/132) 全部合并 **main** 后执行；本单为 **收官**

## 实现备注

- GitHub Issue: [#133](https://github.com/oychao1988/media2text/issues/133)
- 分支：`issue-133-m2t-desktop-p8-smoke`
- 可创建 `docs/superpowers/verification/2026-06-04-m2t-desktop-acceptance.md` 记录结果
