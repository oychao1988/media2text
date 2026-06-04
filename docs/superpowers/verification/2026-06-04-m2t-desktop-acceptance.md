# m2t-desktop — 验收报告（P8 / Issue #133）

**日期:** 2026-06-05  
**基线:** `main` @ P7 合并后（Agent sidecar UI）  
**规格:** [m2t-desktop-design](../specs/2026-06-04-m2t-desktop-design.md) · [ui-review](../specs/2026-06-04-m2t-desktop-ui-review.md)

## 总 verdict

| 类别 | 结论 |
|------|------|
| **自动化（Python）** | `pytest tests/unit/test_desktop_* tests/unit/test_api_* -m desktop` |
| **自动化（Vitest）** | `pnpm --filter m2t-desktop test` — responsive ≤768px CSS + StatusLight a11y |
| **静态检查** | `ruff check src tests`；`pyright` |
| **手工 D1–D10 / U1–U15 / §8** | 见下表；需本机 Tauri + 真实/模拟 daemon |

**签署建议:** 自动化全绿 + 下表手工项在 PR 中勾选或附证据路径后，可关 #133。

---

## 自动化命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
ruff check src tests
pyright
pytest tests/unit/test_desktop_* tests/unit/test_api_* -v -m desktop
pnpm --filter m2t-desktop test
media2text doctor --json
```

---

## D1–D10（架构 §2 Success Criteria）

| ID | 指标 | 状态 | 证据 / 操作说明 |
|----|------|------|-----------------|
| D1 | 冷启动 ≤3s 见 daemon 卡与博主列表 | ☐ 手工 | `pnpm --filter m2t-desktop tauri dev`；计时至左栏 daemon 卡 + 列表渲染；可附录屏或 `GET /api/health` 时间戳 |
| D2 | 选中录制中博主 ≤5s 中栏出画面 | ☐ 手工 | 需真实 🟢 场次 + FLV；观察 flv.js 首帧 |
| D3 | partial 更新 ≤5s 右栏转写刷新 | ☐ 手工 | streaming + WS；对比 `.transcript.partial` mtime |
| D4 | Agent 首 token ≤10s | ☐ 手工 | Agent 区发送短 prompt；观察 PiEvent delta |
| D4b | 「总结直播」触发读 transcript tool | ☐ 手工 / N/A | 需配置 LLM provider；mock 环境可标 N/A |
| D5 | 折叠状态重启保留 | ☐ 手工 | 折叠左右栏 → 退出 → 重开；查 `localStorage` `m2t-desktop-layout` |
| D6 | API 不破坏 CLI/daemon | ☑ 自动 | desktop/API pytest + 既有 CLI 测试未改 daemon 语义 |
| D7 | 🔴 开始录制 ≤10s → 🟢 | ☐ 手工 | 中栏横幅「开始录制」；查 DB session |
| D8 | 重启恢复 AI 对话 | ☐ 手工 | 聊一轮 → 重启 app → 同 thread 历史仍在 |
| D9 | 离线博主历史 Tab ≤2s / 20 场 | ☐ 手工 | 选 ⚫ 博主 → 历史 Tab；Network `GET .../sessions` |
| D10 | 点击场次 ≤3s final 转写首屏 | ☐ 手工 | 历史行 → 右栏 Markdown 出现 |

---

## U1–U15（UI 专项，[ui-review §6](../specs/2026-06-04-m2t-desktop-ui-review.md#6-实现验收建议ui-专项)）

| ID | 检查 | 状态 | 证据 / 操作说明 |
|----|------|------|-----------------|
| U1 | 折叠 rail 键盘聚焦切换博主 | ☐ 手工 | Tab 至 `.rail-dot`；Enter/Space 切换 |
| U2 | 🔴 录制横幅 recording 后 300ms 内消失 | ☐ 手工 | 开录后观察 `#record-banner` |
| U3 | 回放面包屑与 session_id 一致 | ☐ 手工 | 历史 → 回放视图标题 |
| U4 | `prefers-reduced-motion` 关折叠动画 | ☐ 手工 | macOS 辅助功能 → 减少动态效果 |
| U5 | WS 转写增量不整屏闪 | ☐ 手工 | 直播 partial 追加时 DOM 稳定 |
| U6 | Agent streaming 时 composer 禁用不丢输入 | ☐ 手工 | 流式回复中输入框行为 |
| U7 | 右栏 ≤50% 视口；竖屏流 16:9 视窗 | ☐ 手工 | 拖右栏至上限；竖屏 FLV |
| U8 | 主题切换即时 + 刷新保持 | ☐ 手工 | `#cfg-theme` / `m2t-desktop-theme` |
| U9 | 直播头像/rail `.is-live` 呼吸环 | ☐ 手工 | 🟢/🔴 博主对比 ⚫ |
| U10 | rail 用户菜单 vs daemon vs 博主选中 | ☐ 手工 | 折叠态点击行为分离 |
| U11 | 配置撤销还原主题+表单 | ☐ 手工 | 改主题 → 撤销 |
| U12 | PATCH 后 GET 一致；空密码不覆盖 | ☑ 自动 | `test_api_config*` |
| U13 | pipeline_mode 保存提示重启 daemon | ☐ 手工 | 保存 legacy/streaming 切换 toast |
| U14 | manage override 下 poll 生效 | ☐ 手工 | 抽屉 auto_record_override |
| U15 | Daemon 卡 log 与 `GET /api/daemon/logs?tail=5` | ☐ 手工 | 展开 log 面板对比 API |

---

## §8 错误表（架构 [§8](../specs/2026-06-04-m2t-desktop-design.md#8-错误处理)）

| 场景 | 预期 UI | 状态 | 操作说明 |
|------|---------|------|----------|
| sidecar 未启动 | 全屏「正在启动服务…」/ 重试 | ☑ 自动 + ☐ 手工 | Vitest `AppBootstrap.test.tsx`；手工：kill serve 后重试钮 |
| daemon 未运行 | stopped 卡 + ▶ 启动 | ☐ 手工 | 无 `monitor watch --daemon` 时左栏底卡 |
| daemon 已运行 | ⏹ 停止（可点） | ☐ 手工 | 守护进程运行时按钮文案 |
| FLV 代理失败 | 「流不可用，字幕仍更新」 | ☐ 手工 | 断流或 mock 403 |
| 无 DEEPGRAM / partial | 「等待转写」或 final | ☐ 手工 | legacy 场次或无 streaming |
| LLM 失败 | toast + error 文案 | ☐ 手工 | 错误 API key 或断网 |
| 未登录平台 | 配置/管理登录钮 + stale | ☐ 手工 | 删 session 后列表标记 |
| PATCH 400 | toast + 字段高亮 | ☑ 自动 | `test_api_config` 校验路径 |
| 需重启 daemon | 成功 toast + 重启提示 | ☐ 手工 | 改 `pipeline_mode` 等 |

---

## 扩展冒烟（Task 38）

| 项 | 状态 | 操作说明 |
|----|------|----------|
| 空列表 CTA | ☐ 手工 | `?empty-list=1` 或零监控博主 →「添加博主」 |
| AppBootstrap 重试 | ☑ 自动 | `AppBootstrap.test.tsx` error + 重试 |
| 色盲模拟 | ☐ 手工 | Chrome DevTools → Rendering → Emulate vision deficiency（去饱和）；确认灯有 `aria-label`/abbr（Vitest StatusLight） |
| ≤768px 双 rail | ☑ 自动 | `responsive.test.ts` + `layout.css` `@media (max-width: 768px)` |

---

## 非目标（本单不验）

- Playwright E2E 进 CI
- Windows/Linux 打包
- 新功能 scope
