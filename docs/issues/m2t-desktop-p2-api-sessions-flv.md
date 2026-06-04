# m2t-desktop P2：API 会话 / 转写 / 媒体 / FLV 代理

## 背景

桌面中栏直播（flv.js）、右栏实时转写（WS）、历史回放与 Range 读文件，需要会话列表、transcript 读写、静态 media 与 HTTP-FLV 反向代理。

**参考**

- 架构 §4.3、§4.5、§4.5a：[2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- 计划 Phase 3 Task 13–17：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)

## 验收标准

### Task 13 — Transcript 读服务

- [ ] `GET /api/sessions/{id}`：session 元数据 + workspace 相对 paths
- [ ] `GET /api/sessions/{id}/transcript`：读 `.transcript.partial.json` / final md+json；路径经 `safe_workspace_path`
- [ ] `GET /api/sessions/{id}/summary`：读 `{basename}.summary.md`（Agent `m2t_read_summary`；UI 摘要 Tab 亦可用 `/api/media?path=`）
- [ ] `tests/unit/test_api_transcript_service.py`

### Task 14 — Transcript WebSocket

- [ ] `WS /api/sessions/{id}/transcript/stream`；partial 变更推送
- [ ] `tests/unit/test_api_transcript_ws.py`

### Task 15 — `GET /api/media`（Range）

- [ ] 支持 Range；正确 Content-Type；拒绝越界路径
- [ ] `tests/unit/test_api_media.py`

### Task 16 — FLV stream proxy

- [ ] `GET /api/sessions/{id}/stream/proxy`；httpx 流式；注入 Referer/Cookie
- [ ] 403/404 时尝试 `resolve_stream_url` 重试（spec §4.3）
- [ ] mock upstream 集成测试

### Task 17 — Sessions + live-groups + manifest

- [ ] `GET /api/creators/{id}/sessions`：合并 DB + manifest；filters `has_transcript` / `has_summary`；含 `live_groups`
- [ ] `GET /api/creators/{id}/manifest`：返回 `agent-manifest.json`（Agent `m2t_read_manifest`）
- [ ] `GET /api/live/status`：字段对齐 CLI `live status`（抽取 `build_live_status()`）
- [ ] `tests/unit/test_api_sessions.py`

### 质量

- [ ] 各路由至少 1 happy + 1 error path
- [ ] `@pytest.mark.desktop` 标记

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_api_transcript_service.py tests/unit/test_api_transcript_ws.py \
  tests/unit/test_api_media.py tests/unit/test_api_sessions.py \
  tests/unit/test_api_flv_proxy.py -v -m desktop
```

## 非目标范围

- flv.js 前端播放器（P6/P7 UI Issue）
- 编辑转写/摘要正文
- HLS 转封装

## 依赖与顺序

- **依赖**：[#126](https://github.com/oychao1988/media2text/issues/126) P1 API
- **可与** P3 recording/events Issue 并行开发（不同路由文件）

## 实现备注

- GitHub Issue: [#127](https://github.com/oychao1988/media2text/issues/127)
- 分支：`issue-127-m2t-desktop-p2-api-sessions-flv`
