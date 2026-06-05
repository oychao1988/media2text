# m2t-desktop：监控管理 & 左侧博主栏 UX 优化

## 背景

桌面端「监控管理」（`#view-manage`）与左侧博主列表在 Tauri WebView 环境下存在若干交互与信息展示缺口：

1. **Tauri 限制**：`window.confirm` / `window.open` 在壳内无效，导致「移除博主」「打开主页」无反应。
2. **资料展示**：同步资料后 API 已写入 `avatar_url` / `signature` / `follower_count`，但 Desktop 未展示；外链头像被 CSP 拦截无法直接 `<img src>`。
3. **左侧列表**：仅显示昵称首字，无真实头像；直播博主未置顶；缺少悬停资料预览。

本单在 **不改动 monitor watch 核心语义** 的前提下，补齐 Desktop 管理页与侧栏的可操作性与资料可见性。

**参考**

- Desktop 规格：[m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- 配置/管理 IA：[config-manage-ia.md](../superpowers/specs/2026-06-04-m2t-desktop-config-manage-ia.md)
- 创作者资料 API：`GET /api/creators`、`POST /api/creators/{id}/sync-profile`

## 验收标准

### A — 监控管理交互修复（P0）

- [x] 「移除博主」使用应用内 `ConfirmDialog`（Portal + `role="alertdialog"`），替代 `window.confirm`；确认后调用 `DELETE /api/creators/{id}` 并刷新列表与侧栏。
- [x] 确认弹窗样式与位置对齐 Desktop 设计（overlay 居中、危险操作红色确认按钮）。
- [x] 「打开主页」经 `@tauri-apps/plugin-opener` + `openExternalUrl()` 在 Tauri 与浏览器 dev 环境均可打开 `profile_url`。
- [x] 管理抽屉去掉与资料卡重复的头像顶栏，改为工具栏（打开主页 / 移除）+ 下方设置网格。

### B — 博主资料展示（P0）

- [x] 列表 API `_enrich_creator` 返回 `signature`、`follower_count`、`profile_synced_at`（与 DB 字段一致）。
- [x] 新增 `GET /api/creators/{id}/avatar`：sidecar 代理拉取平台头像（带 Referer），供 Desktop CSP 下加载。
- [x] `sync-profile` JSON 响应包含 `avatar_url`、`signature`、`follower_count`。
- [x] 监控管理列表行与抽屉资料卡展示：头像、昵称、`@unique_id`、平台、简介、粉丝数、同步时间；未同步时提示「点击同步资料」。
- [x] `Creator` 前端类型与 `creatorAvatarUrl()` 辅助函数对齐 API。

### C — 左侧博主栏增强（P1）

- [x] 展开列表（`CreatorList`）与折叠快捷栏（`LeftRail`）使用 `CreatorAvatar` 显示真实头像（经 avatar 代理），失败回退首字。
- [x] `CreatorsContext` 对监控中博主 **直播优先置顶**：录制中 > 直播中 > 离线，同档保持 API 原序。
- [x] 直播高亮（`.is-live` 呼吸环）与 `isCreatorLive()` 一致：含红灯「在播未录」。
- [x] 鼠标悬停博主项（列表 + 折叠栏）显示资料浮窗：头像、昵称、平台、直播状态/标题、简介、粉丝与同步时间；Portal 定位在项右侧，不被侧栏 overflow 裁切。

### 测试

- [x] `pytest tests/unit/test_api_creators_list.py tests/unit/test_api_creators_avatar.py -v -m desktop`
- [x] `pnpm --filter m2t-desktop lint && pnpm --filter m2t-desktop test`（含 `ManagePage.test.tsx`、`CreatorHoverPopover.test.tsx`、`creatorUtils.test.ts`）

## 验证命令

```bash
source .venv/bin/activate
pytest tests/unit/test_api_creators_list.py tests/unit/test_api_creators_avatar.py -v -m desktop

cd apps/m2t-desktop
pnpm lint
pnpm test

# 人工（Tauri 需重启以加载 opener 插件与 avatar 路由）
pnpm --filter m2t-desktop tauri dev
# 1. 监控管理 → 同步资料 → 抽屉与列表见头像/简介
# 2. 左侧列表见头像；直播博主置顶；悬停见浮窗
# 3. 打开主页、移除博主（确认框）可用
```

## 非目标范围

- 不修改 `monitor watch` / daemon 调度逻辑。
- 不在本单实现左侧列表拖拽排序或用户自定义置顶（仅按直播状态自动排序）。
- 不扩展 CSP 直接加载外链图片（继续走 sidecar 代理）。
- 不改造 CLI `creator list` 字段（仅 Desktop API `/api/creators` enrich）。
- 不做监控管理页以外的全局 Toast / 通知改版。

## 待确认问题

无（已在 Tauri dev 环境验证 opener 与 avatar 代理路径）。
