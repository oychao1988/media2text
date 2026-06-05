# 抖音图文下载 + signed detail 兜底 & Desktop 作品下载 UX

## 背景

1. **抖音作品下载**：部分博主作品为图文（`aweme_type=68`），catalog 仅有图集 URL、无 MP4；直连 `aweme/detail` 需 a_bogus 签名。此前 `download run` 对图文失败，且无 signed API 兜底。
2. **Desktop 作品流水线**：管理页「同步作品」只更新 catalog，不入队下载；历史列表不展示 `listed` 待下载项；图集 `local_path` 为目录时 `media_available` 误判为缺失；回放页仅支持 MP4/FLV。

**参考**

- 抖音适配：[douyin-design](../superpowers/specs/2026-05-20-media2text-douyin-design.md)
- 桌面规格：[m2t-desktop-design](../superpowers/specs/2026-06-04-m2t-desktop-design.md)
- 历史媒体操作（已交付）：[m2t-desktop-history-media-ops.md](./m2t-desktop-history-media-ops.md)

## 验收标准

### Core — 抖音图文 & signed detail

- [ ] `awemes.media_urls`（JSON）与 `media_type`（`video`|`gallery`）入库；`failed` 条目在 catalog 带回 URL 时可重置为 `listed`
- [ ] 图文下载至 `creators/{sec_uid}/images/{aweme_id}/`（多图 `01.jpeg`…）；视频仍至 `videos/{aweme_id}.mp4`
- [ ] 下载 URL 解析顺序：DB 缓存 → signed `aweme/detail`（a_bogus，`gmssl`）→ yt-dlp（若配置）
- [ ] `pytest tests/unit/test_douyin_gallery.py tests/unit/test_douyin_download_url_cache.py tests/unit/test_catalog_sync.py -v`

### API — Desktop 作品入队 & 历史 enriched

- [ ] `POST /api/creators/{id}/sync?enqueue_download=true` 同步成功后 enqueue `download` 任务
- [ ] `POST /api/creators/{id}/download`（202）单独入队待下载作品
- [ ] `GET /api/creators/{id}/sessions` 含 `sync_status=listed`；VOD 含 `media_type`；图集目录 `media_available=true`
- [ ] `GET /api/media/gallery?path=...` 返回目录内图片相对路径列表
- [ ] Daemon `download` 任务跳过 `gallery` 自动转写（目录非媒体文件）
- [ ] `pytest tests/unit/test_api_creators_sync.py tests/unit/test_api_sessions_list.py tests/unit/test_api_media.py -m desktop -v`

### Desktop UI

- [ ] 管理页运维：**同步并下载**、**下载作品**（toast 提示需开启监控）
- [ ] 历史：待下载作品显示「待下载」标签；图文类型显示「图文」
- [ ] 回放：图集大图 + 上一张/下一张 + 缩略图；`listed` 显示待下载引导文案
- [ ] `pnpm --filter m2t-desktop test`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[desktop,dev]"
pytest tests/unit/test_douyin_gallery.py tests/unit/test_douyin_download_url_cache.py \
  tests/unit/test_api_creators_sync.py tests/unit/test_api_sessions_list.py \
  tests/unit/test_api_media.py -m desktop -v
pnpm --filter m2t-desktop test

# CLI 冒烟（需网络 + 抖音登录）
media2text creator sync <creator_id> --json
media2text download run --creator <creator_id> --limit 3 --json

# Desktop 手工
media2text serve --port 8765
pnpm --filter m2t-desktop tauri dev
# 管理 → 同步并下载 → Daemon 队列出现「下载作品」
# 历史 → 待下载 / 已下载图文可浏览
```

## 非目标范围

- 图集 OCR / 正文提取或转写 pipeline
- VOD 从阿里云盘下载（仍仅 live）
- 修复 Playwright catalog sync 启动失败（`playwright_chromium_launch_failed`）— 另开单
- 历史列表批量下载或多选操作
- 将 `pipeline/run` 完整一条龙接入 Desktop UI（本期仅 sync+download 入队）

## 实现备注

- 签名实现参考 jiji262 `douyin-downloader` 的 a_bogus 路径；依赖 `gmssl>=3.2`
- GitHub Issue: [#168](https://github.com/oychao1988/media2text/issues/168)
- 分支：`issue-168-douyin-gallery-desktop-vod`
