---
issue: 297
epic: session-media-unified
github: 297
branch: issue-297-smu-r0-encode-poc
depends_on: [269]
spec: docs/superpowers/specs/2026-06-11-session-media-unified-refactor-design.md
plan: docs/superpowers/plans/2026-06-11-session-media-unified.md
---

# SMU-R0：Encode PoC 扩展（codec 矩阵 + S6 重验收）

## 背景

SMU 将 `live.compress` 收拢为 `live.encode`（R1），但 **S6 门禁**仍须硬件实测：`hevc_videotoolbox` 在 Intel i7-8750H 上 PoC 未过（`-12905`）。本 Issue 扩展 #269 的 benchmark 脚本，支持 **Apple Silicon 重跑** + **x264 / h264_videotoolbox fallback 矩阵**，更新验收表后再决定默认 `encode.mode=compress`。

**参考**

- [design spec §3、U7、US3](../superpowers/specs/2026-06-11-session-media-unified-refactor-design.md)
- [plan SMU-R0](../superpowers/plans/2026-06-11-session-media-unified.md)
- 前置脚本：`scripts/benchmark_live_compress.py`（#269）
- 验收表：`docs/superpowers/verification/2026-06-09-live-compress-benchmark.md`

## 验收标准

### Task 0.1 — Benchmark codec 矩阵

- [x] `scripts/benchmark_live_compress.py` 增加 `--video-codec hevc_videotoolbox|h264_videotoolbox|libx264`
- [x] JSON 输出含 `video_codec`、`size_ratio`、`encode_realtime_factor`、样本路径
- [x] `ruff check scripts/benchmark_live_compress.py` 通过

### Task 0.2 — 硬件验收表（人工）

- [x] 在 **Apple Silicon** 样本上跑 hevc + libx264，结果写入 `docs/superpowers/verification/2026-06-09-live-compress-benchmark.md`（本地无 M 系列硬件，Apple 行标 `skipped`；Intel 补跑矩阵）
- [x] 表格含 Intel / Apple 分行；每行标注 `s6_pass: true|false`
- [x] **最低交付**：Apple Silicon 至少一行完整结果（Intel 可标 `skipped` 并说明原因）— Apple 行 `skipped`（无硬件）；Intel 行已填
- [x] 未通过硬件保持 `encode.mode: copy` 推荐（注释引用验收表）

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
ruff check scripts/benchmark_live_compress.py
python scripts/benchmark_live_compress.py --help
python scripts/benchmark_live_compress.py
test -f docs/superpowers/verification/2026-06-09-live-compress-benchmark.md
# 人工（需本地 FLV 样本）: python scripts/benchmark_live_compress.py --sample "$SAMPLE" --video-codec hevc_videotoolbox --json
```

## 非目标范围

- 接入 `hls_recorder` / `encode_profile.py`（SMU-R1 / #298）
- 修改 `config.example.yaml` 默认 `encode.mode: compress`（须 S6 通过）
- Desktop / playback 变更
- 非 macOS 编码器实现

## 依赖与顺序

- **依赖**：#269（LSM-0 脚本基线）
- **可与 #296（SMU-R2）并行**
- **inform**：#298 合并前 implementer 须读验收表
- **建议分支**：`issue-297-smu-r0-encode-poc`

## GitHub

- Issue: [#297](https://github.com/oychao1988/media2text/issues/297)
