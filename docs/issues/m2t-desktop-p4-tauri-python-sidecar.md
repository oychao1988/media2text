# m2t-desktop P4：Tauri 脚手架 + Python sidecar 生命周期

## 背景

交付可启动的 `apps/m2t-desktop`（Tauri 2 + React 18 + pnpm workspace），应用启动时 spawn Python API 并轮询 health，为后续三栏 UI 提供 `get_api_base_url()`。

**参考**

- 架构 §4.1 启动顺序：[2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- UI 真源（后续 PR 对齐）：[finalized.html](../superpowers/designs/m2t-desktop/finalized.html)
- 计划 Phase 5 Task 22–23：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)
- 参考实现：`scmclaw-v2` 的 sidecar 模式（本地路径见计划）

## 验收标准

### Task 22 — 脚手架

- [ ] `pnpm-workspace.yaml`：`packages/*`、`apps/m2t-desktop`
- [ ] Tauri 2 + React 18 + TypeScript + Tailwind 最小可编译
- [ ] `packages/shared`：`PiEvent` 类型占位（可从 scmclaw 拷贝）

### Task 23 — Python sidecar

- [ ] `python_sidecar.rs`：spawn `{venv}/python -m media2text serve --port 8765`
- [ ] 启动轮询 `GET /api/health` 直至 OK 或超时；进程退出时清理
- [ ] Tauri command `get_api_base_url() -> String`
- [ ] 手工：启动 app 后 `curl http://127.0.0.1:8765/api/health` 成功

### 质量

- [ ] `pnpm --filter m2t-desktop build`（或文档写明 dev 命令）通过
- [ ] 不阻塞在完整三栏 UI（下 PR）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
# 需已合并 P1 API
pnpm install
pnpm --filter m2t-desktop tauri dev
# 另终端
curl -s http://127.0.0.1:8765/api/health
```

## 非目标范围

- Node Agent sidecar（P7）
- 完整业务 UI（P5–P6）
- macOS 签名 / 自动更新
- Windows/Linux 构建

## 依赖与顺序

- **依赖**：[#126](https://github.com/oychao1988/media2text/issues/126)（health）；开发期可 mock，合并前须真机联调
- **可与** [#130](https://github.com/oychao1988/media2text/issues/130) layout（MSW）并行

## 实现备注

- GitHub Issue: [#129](https://github.com/oychao1988/media2text/issues/129)
- 分支：`issue-129-m2t-desktop-p4-tauri-shell`
- macOS-first；CI 可不跑 Tauri（文档注明）
