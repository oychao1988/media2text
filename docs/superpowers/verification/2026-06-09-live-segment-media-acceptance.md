# Live Segment Media Pipeline — Epic 验收

规格：[2026-06-09-live-segment-media-pipeline-design.md](../specs/2026-06-09-live-segment-media-pipeline-design.md)  
计划：[2026-06-09-live-segment-media-pipeline.md](../plans/2026-06-09-live-segment-media-pipeline.md)

> Epic 闸门：#269–#274 全部合并后执行 `python scripts/epic_verify.py live-segment-media`。

| ID | 验收项 | 命令/证据 | 状态 |
|----|--------|-----------|------|
| S1 | 本地磁盘峰值 ≤ 2×segment_size | segment watcher + 段上传删本地；`test_task_scheduler_segment_order.py` | [x] unit |
| S2 | 段闭合 → 上传完成 P95 | `test_segment_process.py`；生产 `live stats` | [x] unit |
| S3 | STT finalize 封存 ≤10s | `test_streaming_stt_resilience.py` / `test_segment_finalize_sidecar.py` | [x] unit |
| S4 | 播放 seek 与转写对齐 | `test_segment_duration_parse.py` + `test_segment_duration_close.py`；Desktop `playbackTime.test.ts`（G2：`duration_sec` → `discontinuity_at` + part 边界映射） | [x] unit (G2) |
| S5 | upload/compress 失败不停录 | `test_segment_process.py` + G3 `test_segment_process_retry.py` | [x] unit |
| S6 | 压缩 PoC 门禁 | `scripts/benchmark_live_compress.py` + [compress benchmark](./2026-06-09-live-compress-benchmark.md) | [ ] 人工 PoC |
| S7 | `live download --merge` 可还原 MP4 | `test_live_download_cli.py` | [x] unit |

## Issue 验收

| Issue | 范围 | 验证 |
|-------|------|------|
| #269 | LSM-0 PoC / compress gate | `issue_verify.py --issue 269` |
| #270 | LSM-1 HLS 录制 | `issue_verify.py --issue 270` |
| #271 | LSM-2 Segment pipeline | `issue_verify.py --issue 271` |
| #272 | LSM-3 Playback API + Desktop | `issue_verify.py --issue 272` |
| #273 | LSM-4 `live download` CLI | `issue_verify.py --issue 273` |
| #274 | LSM-5 post_process + manifest + docs | `issue_verify.py --issue 274` |

### Spec gap follow-up（#281–#284）

| Issue | 范围 | PR | 验证 |
|-------|------|-----|------|
| #281 | G1 HLS 多次重连 DISCONTINUITY | [#285](https://github.com/oychao1988/media2text/pull/285) | `issue_verify.py --issue 281` |
| #282 | G2 `duration_sec` + 播放对齐 | [#289](https://github.com/oychao1988/media2text/pull/289) | `issue_verify.py --issue 282` |
| #283 | G3 segment_process 重试 + CLI | [#292](https://github.com/oychao1988/media2text/pull/292) | `issue_verify.py --issue 283` |
| #284 | G4 云盘 init + manifest | [#294](https://github.com/oychao1988/media2text/pull/294) | `issue_verify.py --issue 284` |

## Epic verify

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/epic_verify.py live-segment-media
```

**结果（2026-06-09）**：`epic_verify: live-segment-media PASS`（本地 dev 环境；S6 未纳入自动化闸门）。

**Gap-fix（2026-06-09）**：#281–#284 全部合并后 `python scripts/epic_verify.py live-segment-media-gap-fix` → **PASS**。

## VERDICT

**PASS**（S6 压缩 PoC  deferred：需在 Apple Silicon + `hevc_videotoolbox` 环境人工跑 `scripts/benchmark_live_compress.py`；不影响 Epic 代码交付与 S1–S5 / S7 自动化验收。）
