# 直播收尾：poll 先于 mark_stale

GitHub: [#78](https://github.com/oychao1988/media2text/issues/78)（已关闭）  
规格正文: [docs/superpowers/issues/2026-06-02-live-stale-before-poll-issue-body.md](../superpowers/issues/2026-06-02-live-stale-before-poll-issue-body.md)  
关联: [#73 直播录制管道](./live-recording-pipeline.md)

**状态**：本地已实现；守护进程已于 2026-06-02 重启（PID 93041）加载新逻辑。

## 摘要

`mark_stale_recordings_failed()` 在 `poll_active_recordings()` 之前执行，导致 ffmpeg 正常退出时被误判 `stale_recording`，无法自动 remux 与异步入队。
