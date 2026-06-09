# Live Segment Media — 压缩 PoC 验收（LSM-0 / S6）

**日期:** 2026-06-09  
**Issue:** [#269](https://github.com/oychao1988/media2text/issues/269)  
**脚本:** `scripts/benchmark_live_compress.py`  
**规格:** [live-segment-media-pipeline-design §7](../specs/2026-06-09-live-segment-media-pipeline-design.md)

## S6 门槛

| 指标 | 目标 | 字段 |
|------|------|------|
| 压缩后体积 | ≤ 原片 **40%** | `size_ratio <= 0.40` |
| VideoToolbox 编码速度 | ≥ **1.0×** realtime | `encode_realtime_factor >= 1.0` |

编码参数（macOS PoC）：

```bash
-c:v hevc_videotoolbox -b:v 2M -c:a aac -b:a 128k
-f hls -hls_time 600 -hls_playlist_type event
```

## 验收结果

| 样本 | 原片 (B) | 输出 (B) | size_ratio | VT realtime | cpu_pct | S6 体积 | S6 速度 | 结论 |
|------|----------|----------|------------|-------------|---------|---------|---------|------|
| `20260609T021033Z.flv` (720×1280 H264, ~248s, 66 MiB) | 69 110 784 | — | — | — | — | ✗ | ✗ | **编码失败** |

**运行环境:** macOS，Intel Core i7-8750H；`ffmpeg` 含 `hevc_videotoolbox`，但编码报 `Error encoding frame: -12905` / `Generic error in an external library`（该机型常见 HEVC VT 硬件编码不可用）。

**状态:** **S6 未通过** — 需在 **Apple Silicon 或确认支持 HEVC VT 编码的 Mac** 上重跑脚本并更新本表。

### 补跑命令

```bash
source .venv/bin/activate
pip install -e ".[dev]"

python scripts/benchmark_live_compress.py \
  --sample data/creators/<sec_uid>/live/<timestamp>.flv \
  --json
```

成功时 stdout JSON 含 `size_ratio`、`encode_realtime_factor`、`cpu_pct`、`sample_path`；`s6_pass: true` 表示双门槛通过。

## 门禁决策

- [ ] S6 体积（≤40%）— **未测**（编码失败）
- [ ] S6 速度（VT ≥1.0× realtime）— **未测**（编码失败）

**当前决策:** **保持** `live.compress.enabled: false`（见 `config.example.yaml`）。在 Apple Silicon / 兼容硬件上补跑并通过 S6 前，不得将 example 或产品默认改为 `enabled: true`。

## 自动化（脚本 smoke）

```bash
source .venv/bin/activate
pip install -e ".[dev]"
ruff check scripts/benchmark_live_compress.py   # exit 0
python scripts/benchmark_live_compress.py --help   # exit 0
python scripts/benchmark_live_compress.py            # exit 2, prints help
test -f docs/superpowers/verification/2026-06-09-live-compress-benchmark.md
```
