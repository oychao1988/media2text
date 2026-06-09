# Live Segment Media Pipeline — Epic 验收

规格：[2026-06-09-live-segment-media-pipeline-design.md](../specs/2026-06-09-live-segment-media-pipeline-design.md)  
计划：[2026-06-09-live-segment-media-pipeline.md](../plans/2026-06-09-live-segment-media-pipeline.md)

> Epic 闸门：#269–#274 全部合并后执行 `python scripts/epic_verify.py live-segment-media`。

| ID | 验收项 | 命令/证据 | 状态 |
|----|--------|-----------|------|
| S1 | 本地磁盘峰值 ≤ 2×segment_size | segment watcher + 段上传删本地；`test_task_scheduler_segment_order.py` | [x] unit |
| S2 | 段闭合 → 上传完成 P95 | `test_segment_process.py`；生产 `live stats` | [x] unit |
| S3 | STT finalize 封存 ≤10s | `test_streaming_stt_resilience.py` / `test_segment_finalize_sidecar.py` | [x] unit |
| S4 | 播放 seek 与转写对齐 | `test_playback_api.py`；Desktop `playbackTime.test.ts` | [x] unit |
| S5 | upload/compress 失败不停录 | `test_segment_process.py` 失败重试 | [x] unit |
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

## Epic verify

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/epic_verify.py live-segment-media
```
