---
issue: 325
epic: live-recording-stability-2026-06-17
github: 325
branch: issue-325-lr1-douyin-live-detection
depends_on: []
spec: docs/superpowers/specs/2026-05-20-media2text-douyin-design.md
---

# LR-1：抖音直播探测修复（错流 / 过期会话 / 匿名回退）

## 背景

2026-06-17 生产事故：

1. **错流录制**：三位财经博主均解析到 `room_id=45865776`（KPL 电竞），转写与视频内容不一致。根因：`resolve_live_via_http()` 在 API 被挡时从 profile HTML **第一个** `live.douyin.com` 链接取房号（平台推广流），且 `parse_profile_live` 在 `live_status≠1` 时仍因 `room_id` 存在判为在线。
2. **过期会话劣于无会话**：`data/sessions/douyin.json` 过期时 profile 页触发 `AuthRequired` 或返回 offline；**匿名 Playwright** 可正确拦截 `profile/other` API。`auth status` 仍显示 `valid: true`（仅首页探测）。
3. **HTTP「成功」阻断 Playwright**：HTTP 路径返回错误 room 后未抛错，Playwright / 匿名回退未执行。

**参考实现**：`src/media2text/core/platform/douyin/{parse,http_live,adapter,playwright_client,live}.py`

## 复现步骤

1. 配置 `monitor watch --daemon`，登记多位 `monitor_enabled` 抖音博主。
2. 使用过期 `douyin.json`（或删除会话文件），对实际在播博主执行 `get_live_room`。
3. 观察：HTTP 返回推广流短 room_id，或 profile API 非 JSON 后 HTML 兜底取错房号；Playwright 未触发。

## 验收标准

### Task 1 — 解析与 HTTP 路径

- [x] `parse_profile_live`：`is_live=True` **仅当** `live_status=1`（`room_id` 单独存在不算在线）
- [x] `parse_profile_html`：优先 `RENDER_DATA`；博主 offline 时**忽略** HTML 内推广直播链接
- [x] `resolve_live_via_http`：仅走签名 API；API 失败时**抛错**触发 Playwright，不做无签名 HTML 兜底

### Task 2 — Playwright 与匿名回退

- [x] `get_live_room`：无有效会话时仍可通过匿名 Playwright 探测
- [x] 会话探测失败（含 `AuthRequired`）后自动尝试匿名上下文；匿名发现 `is_live` 则返回
- [x] `_visit_profile_page`：存在 `RENDER_DATA` 时不因导航栏登录链接触发 `AuthRequired`；支持 `session_path=None`

### Task 3 — 单测

- [x] `tests/unit/test_parse_profile_html.py`：offline + 推广链接 → `is_live=False`
- [x] `tests/unit/test_resolve_live_via_http.py`：API 失败抛错、无 HTML 兜底
- [x] `tests/unit/test_douyin_live_playwright_fallback.py`：匿名回退场景

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_parse_profile_html.py tests/unit/test_resolve_live_via_http.py tests/unit/test_douyin_live_playwright_fallback.py -v
ruff check src/media2text/core/platform/douyin/
```

## 非目标范围

- Live probe 并发与 tick 预算（见 LR-2 #326）
- HLS 重连 / stall 逻辑（见 LR-3 #327）
- 强制用户重新 `auth login` 的 CLI 提示文案（可另开单）
- B 站适配器改动

## 依赖与顺序

- **无前置依赖**（Epic 首单）
- **建议分支**：`issue-325-lr1-douyin-live-detection`

## GitHub

- Issue: [#325](https://github.com/oychao1988/media2text/issues/325)
