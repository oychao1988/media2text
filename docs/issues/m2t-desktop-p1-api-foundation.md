# m2t-desktop P1：FastAPI 骨架 + daemon / 博主 / 配置 API

## 背景

在 P0 Core 就绪后，交付可独立运行的 `media2text serve`（`127.0.0.1:8765`），覆盖 health、daemon 启停、博主列表与 CRUD、配置 GET/PATCH，为 Tauri 与后续会话/流代理提供 HTTP 基座。

**参考**

- 架构 §4.1、§5 API 表：[2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- 计划 Phase 1–2 Task 5–12：[2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)

## 验收标准

### Task 5 — FastAPI 骨架

- [ ] `pyproject.toml` extra `desktop`（fastapi、uvicorn、websockets）
- [ ] `media2text.api` 包、`create_app()`、`media2text serve --port 8765` 仅绑定 loopback
- [ ] `GET /api/health`（含 Doctor 摘要缓存：ffmpeg / playwright / deepgram extra）
- [ ] `POST /api/doctor/run`（重新跑 doctor 并更新 health 缓存；设计 §5）
- [ ] `tests/unit/test_api_health.py`

### Task 6 — `safe_workspace_path`

- [ ] 拒绝 `../` 等路径穿越；允许 workspace 内相对路径
- [ ] `tests/unit/test_api_security.py`

### Task 7 — 配置 DTO + HTTP 路由

- [ ] `config_dto.py`：camelCase DTO ↔ `AppConfig`；`PATCH` 合并；`clearFeishuWebhook` 等边界
- [ ] `routes/config.py`：`GET /api/config`、`PATCH /api/config`（设计 §4.7.3 映射表）
- [ ] `PATCH` 响应含 `requires_daemon_restart` / `requires_agent_reload`（供 UI toast）
- [ ] `tests/unit/test_api_config_dto.py`、`tests/unit/test_api_config.py`

### Task 8 — Daemon 路由

- [ ] `GET /api/daemon`、`POST start/stop`、`GET logs?tail=N`；复用 PID 锁语义
- [ ] `tests/unit/test_api_daemon.py`（`@pytest.mark.desktop`）

### Task 9 — 状态灯聚合

- [ ] `core/desktop/status_lights.py`：DB → `green|yellow|red|gray` + `is_live`
- [ ] 单元测试 fixture DB

### Task 10 — `GET /api/creators`

- [ ] 默认仅 `monitor_enabled=1`；`?all=1` 含未监控；JSON 含灯色与 badge 字段
- [ ] `tests/unit/test_api_creators_list.py`

### Task 11 — 博主 CRUD + `auto_record_override`

- [ ] `GET /api/creators/{id}`（详情 + latest session + live_snapshot + override）
- [ ] `POST/PATCH/DELETE`；`PATCH` 支持 `autoRecordOverride`
- [ ] `tests/unit/test_api_creators_crud.py`

### Task 12 — sync / delete / auth

- [ ] `POST .../sync-profile`、`POST .../sync`（catalog）、`POST .../sync-dynamics`（仅 bilibili）
- [ ] `DELETE /api/creators/{id}`（可选 `?delete_media=`；二次确认由 UI 负责）
- [ ] `POST /api/auth/login/{platform}`（douyin / bilibili / aliyundrive）、`GET /api/auth/status`
- [ ] `tests/unit/test_api_creators_sync.py`、`test_api_auth.py`

### 质量

- [ ] `pip install -e ".[desktop,dev]"` 后上述 pytest 全绿
- [ ] `pyproject.toml` 增加 `markers = ["desktop: ..."]`；API 测试打标

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
ruff check src tests
pytest tests/unit/test_api_health.py tests/unit/test_api_security.py \
  tests/unit/test_api_config_dto.py tests/unit/test_api_config.py tests/unit/test_api_daemon.py \
  tests/unit/test_api_creators_list.py tests/unit/test_api_creators_crud.py \
  tests/unit/test_api_creators_sync.py tests/unit/test_api_auth.py -v -m desktop

# 冒烟
media2text serve --port 8765 &
curl -s http://127.0.0.1:8765/api/health | jq .
kill %1
```

## 非目标范围

- FLV 代理、transcript WS、chat、events WS（P2/P3 Issue）
- React / Tauri UI
- 业务逻辑重复实现于前端（D6：写操作必须走 core）

## 依赖与顺序

- **依赖**：[#125](https://github.com/oychao1988/media2text/issues/125) P0 Core
- **阻塞**：P2 会话 API、P4 Tauri sidecar 联调

## 实现备注

- GitHub Issue: [#126](https://github.com/oychao1988/media2text/issues/126)
- 分支：`issue-126-m2t-desktop-p1-api-foundation`
- 实现时决策（计划 eng review）：`packages/shared/api-types.ts` v1 可本 PR 起草案或下 PR 补
