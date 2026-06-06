# m2t-desktop Agent Pane PR1：历史转写/摘要 API + display_label

## 背景

桌面端 Agent 面板与布局预设（规格 [2026-06-06-m2t-desktop-agent-pane-design.md](../superpowers/specs/2026-06-06-m2t-desktop-agent-pane-design.md)）依赖 **P0 后端**：统一历史内容读取路由（D1），以及场次下拉用的 `display_label`（§14.3 B）。

当前 `GET /api/sessions/{id}/transcript` 仅支持 live UUID；VOD 的 `aweme_id` 会 404。桌面端必须改用 `GET /api/creators/{id}/history/{kind}/{item_id}/transcript|summary`。

**参考**

- 实施计划：[2026-06-06-m2t-desktop-agent-pane.md](../superpowers/plans/2026-06-06-m2t-desktop-agent-pane.md) — Task 1–3
- 复用：`history_media._resolve_media_path`、`read_transcript_payload` / `read_summary_text`

**依赖**：无（本系列首单）。**阻塞**：PR2–PR4。

## 验收标准

### Task 1 — `history_content` 服务

- [ ] 新增 `src/media2text/api/services/history_content.py`
- [ ] `resolve_history_media_path(conn, workspace, creator_id, kind, item_id)` 支持 `kind=live|vod`，404 场景返回 `None`
- [ ] `read_history_transcript` / `read_history_summary` 在 item 不存在或无 sidecar 时返回 HTTP 404
- [ ] live 路径解析复用 manifest + `LiveSessionRepo`；vod 复用 `AwemeRepo` + manifest

### Task 2 — HTTP 路由

- [ ] `GET /api/creators/{creator_id}/history/{kind}/{item_id}/transcript` 返回 `{ ok, text, segments, ... }`
- [ ] `GET /api/creators/{creator_id}/history/{kind}/{item_id}/summary` 返回 `{ ok, text, summary_path }`
- [ ] `kind` 非法 → 422
- [ ] **回归（CRITICAL）**：`GET /api/sessions/{aweme_id}/transcript` 对 VOD aweme_id 仍为 404（禁止误用 sessions 路由读作品）

### Task 3 — `display_label`

- [ ] `GET /api/creators/{id}/sessions` 的 live 项含 `display_label`（如 `2026-06-02 21:04 直播`）
- [ ] vod 项 `display_label` 为作品标题或 `aweme_id` 回退

### 测试

- [ ] `pytest tests/unit/test_history_content.py -v`
- [ ] `pytest tests/unit/test_api_history_transcript.py -v -m desktop`
- [ ] `pytest tests/unit/test_api_sessions_list.py -v -m desktop`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_history_content.py tests/unit/test_api_history_transcript.py tests/unit/test_api_sessions_list.py -v -m desktop
ruff check src/media2text/api/services/history_content.py src/media2text/api/routes/creators.py src/media2text/api/services/sessions_list.py
```

## 非目标范围

- Node sidecar / React 布局 / Agent 多 Tab UI（PR2–PR4）
- B 站 archive/dynamic 进 history 路由（P2）
- 修改 `GET /api/sessions/{uuid}/transcript` 的 live 行为

## 实现备注

- 分支：`issue-170-desktop-history-api`
- GitHub Issue: [#170](https://github.com/oychao1988/media2text/issues/170)
- 合并后开 PR2 Issue [#171](https://github.com/oychao1988/media2text/issues/171)
