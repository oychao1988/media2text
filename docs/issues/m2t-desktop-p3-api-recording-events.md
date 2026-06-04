# m2t-desktop P3：API 手动录制 / 快照 / Chat / Events WS

## 背景

🔴 在播未录 + 手动开录、daemon 写 `creator_live_snapshots`、Agent 对话 SQLite 持久化，以及左栏状态灯实时刷新，需要录制 API、chat 路由与全局 events WebSocket hub。

**参考**

- 架构 §4.4、§4.6.8、§5：[2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- 计划 Phase 4 Task 18–21：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)

## 验收标准

### Task 18 — 手动录制 start/stop

- [ ] `POST /api/creators/{id}/recording/start`、`.../stop`；复用 `start_recording_for_creator` / finalize
- [ ] `tests/unit/test_api_recording.py`

### Task 19 — Live snapshot（daemon hook）

- [ ] daemon poll 后 upsert `creator_live_snapshots`；供 🔴 灯与 poll 缓存
- [ ] `POST /api/creators/{id}/live/refresh`：按需刷新 snapshot（**30s** rate limit / 429）
- [ ] 单测或集成测验证 upsert 与 refresh

### Task 20 — Chat 持久化

- [ ] threads：`GET/POST/PATCH/DELETE /api/chat/threads/{id}`；messages：`GET/POST .../messages`
- [ ] `GET /api/chat/providers`（从 `summarize.llm` 解析）
- [ ] `tests/unit/test_api_chat.py`

### Task 21 — Events WebSocket hub

- [ ] `WS /api/events` 广播；事件类型含 `creator.updated` 等（建议 `api/schemas/events.py` 枚举）
- [ ] **heartbeat**：服务端每 30s `ping`（eng review 默认）
- [ ] `tests/unit/test_api_events_ws.py`

### 质量

- [ ] P1–P3 API 测试 `pytest tests/unit/test_api_* -v -m desktop` 全绿（允许分文件增量合并）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_api_recording.py tests/unit/test_api_chat.py \
  tests/unit/test_api_events_ws.py -v -m desktop
```

## 非目标范围

- Node Agent sidecar / PiEvent（P7 Issue）
- 中栏「停止录制」按钮（v1 仅 API + Agent tool）
- LLM 推理在 Python API 内执行

## 依赖与顺序

- **依赖**：[#125](https://github.com/oychao1988/media2text/issues/125)、[#126](https://github.com/oychao1988/media2text/issues/126)；与 [#127](https://github.com/oychao1988/media2text/issues/127) 可并行
- **阻塞**：P6 博主列表 WS、P7 Agent chat UI

## 实现备注

- GitHub Issue: [#128](https://github.com/oychao1988/media2text/issues/128)
- 分支：`issue-128-m2t-desktop-p3-api-recording-events`
