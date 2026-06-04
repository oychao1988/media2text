# m2t-desktop P6：React 功能面板（daemon / 直播 / 历史 / 配置 / 管理）

## 背景

三栏壳就绪且 API 齐全后，接线 daemon 卡、博主列表+WS 状态灯、直播 flv.js、转写 WS、历史回放、四段配置表单与监控管理；落实架构 **§8 错误 UX** 与交互状态矩阵。

**参考**

- 架构 §8：[2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- [config-manage-ia.md](../superpowers/specs/2026-06-04-m2t-desktop-config-manage-ia.md)
- 计划 Phase 7 Task 27–32：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)

## 验收标准

### Task 27 — API client + DaemonCard

- [ ] `api.ts` + `toast.ts`；非 2xx → toast，禁止 silent fail
- [ ] Daemon 启停、日志 tail；§8 daemon 未运行/运行中 UI 态

### Task 28 — 博主列表 + WS

- [ ] `GET /api/creators` + `WS /api/events`；断线重连后全量刷新
- [ ] `StatusLight`：`aria-label` + 缩写 录/播/收/离；`flv-badge` 仅 DEV/`?debug=1`

### Task 29 — 转写区

- [ ] REST + transcript WS；断线 banner；「等待转写」占位

### Task 30 — 直播 + 录制横幅

- [ ] flv.js + proxy URL；`StreamUnavailable`（流失败字幕仍更新）
- [ ] 🔴 横幅 + `POST recording/start`；切换博主时 destroy player

### Task 31 — 历史 + 回放

- [ ] chips 筛选、合并组、回放 `<video>` vs flv.js

### Task 32 — 配置 + 管理

- [ ] 按 [config-manage-ia.md](../superpowers/specs/2026-06-04-m2t-desktop-config-manage-ia.md)：左栏用户菜单 → **系统配置** / **监控管理** 两 Tab（非中栏常驻）
- [ ] 配置四段（用户 / 博主 / 系统 / AI）：`GET/PATCH /api/config`；脏检测；保存/还原；`#cfg-theme` 即时生效
- [ ] 各段 auth 平台「登录 ××」→ `POST /api/auth/login/{platform}`；`GET /api/auth/status` 驱动 stale 标记
- [ ] 管理：全量博主列表（`?all=1`）、内联抽屉 CRUD、`sync-profile` / `sync` / `sync-dynamics`
- [ ] §8：PATCH 400 → toast + 字段高亮；需重启 daemon → 成功 toast + 可选一键 stop/start；LLM 变更触发 agent reload（#132）

### 状态矩阵（DoD 抽查）

- [ ] 左栏 EMPTY / ERROR；中栏 FLV ERROR；配置 PATCH ERROR；管理 sync fail 行内 tag

### 质量

- [ ] 关键组件 Vitest（transcript reducer 等，计划 Task 29）
- [ ] 手工：daemon 启停、选一博主出画面、partial 转写刷新（需本地 daemon + 可选 DEEPGRAM）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# API 回归
pytest tests/unit/test_api_* -v -m desktop
```

## 非目标范围

- Agent Composer 真 LLM（P7）
- 中栏停止录制按钮
- Playwright CI E2E

## 依赖与顺序

- **依赖**：[#126](https://github.com/oychao1988/media2text/issues/126)–[#130](https://github.com/oychao1988/media2text/issues/130)
- **阻塞**：[#133](https://github.com/oychao1988/media2text/issues/133) smoke、[#132](https://github.com/oychao1988/media2text/issues/132) Agent 联调

## 实现备注

- GitHub Issue: [#131](https://github.com/oychao1988/media2text/issues/131)
- 分支：`issue-131-m2t-desktop-p6-feature-panels`
- D2/D3/D7/D9/D10 验收多在本 PR 或 P8 手工勾选
