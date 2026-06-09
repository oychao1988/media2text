---
issue: 274
epic: live-segment-media
github: 274
branch: issue-274-live-segment-lsm5
depends_on: [271]
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Media LSM-5：post_process 瘦身 + manifest + Epic 验收

## 背景

#271 已调整 finalize / segment 路径后，本单清理 **HLS session** 在 `post_process.py` 中的 legacy 整文件 remux/upload 分支，刷新 `agent-manifest.json`（`playback_mode: hls`、`parts[]`），更新用户文档，并新建 Epic 验收表勾 **S1–S7**。

**须在 #271 合并后** 开分支（同文件 `post_process.py`）。

**参考**

- [design spec §11、Success Criteria](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)
- [plan LSM-5](../superpowers/plans/2026-06-09-live-segment-media-pipeline.md)

## 验收标准

### Task 5.1 — post_process 瘦身

- [x] `run_post_process_job`：HLS session 不再走整文件 MP4 remux / live 整文件 upload
- [x] FLV legacy session 行为不变；现有 post_process 单测更新并通过

### Task 5.2 — agent-manifest

- [x] `agent-manifest.json` 刷新逻辑含 `playback_mode`（`hls`|`flv`）、`parts[]` 摘要（index、state、cloud_path 可选）
- [x] Desktop / Agent 读 manifest 可区分 HLS 会话

### Task 5.3 — 文档与 Epic 验收

- [x] `CLAUDE.md`、`README.md` live 段落：HLS 分段、Tier 隔离、`live download`、配置摘录
- [x] 新建 `docs/superpowers/verification/2026-06-09-live-segment-media-acceptance.md`：S1–S7 勾选表 + 验证命令指针
- [x] `docs/issues/epic-manifests/live-segment-media.yaml` 与本 README 系列表 issue 号对齐

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_post_process*.py tests/unit/test_agent_manifest*.py -v
python scripts/epic_verify.py live-segment-media
ruff check src/media2text/core/live/post_process.py
```

## 非目标范围

- 重新实现 #271 的 segment pool / scheduler
- 修改 #272 Playback UI
- 变更 `config.example.yaml` 默认 `media.format`（除非 #269 PoC + 产品确认一并改）
- 历史 FLV 会话迁移为 HLS

## 依赖与顺序

- **依赖**：#271（必须已合并）
- **Epic 验收闸门**：本单 + #269–#273 全部合并后跑 `epic_verify.py live-segment-media`
- **建议分支**：`issue-274-live-segment-lsm5`

## GitHub

- Issue: [#274](https://github.com/oychao1988/media2text/issues/274)
