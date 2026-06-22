# m2t-desktop — 中栏「本地」Tab（博主外部媒体登记）

**日期:** 2026-06-10  
**状态:** 已批准（产品决策已锁定，待实现）  
**前置:** [m2t-desktop 总规格](./2026-06-04-m2t-desktop-design.md)、[UI 设计系统](./2026-06-04-m2t-desktop-ui-design.md)、[Agent 上下文附件](./2026-06-09-m2t-desktop-agent-context-attachments-design.md)  
**CLI 行为参考:** `media2text transcribe run`、`media2text summarize run`（sidecar 与 core 一致）

---

## 0. 背景与范围

### 0.1 动机

现有中栏 **直播 / 历史** Tab 只覆盖 **监控 pipeline** 产出的内容（DB session、VOD、manifest）。用户常有 **本机任意路径** 的音视频或文档，希望：

- 在 **当前选中博主** 语境下登记、浏览、预览；
- 手动触发 **转写 / 摘要**（与 daemon 解耦）；
- 右栏 **TranscriptPane + Agent** 与历史场次体验一致。

### 0.2 已锁定产品决策（2026-06-10）

| ID | 问题 | 决策 |
|----|------|------|
| P1 | Tab 作用域 | **绑定博主** — 列表按 `creator_id` 过滤；中栏标题仍为博主名 + badge |
| P2 | 文件路径 | **允许任意本机绝对路径** — 不强制复制进 `data/` workspace |
| P3 | 文件夹登记 | **一次性扫描入库** — 登记时对子树 glob 写入 DB；日常打开 Tab **不**自动重扫；用户点 **刷新** 可增量扫描同一登记根目录 |
| P4 | 路径唯一性 | **同一绝对路径全局仅登记给一个博主** — DB `abs_path` UNIQUE；登记冲突时返回明确错误 |
| P5 | 移除登记 | **只删 DB 行，不删磁盘** — 原文件与 sidecar 保留 |
| P6 | Sidecar 位置 | **写在源媒体旁** — 复用 core `write_transcript_outputs` / `write_summary`（与 CLI 一致） |

### 0.3 范围

| 在范围内 | 不在范围内 |
|----------|------------|
| 中栏第三 Tab「本地」+ `ViewLocal` 列表 UI | 编辑 / 保存转写或摘要正文 |
| Tauri 选文件 / 选文件夹 → API 登记 | PDF / Office 解析 |
| `creator_local_items` 表 + CRUD + 异步转写/摘要 job | 自动 inotify 监视文件夹 |
| `GET .../local/items/{id}/media` Range 代理（任意路径） | 跨博主共享同一登记 |
| 右栏 `TranscriptPane` `mode: 'local'` | 写入 `agent-manifest.json`（v1） |
| Agent `@` / 场次 chip 扩展 local 文档（P2，见 §8） | 从列表删除磁盘原文件 |
| `--json` API 字段与 Desktop 集成测试 | 全文检索 / FTS |

---

## 1. 信息架构

### 1.1 中栏 Tab

```
Tab: [ 直播 | 历史 | 本地 ]
```

| 状态 | 行为 |
|------|------|
| 未选博主 | 与历史 Tab 相同空态：「请先选择博主」 |
| 已选博主 | 列表仅含 `creator_id = 当前博主` 的登记项 |
| 选中列表行 | 中栏预览 + 右栏转写/摘要；`transcriptSelection.mode = 'local'` |

**与 `CenterView` 关系：**

- `centerTab`: `'live' | 'history' | 'local'`（新增 `'local'`）
- 本地 Tab **无** 独立 `playback` 子视图；预览在中栏 `ViewLocal` 内嵌（复用 `ViewPlayback` 子组件或等价 `<video>` / 文本预览）

### 1.2 本地 Tab 布局（参考 `HistoryPanel`）

**可交互原型（模块化）：** [panels/local-tab.html](../designs/m2t-desktop/panels/local-tab.html) 由 [finalized.html](../designs/m2t-desktop/finalized.html) 通过 `fetch` 注入 `#view-local`；样式见 [panels/local-tab.css](../designs/m2t-desktop/panels/local-tab.css)。

```
┌─────────────────────────────────────────────────────────┐
│ [+ 添加文件] [+ 添加文件夹] [刷新]                        │
│ 筛选: 全部 | 待转写 | 待摘要          搜索: ________     │
├─────────────────────────────────────────────────────────┤
│ ▶ /Volumes/ext/interview.mp4              1:02:33       │
│   video · ✓转写 · ✗摘要 · 源✓                            │
│   [预览] [转写] [摘要] [移除]                             │
│ ▶ ~/notes/meeting.md                                    │
│   document · —转写 · ✓摘要 · 源✓                       │
│   [预览] [摘要] [移除]                                    │
└─────────────────────────────────────────────────────────┘
```

**行内 tag 语义（与历史 Tab 对齐）：**

| Tag | 含义 |
|-----|------|
| `✓转写` / `无转写` | sidecar `.transcript.json` 存在且可读 |
| `✓摘要` / `无摘要` | `.summary.md` 存在 |
| `源✓` / `源缺失` | 登记 `abs_path` 仍指向存在文件 |
| `转写中…` / `摘要中…` | job `running` |

### 1.3 类型与操作

| `media_kind` | 扩展名（v1 白名单） | 预览 | 转写 | 摘要 |
|--------------|---------------------|------|------|------|
| `video` | `.mp4`, `.mkv`, `.webm`, `.flv`, `.mov` | flv.js / `<video>` | ✓ | 需先有转写 |
| `audio` | `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg` | `<audio>` | ✓ | 需先有转写 |
| `document` | `.md`, `.txt` | 文本 / Markdown | 跳过（UI 隐藏） | ✓ 直接对正文 |

**文件夹登记（P3）：**

1. 用户选目录 `D`；
2. API 对 `D` 递归 glob 白名单扩展名（**不**跟随 symlink 出目录）；
3. 每个匹配文件插入一行 `creator_local_items`（`scan_root_id` 可选，便于「刷新」）；
4. 已存在 `abs_path`（任意博主）→ **跳过** 并计入 `skipped_duplicate`；
5. 响应汇总：`added`, `skipped_duplicate`, `skipped_unsupported`。

**刷新（同一 scan root）：**

- `POST /api/creators/{id}/local/scan-roots/{root_id}/refresh` — 仅对该 root 再 glob，**新增**文件入库；不删除已登记但源已删的行（标 `source_missing`）。

---

## 2. 数据模型

### 2.1 表 `creator_local_items`

```sql
CREATE TABLE creator_local_items (
  id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  abs_path TEXT NOT NULL,
  display_name TEXT NOT NULL,
  media_kind TEXT NOT NULL,  -- video | audio | document
  scan_root_id TEXT,         -- nullable; 文件夹批次 id
  file_size INTEGER,
  file_mtime REAL,
  transcribe_status TEXT NOT NULL DEFAULT 'none',
  summary_status TEXT NOT NULL DEFAULT 'none',
  transcript_path TEXT,
  summary_path TEXT,
  last_error TEXT,
  added_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(abs_path)
);
CREATE INDEX idx_local_items_creator ON creator_local_items(creator_id);
CREATE INDEX idx_local_items_scan_root ON creator_local_items(scan_root_id);
```

**`transcribe_status` / `summary_status` 枚举：**

`none` | `pending` | `running` | `done` | `failed` | `skipped`（document 转写）

**Sidecar 路径解析（服务端）：**

- 媒体 `M`：`M.with_suffix('.transcript.json')`、`.summary.md`（与 core 一致）
- 文档 `D.md`：`D.with_suffix('.summary.md')` 或通过 `summary_paths_for_media(D)`

登记 / job 完成 / 列表 GET 时 **探测 sidecar 是否存在**，同步更新 `transcript_path`、`summary_path` 与 status（允许用户用 CLI 在外部生成 sidecar 后点刷新对齐）。

### 2.2 表 `creator_local_scan_roots`（可选，推荐）

```sql
CREATE TABLE creator_local_scan_roots (
  id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  abs_path TEXT NOT NULL,
  added_at TEXT NOT NULL,
  UNIQUE(creator_id, abs_path)
);
```

用于 P3「刷新文件夹」与 UI 分组（「来自 ~/Recordings/…」）。

### 2.3 异步任务 `creator_local_jobs`

复用 post_process **模式**（独立 worker 线程 / 进程内 queue），不阻塞 HTTP：

```sql
CREATE TABLE creator_local_jobs (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES creator_local_items(id) ON DELETE CASCADE,
  job_type TEXT NOT NULL,  -- transcribe | summarize
  status TEXT NOT NULL,    -- pending | running | done | failed
  force INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
```

Daemon `PostProcessPool` **不**消费此队列；Desktop API lifespan 或专用 `LocalJobPool`（max_parallel 可配置，默认 1，避免 Whisper CPU 争抢）。

---

## 3. 安全与路径访问

### 3.1 原则

- 客户端 **永不** 在 query 中传绝对路径读取媒体；
- 所有读文件经 **`item_id` → DB `abs_path`**；
- 登记时 `path.resolve()`；拒绝 `..` 组件；目录扫描不跟随 symlink。

### 3.2 与 `safe_workspace_path` 的关系

现有 `GET /api/media?path=` **仍仅 workspace 相对路径**。本地项使用 **新路由**：

```
GET /api/creators/{creator_id}/local/items/{item_id}/media
Range: bytes=...
```

实现：查 row → `Path(abs_path)` → `FileResponse` / Range（逻辑可复制 `routes/media.py`）。

### 3.3 登记冲突（P4）

```json
{
  "ok": false,
  "error": "path_already_registered",
  "existing_creator_id": "...",
  "existing_item_id": "..."
}
```

HTTP **409**。UI toast：「该文件已登记给其他博主」。

---

## 4. HTTP API

前缀：`/api/creators/{creator_id}/local`

### 4.1 `GET /items`

Query: `has_transcript`, `has_summary`, `q`（display_name / abs_path 子串）

```json
{
  "ok": true,
  "items": [
    {
      "id": "uuid",
      "creator_id": "...",
      "display_name": "interview.mp4",
      "abs_path": "/Volumes/ext/interview.mp4",
      "media_kind": "video",
      "scan_root_id": null,
      "file_size": 123456789,
      "file_mtime": 1718000000.0,
      "source_present": true,
      "has_transcript": true,
      "has_summary": false,
      "transcribe_status": "done",
      "summary_status": "none",
      "transcript_path": "/Volumes/ext/interview.transcript.json",
      "summary_path": null,
      "last_error": null,
      "added_at": "2026-06-10T12:00:00Z"
    }
  ]
}
```

**注意：** 响应含 `abs_path` 供 Desktop 展示与「在 Finder 中显示」；Agent tools 只用 `item_id`。

### 4.2 `POST /items`

Body:

```json
{ "path": "/absolute/or/~/expanded/path/to/file.mp4" }
```

- 展开 `~`；`resolve()`；验文件存在；
- 推断 `media_kind`；插入行；
- 若 sidecar 已存在 → 同步 status。

### 4.3 `POST /scan-roots`

Body:

```json
{ "path": "/absolute/path/to/folder" }
```

响应:

```json
{
  "ok": true,
  "scan_root_id": "uuid",
  "added": 12,
  "skipped_duplicate": 2,
  "skipped_unsupported": 5,
  "items": [ "... id list or full rows ..." ]
}
```

### 4.4 `POST /scan-roots/{root_id}/refresh`

增量扫描；返回新增计数。

### 4.5 `DELETE /items/{item_id}`

删除 DB 行；**不**删磁盘与 sidecar。

### 4.6 `GET /items/{item_id}/media`

视频/音频流；`Content-Type` + `Accept-Ranges`。

### 4.7 `GET /items/{item_id}/transcript`

```json
{ "ok": true, "text": "...", "segments": [...], "path": "..." }
```

无 sidecar → 404 或 `{ "ok": true, "text": "", "segments": [] }`（与 session transcript 对齐）。

### 4.8 `GET /items/{item_id}/summary`

```json
{ "ok": true, "text": "...", "summary_path": "..." }
```

### 4.9 `POST /items/{item_id}/transcribe`

Query: `force=false`

- `document` → 400 `transcribe_not_applicable`
- 源缺失 → 409 `source_missing`
- 已有 sidecar 且非 force → 200 `{ "skipped": true }`
- 否则 enqueue job → 202 `{ "job_id": "...", "status": "pending" }`

Worker：复用 `create_transcribe_backend` + `write_transcript_outputs`；更新 row。

### 4.10 `POST /items/{item_id}/summarize`

Query: `force=false`

- 音视频无转写 → 409 `transcript_required`
- Worker：复用 `summarize_one(item.abs_path, cfg, backend, force=...)`

### 4.11 `GET /jobs/{job_id}`

轮询 job 状态（UI 3s 间隔或 WS `local_job` 事件 P2）。

---

## 5. 前端（React / Tauri）

### 5.1 改动清单

| 文件 | 变更 |
|------|------|
| `layoutConstants.ts` | `CenterTab` 含 `'local'` |
| `CenterToolbar.tsx` | 第三 Tab「本地」 |
| `useLayoutStore.ts` | `setCenterTab('local')` |
| `AppShell.tsx` | 挂载 `ViewLocal`；`transcriptSelection` local 分支 |
| `ViewLocal.tsx` | 新建；列表 + 预览区 |
| `TranscriptPane.tsx` | `mode: 'local'`；API 路径；转写/摘要按钮 |
| `transcriptSelection.ts` | `LocalTranscriptSelection` 类型 |
| Tauri | `@tauri-apps/plugin-dialog` 选文件/目录；`open`  reveal（可选） |

### 5.2 Tauri 选路径流程

```
用户点击「添加文件」
  → dialog.open({ multiple: false, filters: [...] })
  → POST /api/creators/{selectedId}/local/items { path: selected }
  → 刷新列表；选中新行
```

文件夹同理 → `POST /scan-roots`。

### 5.3 右栏 `TranscriptPane`

| 字段 | local 模式 |
|------|------------|
| `sessionId` | null |
| `localItemId` | item.id |
| `transcriptPath` | 仅展示用；加载走 GET transcript |
| `mode` | `'local'` |
| WS | **不**连接 session transcript WS |
| 摘要按钮 | `POST .../summarize`（与 history playback 类似） |

### 5.4 布局预设

| 预设 | 本地 Tab 行为 |
|------|----------------|
| `full` | 中栏列表 + 预览；转写在右栏上部 |
| `transcript-chat` | 中栏可仅列表或列表+预览（与历史 playback 一致：预览占中栏 body） |
| `chat-only` | 隐藏转写区；Agent 仍可用 |

---

## 6. Agent 集成（P2，建议紧随 v1 UI）

| 项 | 方案 |
|----|------|
| 场次 chip | 选中 local 行 → 提供 `sessionKind: 'local'` + `itemId` |
| `@` 列表 | 扩展索引：当前博主 `GET /local/items` 中有 sidecar 的项 |
| `context.refresh` | 增加 `localItemId`；paths 仍用绝对 sidecar path 或 API 相对封装 |
| Tools | `m2t_read_local_transcript` / `m2t_read_local_summary`（by item_id） |

v1 可仅支持 **右栏手动复制** + 现有 `@` 不索引 local；Agent 只读当前选中项 transcript GET。

---

## 7. 与 CLI / core 一致性

| 操作 | core 入口 |
|------|-----------|
| 转写 | `create_transcribe_backend` → `transcribe` → `write_transcript_outputs` |
| 摘要 | `summarize_one` |
| 引擎不可用 | 与 history summarize 相同错误码：`transcribe_unavailable` / `summarize_disabled` |

**不**调用 CLI 子进程；API 直接 import core（符合 D6）。

---

## 8. 验收标准（AC）

| ID | 条件 |
|----|------|
| L1 | 选中博主 A，登记 `/tmp/a.mp4`，切博主 B 列表不可见 |
| L2 | 同一 `/tmp/a.mp4` 登记给 B 时返回 409 |
| L3 | 登记 workspace **外**路径，≤3s 内中栏预览首帧 / 音频可播 |
| L4 | 文件夹一次性扫描 50 个文件，≤10s 入库（不含转写） |
| L5 | 转写完成后 sidecar 在 **源路径旁**，非 `data/` |
| L6 | 文档 `.md` 无转写按钮；摘要成功生成 `.summary.md` |
| L7 | 移除登记后磁盘与 sidecar 仍在；重新登记可识别已有 sidecar |
| L8 | 重启 Desktop 后列表与 status 与 sidecar 一致 |
| L9 | 未登记路径无法通过 API 读取（无 item_id 旁路） |
| L10 | `pytest tests/unit/test_api_local_*` + `pnpm --filter m2t-desktop test` 通过 |

---

## 9. 实现顺序

1. **Migration** + repos：`creator_local_items`（+ scan_roots、jobs）
2. **API routes** + services：登记、列表、media Range、sidecar GET
3. **LocalJobPool** + transcribe/summarize worker
4. **Desktop UI**：Tab + ViewLocal + dialog
5. **TranscriptPane** local mode
6. **Agent** 扩展（P2）
7. **文档**：README / CLAUDE.md 命令速查一行（可选）

---

## 10. 验证命令（Issue 模板）

```bash
source .venv/bin/activate
pytest tests/unit/test_api_local_* tests/unit/test_desktop_local_* -v -m desktop
pnpm --filter m2t-desktop test
ruff check src/media2text/api/routes/local_media.py src/media2text/api/services/local_media.py
pyright
```

手动：

1. `pnpm --filter m2t-desktop tauri dev`
2. 选博主 → 本地 Tab → 添加 workspace 外 mp4 → 预览 → 转写 → 右栏出字
3. 添加 `.md` → 直接摘要
4. 换博主确认列表隔离；重复登记确认 409

---

## 11. 相对总规格的修订

| 项 | [2026-06-04 总规格](./2026-06-04-m2t-desktop-design.md) | **本文** |
|----|----------------------------------------------------------|----------|
| 中栏 Tab | 直播 \| 历史 | 直播 \| 历史 \| **本地** |
| 媒体路径 | workspace + `/api/media` | 新增 **item_id 代理任意绝对路径** |
| 转写入口 | daemon / post_process | 用户 **手动** + local job queue |
| manifest | agent-manifest 索引 | v1 **不**写入 local 块 |
