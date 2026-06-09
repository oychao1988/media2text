---
issue: 273
epic: live-segment-media
github: 273
branch: issue-273-live-segment-lsm4
depends_on: [271]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Media LSM-4：CLI `live download`

## 背景

段级上传（#271）后，用户需从云或本地拉取 HLS parts，可选合并为单 MP4（**S7**）。新增 `media2text live download <session_id>`，输出 `--json` 供 Agent 解析。

**参考**

- [design spec §8、S7](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- [plan LSM-4](../superpowers/plans/2026-06-09-live-segment-media-pipeline.md)

## 验收标准

### Task 4.1 — `live download` 子命令

- [x] `media2text live download <session_id> --parts all|1,2,3 --json`：从云（或本地若存在）拉取指定 parts
- [x] 默认输出目录行为 documented；`--keep-local` / 目标路径 flags 与 spec 一致
- [x] `--merge`：ffmpeg concat demuxer → 单可播 MP4；失败时保留分段并 JSON 报告 `merge_error`
- [x] `tests/unit/test_live_download_cli.py` 通过（mock 云客户端）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_live_download_cli.py -v
media2text live download --help
ruff check src/media2text/cli/
```

## 非目标范围

- Desktop 内嵌下载 UI
- 自动后台同步全量历史 sessions
- 修改 aliyundrive 鉴权
- 抖音/B 站重新拉流（仅已有 cloud_uploads / 本地 parts）

## 依赖与顺序

- **依赖**：#271（`cloud_uploads.part_index`、云路径）
- **建议分支**：`issue-273-live-segment-lsm4`

## GitHub

- Issue: [#273](https://github.com/oychao1988/media2text/issues/273)
