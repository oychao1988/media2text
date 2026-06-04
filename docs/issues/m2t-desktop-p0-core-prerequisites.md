# m2t-desktop P0：Core 前置（config / DB / 自动开录 / 抖音 poll）

## 背景

桌面端（Tauri + FastAPI sidecar）依赖现有 `media2text.core`，但需先扩展配置、SQLite 表、自动开录语义与抖音独立 live poll，否则 API 与 daemon 行为会漂移。

**参考**

- 架构：[docs/superpowers/specs/2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md) §4.4、§4.6.8、§4.7
- 计划 Phase 0 Task 1–4：[docs/superpowers/plans/2026-06-04-m2t-desktop.md](../superpowers/plans/2026-06-04-m2t-desktop.md)

## 验收标准

### Task 1 — 配置字段

- [ ] `AppConfig` 增加：`live.auto_record`（默认 `true`）、`desktop.*`、`platforms.douyin.live_poll_interval_sec`、`summarize.llm.default_provider` / `default_model`
- [ ] `config.example.yaml` 文档化上述键
- [ ] `summarize/openai_backend.py`：未显式传 provider/model 时 honor `default_provider` / `default_model`
- [ ] `tests/unit/test_desktop_config.py` 覆盖默认值与解析；`tests/unit/test_summarize_default_provider.py`（或等价）覆盖 backend 默认

### Task 2 — DB migration `desktop_v1`

- [ ] `_migrate_desktop_v1`：`creator_live_snapshots`、`desktop_chat_*`、`creators.auto_record_override`
- [ ] `CreatorRow`、`LiveSnapshotRepo`、`DesktopChatRepo` 最小 CRUD
- [ ] `tests/unit/test_desktop_db_migration.py`

### Task 3 — `effective_auto_record` + 扫描门控

- [ ] `effective_auto_record(creator, cfg)`：`inherit` / `on` / `off`
- [ ] `recording.py` `scan_and_start` 在 `_start_recording` 前门控
- [ ] `tests/unit/test_effective_auto_record.py`、`test_live_recording_auto_record.py`

### Task 4 — 抖音 per-platform live poll

- [ ] `douyin/live.py` poll 间隔：平台值 → `live.live_poll_interval_sec` → `monitor.live_poll_interval_sec`
- [ ] `tests/unit/test_douyin_live_poll.py`

### 质量

- [ ] `pytest tests/unit/test_desktop_*.py tests/unit/test_effective_auto_record.py tests/unit/test_live_recording_auto_record.py tests/unit/test_douyin_live_poll.py -v`
- [ ] `ruff check src tests`；`pyright` 无新增 error

## 验证命令

```bash
source .venv/bin/activate
ruff check src tests
pyright
pytest tests/unit/test_desktop_config.py tests/unit/test_desktop_db_migration.py \
  tests/unit/test_effective_auto_record.py tests/unit/test_live_recording_auto_record.py \
  tests/unit/test_douyin_live_poll.py -v
```

## 非目标范围

- FastAPI / Tauri / React（后续 Issue）
- 修改 `monitor watch` 三线程架构
- Windows/Linux 打包

## 依赖与顺序

- **无前置 Issue**；本单为 m2t-desktop 系列 **#1**，阻塞全部 API/UI Issue。

## 实现备注

- GitHub Issue: [#125](https://github.com/oychao1988/media2text/issues/125)
- 分支建议：`issue-125-m2t-desktop-p0-core`
- 修单 Agent：仅改 `src/media2text/core/`、`config.example.yaml`、`tests/`；勿顺手做 API 路由
