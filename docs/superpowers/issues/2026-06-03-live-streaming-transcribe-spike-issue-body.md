## 背景

Live Pipeline v2 Spec §3 将「录播中实时转写」列为**非目标**；v3 增量规格已批准，把 **Deepgram WebSocket 流式 STT** 作为 `live.pipeline_mode: streaming` 主路径，接入 `monitor watch --daemon`。

**已完成（Spike / 规格，2026-06-03）**

- PoC：[scripts/test_douyin_live_deepgram_stream.py](../../../scripts/test_douyin_live_deepgram_stream.py) 已跑通（抖音 FLV → ffmpeg PCM → Deepgram WS → `[final]` 中文）
- 设计 spec（ENG CLEARED）：[docs/superpowers/specs/2026-06-03-live-streaming-stt-design.md](../specs/2026-06-03-live-streaming-stt-design.md)
- `/plan-eng-review` 决策 D1–D5 已锁定（见 spec §0、§Eng review）

**本工单范围：** v3 **P0 实现**（~9 文件），在 `monitor watch` 内启用 streaming 模式；代码默认仍为 `legacy`，`config.example.yaml` 推荐 `streaming`。

**工程决策（已锁定）**

| ID | 选择 |
|----|------|
| D1 | P0 单段 streaming；ffmpeg 重连 → **legacy finalize** 或 degraded（不做 offset merge） |
| D2 | record + STT **均成功**才 `live_started`；否则 `live_start_failed` |
| D3 | 代码缺省 **`legacy`**；example **`streaming`** |
| D4 | DB 列名保留 **`post_process_jobs.mp4_path`**（值可为 `.flv`） |
| D5 | post_process：**summarize ∥ upload 并行**（summary 晚完成则补传 sidecar） |

**参考**

- v2 基线：[live-pipeline-v2-design](../specs/2026-06-03-live-pipeline-v2-design.md)
- Agent 指南：[CLAUDE.md](../../../CLAUDE.md)

---

## Spike 阶段（已完成）

- [x] 规格 `docs/superpowers/specs/2026-06-03-live-streaming-stt-design.md`（用户场景、与 batch 关系、断流/费用、monitor 集成路径）
- [x] PoC 验证 + 集成点列表（见 spec §4.3、§10）
- [x] 默认策略：代码 `legacy`；新装 example 推荐 `streaming`（非「永远不开」）

---

## 验收标准（P0 实现）

### 核心模块

- [ ] 新增 `src/media2text/core/live/streaming_stt.py`：`StreamingSttSession`（PCM ffmpeg + Deepgram `listen.v1` WS 线程）
- [ ] 新增 `src/media2text/core/live/transcript_writer.py`：partial/final 落盘，格式与 `write_transcript_outputs` 兼容
- [ ] 新增 `src/media2text/core/platform/douyin/live_enter.py`：从 PoC 提升 `resolve_stream_via_web_enter()`；**仅在** `_start_recording` / 重连 resolve 调用，poll 不打开 Playwright

### LiveRecordingCore（streaming 分支）

- [ ] `live.pipeline_mode: streaming` 时：`start_recording` 启动 `{ record_proc, stt_session }` 两路
- [ ] `_finalize_recording`：**不 remux**；`local_path=*.flv`；封存 `.transcript.json/.md`；写入 `live_pipeline_events` stage `streaming_stt`
- [ ] **D1**：出现 ffmpeg 重连（`_r1.flv`）时降级 legacy finalize 或标记 degraded（单测覆盖分支）
- [ ] **D2**：任一路启动失败 → `live_start_failed`，不发送 `live_started`
- [ ] `pipeline_mode=legacy` 行为与现网 **bit-identical**（回归现有 live tests）

### post_process + upload

- [ ] streaming 下 **skip** `post_process` transcribe（transcript 已在 finalize 封存）
- [ ] **D5**：transcribe 完成或跳过后，`summarize` 与 `cloud_upload` **并行** fan-out；upload 不等待 summarize 才开始
- [ ] 若 upload 先完成且 `upload_transcripts: true`，summarize 完成后 **补传** `.summary.*`
- [ ] `live_upload.py` 支持 FLV 主文件 + transcript/summary sidecar（列名仍 `mp4_path`）

### 配置与 DX

- [ ] `config.example.yaml`：`live.pipeline_mode: streaming` + `streaming_stt` 块（见 spec §7）
- [ ] 代码缺省 `pipeline_mode=legacy`
- [ ] `media2text doctor --json`：streaming 模式未配 Deepgram key 时给出提示

### 测试

- [ ] `tests/unit/test_transcript_writer.py`：flush / finalize 封存
- [ ] `tests/unit/test_streaming_finalize.py`（或等价）：streaming finalize **不调用** remux
- [ ] `tests/unit/test_post_process_summarize_upload_parallel.py`：upload 不阻塞于 summarize（mock 慢 summarize）
- [ ] `tests/unit/test_douyin_live_enter.py`：enter payload fixture 解析
- [ ] mock Deepgram WS + fake PCM（可选 integration）
- [ ] `pytest tests/ -v`、`ruff check src tests`、`pyright` 通过

### 文档（P0 最小）

- [ ] 更新 `CLAUDE.md` / `README.md`：`pipeline_mode`、streaming 路径、Deepgram 流式计费提示、`legacy` 回退

---

## 验证命令

```bash
source .venv/bin/activate
pip install -e ".[dev,transcribe-deepgram]"

ruff check src tests
pyright
pytest tests/unit/test_transcript_writer.py \
  tests/unit/test_post_process_summarize_upload_parallel.py -v
pytest tests/ -v

media2text doctor --json

# PoC 回归（需抖音登录 + DEEPGRAM_API_KEY + 真实直播 URL）
export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Caches/ms-playwright"
python scripts/test_douyin_live_deepgram_stream.py '<live_url>' -t 60

# P0 合并后手动（config: pipeline_mode: streaming）
# monitor watch 一轮或 daemon；下播后检查：
#   data/creators/<sec_uid>/live/<stamp>.flv
#   data/creators/<sec_uid>/live/<stamp>.transcript.json
#   media2text live timeline <session_id> --json  # 含 streaming_stt stage
```

---

## 非目标范围（P0）

- B 站 streaming STT（**P1**）
- 断流 transcript **offset merge**（**P1**；P0 仅降级 legacy）
- 直播中 partial 字幕飞书通知（**P2**）
- 单 ffmpeg tee 分流（defer）
- 去掉 `legacy` 模式
- VOD / 作品 transcribe 路径改动
- DB 列 `mp4_path` → `media_path` 迁移（**P1**）
- 独立实验子命令（streaming 走现有 `monitor watch` + config）

---

## 待确认问题

无（D1–D5 已于 2026-06-03 确认）。

---

## 实现备注

- GitHub Issue: [#97](https://github.com/oychao1988/media2text/issues/97)
- 分支建议：`issue-97-live-streaming-stt-p0`
- P1 跟进：offset merge、B 站、DB rename（可另开 issue 或在本 issue 评论拆分）
