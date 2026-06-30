# 阿里云盘滚动清理：仅删视频 + 回收站永久释放

GitHub: [#364](https://github.com/oychao1988/media2text/issues/364)  
依赖: [#67](https://github.com/oychao1988/media2text/issues/67) 直播云备份（已交付）  
分支: `issue-364-aliyundrive-rolling-cleanup-video-purge`  
PR: （待开）

## 背景

`rolling_cleanup` 在空间不足时为本工具上传腾出云盘配额。当前实现有两处缺口：

1. **streaming 默认**（`transcribe_on_complete: false`）下 `list_cleanup_candidates(require_transcripts=False)` 返回**所有** `cloud_uploads` 已完成记录，可能误删 `transcript_json`、`summary_*`、`manifest_json`、`m3u8` 等文本 sidecar。
2. 清理仅调用 `client.trash()`，文件进入回收站后 **`used` 配额不下降**；回收站积压时滚动清理无法真正腾空间。

**产品决策**

| # | 决策 |
|---|------|
| D1 | 滚动清理**仅删除视频类** `file_kind`：`mp4`、`flv`、`m4s`、`init_mp4` |
| D2 | **禁止**滚动清理删除：`transcript_*`、`summary_*`、`manifest_json`、`m3u8` |
| D3 | `require_transcripts` 门禁保留：legacy 路径须 session 转写已备份后才可删该 session 的视频 |
| D4 | 对候选视频执行**永久删除**（`/v3/file/delete`，aligo 扩展 API），而非仅 `trash` |
| D5 | DB 候选删完后若仍 `free < needed_bytes`，且 `purge_recycle_bin: true`（默认开），从回收站按时间删最旧**视频扩展名**文件，直至达标或 `max_delete_per_round` |
| D6 | 回收站清理**同样仅视频扩展名**；飞书 `upload_cleanup` 通知区分 `db` / `recycle_bin` 来源 |

## 验收标准

### 候选过滤
- [x] `list_cleanup_candidates` 在 `require_transcripts=false` 时亦只返回视频类 `file_kind`
- [x] `require_transcripts=true` 行为不变：仅 `mp4`/`flv` 且转写已备份的 session
- [x] 单元测试：`m4s` + `transcript_json` 同 session，`require_transcripts=false` 时候选仅含 `m4s`

### 永久删除
- [x] `AliyunDriveClient.delete_file_permanently(file_id)` 封装 `/v3/file/delete`
- [x] `rolling_cleanup` 对 DB 候选调用永久删除，不再仅 `trash`
- [x] 单元测试：mock 验证 `delete_file_permanently` 被调用

### 回收站释放
- [x] `AliyunDriveClient.list_recycle_bin()` 分页列出回收站
- [x] `rolling_cleanup` 在 DB 候选不足时扫描回收站，仅删 `.mp4`/`.flv`/`.m4s`/`init.mp4`
- [x] `aliyundrive.rolling_cleanup.purge_recycle_bin` 配置项（默认 `true`）
- [x] 单元测试：mock 回收站含 `.mp4` 与 `.json`，仅 `.mp4` 被永久删除

### 配置与文档
- [x] `config.example.yaml` 增加 `rolling_cleanup.purge_recycle_bin`
- [x] `AliyunDriveRollingCleanupConfig` 增加字段

## 验证命令

```bash
source .venv/bin/activate
ruff check src/media2text/core/cloud/ src/media2text/core/storage/repos.py tests/unit/test_aliyundrive_live_upload.py tests/unit/test_aliyundrive_client.py
pytest tests/unit/test_aliyundrive_live_upload.py tests/unit/test_aliyundrive_client.py -v -q
```

## 非目标

- 不修改上传覆盖策略（`check_name_mode` / `trash` 后重传仍用于同名覆盖）
- 不实现 `clear_recyclebin` 清空整个回收站（仅按扩展名删最旧视频）
- 不清理非 `media2text/` 根目录下、且无 DB 记录的手动上传文件（回收站阶段仅按视频扩展名过滤，无法可靠还原路径时不强依赖 `root_folder` 前缀）
- 不改 HLS 分段上传主路径逻辑
