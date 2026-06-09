import json

from media2text.core.runtime.log_format import (
    format_daemon_log_line,
    parse_daemon_log_entry,
)


def test_formats_structlog_json_with_timestamp() -> None:
    line = json.dumps(
        {
            "event": "monitor_watch_daemon_started",
            "live_poll": 20,
            "vod_poll": 300,
            "post_process_poll": 10,
            "timestamp": "2026-06-05T10:42:01.123456+00:00",
            "level": "info",
        }
    )
    out = format_daemon_log_line(line)
    assert out.startswith("[")
    assert "启动" in out
    assert "监控守护" in out
    assert "全局" in out
    assert "20s" in out


def test_formats_live_status_check_failed_with_creator_name() -> None:
    line = json.dumps(
        {
            "creator_id": "abc-creator-id",
            "error": "live status failed: bilibili api code -799",
            "event": "live_status_check_failed",
            "timestamp": "2026-06-05T10:42:11Z",
            "level": "warning",
        }
    )
    names = {"abc-creator-id": "老班长说市"}
    out = format_daemon_log_line(line, creator_names=names)
    assert "老班长说市" in out
    assert "开播检测" in out
    assert "失败" in out
    assert "B站接口限流" in out


def test_formats_notify_delivered() -> None:
    line = json.dumps(
        {
            "event": "notify_delivered",
            "kind": "upload_completed",
            "title": "满江宏&",
            "timestamp": "2026-06-09T12:23:44.801608Z",
            "level": "info",
        }
    )
    out = format_daemon_log_line(line)
    assert "通知推送" in out
    assert "满江宏&" in out
    assert "云备份完成" in out


def test_formats_live_tick_with_recordings() -> None:
    line = json.dumps(
        {
            "event": "live_tick",
            "active_recordings": 2,
            "live_poll_sec": 20,
            "timestamp": "2026-06-09T12:24:31Z",
            "level": "info",
        }
    )
    out = format_daemon_log_line(line)
    assert "直播检测" in out
    assert "2 场录制中" in out
    assert "进行中" in out


def test_formats_monitor_download_transcribe_failed() -> None:
    line = json.dumps(
        {
            "event": "monitor_download_transcribe_failed",
            "aweme_id": "7388817240428268840",
            "error": "Deepgram returned empty transcript",
            "timestamp": "2026-06-09T12:18:42Z",
            "level": "warning",
        }
    )
    out = format_daemon_log_line(line)
    assert "作品转写" in out
    assert "作品 #" in out
    assert "Deepgram 返回空转写" in out


def test_formats_cli_json_failure() -> None:
    line = json.dumps({"ok": False, "command": "monitor watch", "error": "already_running"})
    out = format_daemon_log_line(line)
    assert out == "失败 · 启动监控 · 守护进程 · 监控进程已在运行"


def test_parse_structured_entry_dict() -> None:
    line = json.dumps(
        {
            "event": "live_recording_completed_streaming_hls",
            "session_id": "c2402424-e34c-4d81-8d6a-c3f45c639dc6",
            "timestamp": "2026-06-09T12:23:43Z",
            "level": "info",
        }
    )
    entry = parse_daemon_log_entry(line)
    assert entry is not None
    d = entry.to_dict()
    assert d["status"] == "完成"
    assert d["task"] == "直播录制"
    assert "会话 c2402424" in d["target"]
    assert d["detail"] == "HLS 流式收尾"


def test_passes_through_prefixed_structured_line() -> None:
    line = "[10:42:21] 完成 · 录后处理 · 任务 #1284 · 摘要已生成"
    entry = parse_daemon_log_entry(line)
    assert entry is not None
    assert entry.status == "完成"
    assert entry.task == "录后处理"
    assert entry.target == "任务 #1284"


def test_passes_through_non_json_plain_line() -> None:
    entry = parse_daemon_log_entry("plain log line")
    assert entry is not None
    assert entry.detail == "plain log line"
