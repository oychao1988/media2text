---
issue: 269
epic: live-segment-media
github: 269
branch: issue-269-live-segment-lsm0
depends_on: []
spec: docs/superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md
plan: docs/superpowers/plans/2026-06-09-live-segment-media-pipeline.md
---

# Live Segment Media LSM-0：压缩 PoC（Phase 0 门禁）

## 背景

直播 HLS 分段流水线（Epic `live-segment-media`）默认在录制时即 HEVC 压缩（`live.compress.enabled`），但 **S6** 要求先通过 PoC 证明 macOS `hevc_videotoolbox` 在目标参数下可达体积 ≤40% 原片、编码 ≥1.0× realtime。未通过前 **不得** 在 `config.example.yaml` 默认开启压缩。

本 Issue 对应实现计划 **LSM-0**；无代码路径依赖，可与 LSM-1 准备并行，但 **LSM-1 合并前** PoC 表须填完以决定默认开关。

**参考**

- [live-segment-media-pipeline-design §7](../superpowers/specs/2026-06-09-live-segment-media-pipeline-design.md)（S6、D2）
- [implementation plan LSM-0](../superpowers/plans/2026-06-09-live-segment-media-pipeline.md)

## 验收标准

### Task 0.1 — Benchmark 脚本

- [x] 新增 `scripts/benchmark_live_compress.py`：接受本地 FLV/TS 或短录样本路径，跑 HLS 目标参数（spec §7：`hevc_videotoolbox`、segment 时长等），输出 JSON：`size_ratio`、`encode_realtime_factor`、`cpu_pct`、样本路径
- [x] 脚本在无样本时以 `--help` 说明用法；`--json` 便于 CI/人工归档

### Task 0.2 — 验收文档

- [x] 新增 `docs/superpowers/verification/2026-06-09-live-compress-benchmark.md`：记录 ≥1 段真实/代表性样本结果，勾选 S6 门槛（体积 ≤40%、VT ≥1.0× realtime）
- [x] 若未通过：文档明确 **保持** `live.compress.enabled: false` 直至参数调优或硬件升级

### Task 0.3 — 配置注释

- [x] `config.example.yaml` 在 `live.compress` 段注释 PoC 门禁（引用验收文档路径）；**不**默认 `enabled: true`

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"
# 有样本时（路径按本机 data 调整）
python scripts/benchmark_live_compress.py --sample data/creators/<sec_uid>/live/<file>.flv --json
test -f docs/superpowers/verification/2026-06-09-live-compress-benchmark.md
ruff check scripts/benchmark_live_compress.py
```

## 非目标范围

- 接入 `hls_recorder` 或 daemon 内自动跑 PoC
- 非 macOS 平台编码器 fallback 实现
- 修改 `live.media.format` 默认值为 `hls`（属 LSM-1）
- 云上传、SegmentWatcher、Desktop 播放

## 依赖与顺序

- **依赖**：无
- **阻塞**：LSM-1 产品默认压缩开关决策（implementer 合并 LSM-1 前须读验收表）
- **建议分支**：`issue-269-live-segment-lsm0`

## GitHub

- Issue: [#269](https://github.com/oychao1988/media2text/issues/269)
