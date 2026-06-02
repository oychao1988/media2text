## 背景

`LiveWatcher.run_once()` 在每轮开头调用 `mark_stale_recordings_failed()`，**早于** `poll_active_recordings()`。

当某路直播下播、ffmpeg 因断流正常退出时：

1. `mark_stale` 发现 PID 不存在 → 立刻标 `failed` / `stale_recording`
2. 随后 `poll_active` 已看不到 `recording` 状态 → 无法走 `_handle_ffmpeg_exit` → remux → `post_process_jobs` 入队

**生产现象**（2026-06-02）：万狮虎、老曹浪迹大A、满江宏& 等场次 `.flv` 仍在磁盘（~1GB），但 session 为 `stale_recording`，需人工 remux。

多路同时录制时：**每路独立中招**，不是 ffmpeg 互相干扰，而是同一轮 poll 顺序 bug。

**关联**：[#73](https://github.com/oychao1988/media2text/issues/73) 直播管道（offline streak / 异步入队）已合并逻辑，但 stale 顺序未按 D1 意图落地。

## 验收标准

- [x] `douyin` / `bilibili` `LiveWatcher.run_once`：`poll_active_recordings` → `scan_and_start` →（可选）对本 tick 新开的 session 再 poll（`skip_session_ids`）→ **`mark_stale_recordings_failed`**
- [x] `get_active_for_creator`：ffmpeg PID 已死时**不**抢先标 `stale_recording`，留给 poll finalize
- [x] `run_daemon` 启动时**不再**单独先跑 `mark_stale`（避免与 `run_once` 重复且顺序错误）
- [x] 单测：ffmpeg 已退出 + 有效 `.flv` + API offline → `run_once` 后 session 为 `completed`（或 `remuxing`→`completed`），**非** `stale_recording`
- [x] 既有 `reconnect_attempts > 0` 跳过 stale 行为不变（`repos.mark_stale_recordings_failed` 未改跳过逻辑）
- [x] `pytest tests/unit/test_live_watcher.py tests/unit/test_bilibili_live.py -q` 通过（20 passed，含 `test_live_recording_core`）

## 非目标

- 不改 remux / post_process 逻辑
