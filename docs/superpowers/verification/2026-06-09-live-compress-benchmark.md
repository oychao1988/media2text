# Live Segment Media — 压缩 PoC 验收（LSM-0 / S6）

**日期:** 2026-06-09（Apple Silicon 补跑：2026-06-12，#297）  
**Issue:** [#269](https://github.com/oychao1988/media2text/issues/269)（基线）、[#297](https://github.com/oychao1988/media2text/issues/297)（codec 矩阵）  
**脚本:** `scripts/benchmark_live_compress.py`  
**规格:** [live-segment-media-pipeline-design §7](../specs/2026-06-09-live-segment-media-pipeline-design.md)

## S6 门槛

| 指标 | 目标 | 字段 |
|------|------|------|
| 压缩后体积 | ≤ 原片 **40%** | `size_ratio <= 0.40` |
| VideoToolbox 编码速度 | ≥ **1.0×** realtime | `encode_realtime_factor >= 1.0` |

编码参数（macOS PoC）：

```bash
-c:v <hevc_videotoolbox|h264_videotoolbox|libx264> -b:v 2M -c:a aac -b:a 128k
-f hls -hls_time 600 -hls_playlist_type event
```

CLI：`--video-codec hevc_videotoolbox|h264_videotoolbox|libx264`

## 验收结果

**样本:** `20260609T021033Z.flv`（720×1280 H264，~248s，~66 MiB）  
路径：`data/creators/MS4wLjABAAAAKgJe9JWPt3EiqVCyL81ysj3nT29G11FyTore_eETSDoaAvK5JPG_u8pBcuiS0PoL/live/20260609T021033Z.flv`

### Apple Silicon（M 系列）

| video_codec | 原片 (B) | 输出 (B) | size_ratio | encode_realtime_factor | cpu_pct | s6_pass | 备注 |
|-------------|----------|----------|------------|------------------------|---------|---------|------|
| `hevc_videotoolbox` | — | — | — | — | — | **skipped** | 本地无 Apple Silicon 硬件；须在 M 系列 Mac 上补跑 |
| `libx264` | — | — | — | — | — | **skipped** | 同上 |

### Intel（Core i7-8750H，x86_64 macOS）

| video_codec | 原片 (B) | 输出 (B) | size_ratio | encode_realtime_factor | cpu_pct | s6_pass | 备注 |
|-------------|----------|----------|------------|------------------------|---------|---------|------|
| `hevc_videotoolbox` | 69 004 045 | — | — | — | — | **false** | 编码失败：`Error encoding frame: -12905`（HEVC VT 硬件编码不可用） |
| `h264_videotoolbox` | 69 004 045 | 68 828 264 | 0.9975 | 10.94 | 240.9 | **false** | 速度通过；体积未压缩（≈100%，S6 体积门槛失败） |
| `libx264` | 69 004 045 | 68 474 824 | 0.9923 | 8.061 | 698.3 | **false** | 速度通过；体积未压缩（≈100%，S6 体积门槛失败） |

**运行环境（Intel 行）:** macOS x86_64，Intel Core i7-8750H；`ffmpeg` 含 `hevc_videotoolbox` / `h264_videotoolbox`。

**状态:** **S6 未通过** — Apple Silicon 上 `hevc_videotoolbox` 仍待实测；Intel 上 HEVC VT 不可用，H.264 VT / x264 仅验证脚本与速度门槛，**不得**作为 `encode.mode=compress` 默认依据。

### 补跑命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"

SAMPLE=data/creators/<sec_uid>/live/<timestamp>.flv

python scripts/benchmark_live_compress.py \
  --sample "$SAMPLE" \
  --video-codec hevc_videotoolbox --json

python scripts/benchmark_live_compress.py \
  --sample "$SAMPLE" \
  --video-codec h264_videotoolbox --json

python scripts/benchmark_live_compress.py \
  --sample "$SAMPLE" \
  --video-codec libx264 --json
```

成功时 stdout JSON 含 `video_codec`、`size_ratio`、`encode_realtime_factor`、`sample_path`；`s6_pass: true` 表示双门槛通过。

## 门禁决策

- [ ] S6 体积（≤40%）— **未通过**（Intel HEVC 失败；H.264 VT / x264 体积≈原片）
- [ ] S6 速度（VT ≥1.0× realtime）— **Intel 部分通过**（H.264 VT / x264）；Apple Silicon **未测**

**当前决策:** **保持** `live.compress.enabled: false`（见 `config.example.yaml`）。在 Apple Silicon 上补跑 `hevc_videotoolbox` 并通过 S6 前，不得将 example 或产品默认改为 `enabled: true` / `encode.mode: compress`。

## 自动化（脚本 smoke）

```bash
source .venv/bin/activate
pip install -e ".[dev]"
ruff check scripts/benchmark_live_compress.py   # exit 0
python scripts/benchmark_live_compress.py --help   # exit 0
python scripts/benchmark_live_compress.py            # exit 0, prints help
test -f docs/superpowers/verification/2026-06-09-live-compress-benchmark.md
```
