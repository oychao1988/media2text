# P0 Archive 索引基础（schema、FTS5、index、转写增量）

> **类型**：功能  
> **建议分支**：`issue-18-archive-index`  
> **GitHub**：[#18](https://github.com/oychao1988/media2text/issues/18)  
> **依赖**：无（P0 第一单）  
> **规格来源**：CEO plan 2026-05-22 + eng plan P0 Lane A

## 背景

财经直播情报工作台 P0 的核心是「复盘可检索」。当前转写产物为 `*.transcript.json`（含 `segments[]`），但 SQLite 无全文索引，`media2text` 无法跨场次搜索。

本单建立 `core/archive/` 索引层：`transcript_segments` 表 + FTS5，CLI `archive index`，并在转写完成时**自动增量 upsert**（eng review D1 已确认）。全量修复用 `archive index --rebuild`。

## 验收标准

### Schema 与索引器

- [ ] DB 迁移：`transcript_segments` 表字段与 eng plan 一致（`session_type` live|vod、`session_id`、`creator_id`、`sec_uid`、`media_path`、`transcript_path`、`segment_index`、`start_sec`、`end_sec`、`text`、`started_at`、`indexed_at`；`UNIQUE(transcript_path, segment_index)`）。
- [ ] FTS5 虚拟表 `transcript_fts` 与 content 表联动；重建索引时 FTS 与行表一致。
- [ ] `core/archive/indexer.py`：从 `.transcript.json` 解析 `TranscriptSegment`，关联 `live_sessions` / `awemes` 取 `started_at`。
- [ ] 损坏或缺失的 transcript 文件：跳过并计入 `skipped`，不中断整批 index。

### CLI

- [ ] 注册 Typer 子命令组 `media2text archive`（在 `cli/main.py`）。
- [ ] `archive index [--creator <id>] [--rebuild] [--json]`：增量或全量；JSON 含 `indexed`、`skipped`、`errors`（如有）。
- [ ] `--rebuild` 清空段表与 FTS 后重扫 workspace 下已有 transcript。

### 转写完成 hook

- [ ] 直播/作品转写成功写入 `.transcript.json` 后，调用增量 upsert（复用 indexer，单文件路径）。
- [ ] hook 失败仅 `log.warning`，不导致转写命令失败（索引可稍后 `archive index` 补救）。

### 测试

- [ ] `tests/unit/test_archive_indexer.py`：临时 workspace + 假 transcript JSON；upsert 幂等；rebuild；损坏 JSON 跳过。
- [ ] 现有 `pytest tests/ -v` 全绿。

## 验证命令

```bash
source .venv/bin/activate
ruff check src tests
pyright
pytest tests/unit/test_archive_indexer.py tests/ -v

# 手工（需 ./data 内至少一场带 .transcript.json 的录制）
media2text archive index --json
media2text archive index --rebuild --json
# 转写一场后无需手动 index 即能在 DB 中看到段（可用 sqlite3 data/media2text.db 抽查）
```

## 非目标范围

- `archive search` / `archive timeline`（下一单）。
- `compliance accept` 门禁（下一单）。
- `pricing-log`、E6 实验（第三单）。
- Tauri 桌面、女娲 skill 向导、notify/飞书重构。
- 修改 `sessions/douyin.json` 或上传索引到云端。

## 实现提示（给修单 Agent）

- 复用：`TranscriptSegment`、`open_db`、`AppConfig.ensure_workspace()`、`manifest` 中 transcript 路径约定。
- 新包：`src/media2text/core/archive/`（`indexer.py`、`models.py` 等）。
- 分支从 `origin/main` 最新切出；PR 使用 `Fixes #<N>`。

## 待确认（实现前可评论 Issue）

- FTS5 中文分词：默认 `unicode61` 是否满足「半导体」类关键词；若不足，在 PR 说明 tokenizer 选择与权衡。
