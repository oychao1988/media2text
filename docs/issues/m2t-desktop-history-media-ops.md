# m2t-desktop：历史列表媒体状态与云盘操作

## 背景

桌面端中栏「历史」此前仅展示直播场次，文件名/路径对用户无意义；云盘备份状态常不显示（数据在 `cloud_uploads` 或仅有 `cloud_relative_path`）；无法区分直播与作品（VOD）；缺少删本地、从云下载、删记录等操作。

**参考**

- 桌面规格：[2026-06-04-m2t-desktop-design.md](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- 云备份：[aliyundrive-live-upload.md](./aliyundrive-live-upload.md)

## 验收标准

### API — 列表 enriched

- [ ] `GET /api/creators/{id}/sessions` 合并 **直播**（`live_sessions`）与 **已下载作品**（`awemes`，`sync_status=downloaded|failed`）
- [ ] 每条含 `kind`（`live`|`vod`）、`item_id`、本地 `media_available`、云盘 `cloud_upload_status` / `cloud_available`
- [ ] 云盘状态合并顺序：`live_sessions` → `agent-manifest.json` → `cloud_uploads`（`done` 的 mp4/flv）；`cloud_available` 在 `done`/`uploaded` 且有 `cloud_file_id` 或 `cloud_relative_path` 时为 true

### API — 历史媒体操作

- [ ] `POST .../history/live/{session_id}/delete-local` — 删本地视频，保留 DB/转写/云记录
- [ ] `POST .../history/live/{session_id}/download-cloud` — 本地缺失且云盘可用时从阿里云盘拉回
- [ ] `DELETE .../history/{live|vod}/{item_id}` — 删历史记录（VOD 可选删媒体文件）
- [ ] VOD 云盘下载 **非目标**（首期仅 live）

### 前端 — HistoryPanel

- [ ] 行标题：直播显示时段，作品显示标题（不展示文件名）
- [ ] 标签：`直播`/`作品`、时长、转写/摘要、**本地**（✓ / 缺失 / —）、**云端**（已备份 / 仅云端 / 待传 / 失败 / —）
- [ ] 直播 **仅失败** 时显示「失败」；不展示 `completed`/`streaming` 等内部字段
- [ ] 行操作：从云下载（live + 仅云端）、删本地、删除记录（确认对话框）
- [ ] VOD 可选中转写/摘要路径回放（`transcript_path` / `summary_path`）

### 测试

- [ ] `pytest tests/unit/test_api_history_media.py tests/unit/test_api_sessions_list.py -v -m desktop`
- [ ] `pnpm --filter m2t-desktop test`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_api_history_media.py tests/unit/test_api_sessions_list.py -v -m desktop
pnpm --filter m2t-desktop test
pnpm --filter m2t-desktop tauri dev
# 手工：选一博主 → 历史 → 确认本地/云端标签；仅云端场次可「从云下载」
```

## 非目标范围

- VOD 从云盘下载/上传
- 历史列表展示 `pipeline_mode` / streaming 技术标签
- 批量删除或多选操作

## 实现备注

- GitHub Issue: [#164](https://github.com/oychao1988/media2text/issues/164)
- 分支：`issue-164-desktop-history-media-ops`
