import json

from media2text.core.runtime.log_format import format_daemon_log_line


def test_formats_structlog_json_with_timestamp() -> None:
    line = json.dumps(
        {
            "event": "monitor_watch_daemon_started",
            "live_poll": 20,
            "post_process_poll": 10,
            "timestamp": "2026-06-05T10:42:01.123456+00:00",
            "level": "info",
        }
    )
    out = format_daemon_log_line(line)
    assert out.startswith("[")
    assert "监控已启动" in out
    assert "20 秒" in out


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
    assert "开播状态查询失败" in out
    assert "B站接口限流" in out
    assert "警告" in out


def test_formats_cli_json_failure() -> None:
    line = json.dumps({"ok": False, "command": "monitor watch", "error": "already_running"})
    out = format_daemon_log_line(line)
    assert out == "启动监控失败：监控进程已在运行"


def test_passes_through_prefixed_plain_line() -> None:
    line = "[10:42:21] post_process claim job #1284"
    assert format_daemon_log_line(line) == line


def test_passes_through_non_json_plain_line() -> None:
    assert format_daemon_log_line("plain log line") == "plain log line"
