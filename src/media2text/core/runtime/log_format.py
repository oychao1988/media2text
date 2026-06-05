"""Human-readable daemon log lines for Desktop `#daemon-log-panel`."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable


def _short_time(timestamp: str | None) -> str:
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M:%S")
    except ValueError:
        return ""


def _short_id(value: str, *, n: int = 8) -> str:
    text = value.strip()
    return text if len(text) <= n else text[:n]


def _short_error(error: str, *, max_len: int = 72) -> str:
    text = _humanize_error(error)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _humanize_error(error: str) -> str:
    text = re.sub(r"\s+", " ", error.strip())
    lowered = text.lower()
    if "bilibili api code -799" in lowered or "请求过于频繁" in text:
        return "B站接口限流，稍后再试"
    if "executable doesn't exist" in lowered:
        return "Playwright 浏览器未安装或路径错误"
    if "segv" in lowered or "signal=sigsegv" in lowered or "headless_shell" in lowered:
        return "Playwright Chromium 崩溃，请运行 playwright install chromium"
    if "already_running" in lowered or "already running" in lowered or "lock held" in lowered:
        return "监控进程已在运行"
    if text.lower().startswith("live status failed:"):
        return _humanize_error(text.split(":", 1)[-1].strip())
    return text


def _creator_label(creator_id: str | None, names: dict[str, str] | None) -> str:
    if not creator_id:
        return "creator"
    if names and creator_id in names:
        return names[creator_id]
    return _short_id(creator_id)


def _format_cli_json(obj: dict[str, Any]) -> str | None:
    command = obj.get("command")
    if not isinstance(command, str):
        return None
    label = "启动监控" if "monitor watch" in command else command
    if obj.get("ok") is False:
        err = obj.get("error") or obj.get("message") or "失败"
        return f"{label}失败：{_short_error(str(err))}"
    if obj.get("ok") is True:
        return f"{label}成功"
    return label


def _format_event(
    event: str,
    obj: dict[str, Any],
    *,
    names: dict[str, str] | None,
) -> str | None:
    creator = _creator_label(obj.get("creator_id"), names)
    task_labels = {
        "sync_catalog": "同步作品列表",
        "download": "下载作品",
        "sync_dynamic": "同步动态",
        "finalize": "直播收尾",
        "pipeline_run": "作品流水线",
    }

    def _task_label(task_type: object) -> str:
        key = str(task_type or "task")
        return task_labels.get(key, key)

    handlers: dict[str, Callable[[dict[str, Any]], str]] = {
        "monitor_watch_daemon_started": lambda o: (
            f"监控已启动 · 直播每 {o.get('live_poll', '?')} 秒检测"
        ),
        "monitor_supervisor_started": lambda _: "内嵌监控已启动",
        "monitor_supervisor_stopped": lambda _: "内嵌监控已停止",
        "monitor_supervisor_thread_failed": lambda o: (
            "监控线程异常退出"
            + (
                f"：{_short_error(str(o.get('error', '未知错误')))}"
                if o.get("error")
                else "，请尝试重新启动"
            )
        ),
        "monitor_supervisor_stop_timeout": lambda _: "停止超时，后台线程仍在退出",
        "live_tick": lambda o: (
            f"直播检测一轮 · 正在录制 {o.get('active_recordings', 0)} 场"
        ),
        "monitor_watch_lock_held": lambda _: "已有监控进程在运行，无法重复启动",
        "monitor_finalize_drained": lambda o: f"直播收尾完成 {o.get('count', 0)} 场",
        "monitor_task_enqueued": lambda o: (
            f"排队 {_task_label(o.get('task_type'))} · {creator}"
        ),
        "monitor_task_failed": lambda o: (
            f"{_task_label(o.get('task_type'))}失败 · {creator}"
        ),
        "live_status_check_failed": lambda o: (
            f"{creator} 开播状态查询失败：{_short_error(str(o.get('error', '未知错误')))}"
        ),
        "live_stream_url_resolve_failed": lambda o: (
            f"{creator} 直播流地址获取失败：{_short_error(str(o.get('error', '未知错误')))}"
        ),
        "live_recording_completed": lambda o: (
            f"{creator} 录制完成"
        ),
        "live_recording_completed_streaming": lambda o: (
            f"{creator} 流式录制收尾完成"
        ),
        "live_recording_reconnected": lambda o: (
            f"录制断线重连 · 第 {o.get('attempt', 1)} 次"
        ),
        "live_recording_empty": lambda o: "录制文件为空，已跳过",
        "live_stale_sessions_cleared": lambda o: f"清理卡住录制 {o.get('count', 0)} 场",
        "streaming_stt_reconnected": lambda o: "实时转写已重连",
        "archive_index_upsert": lambda o: (
            f"更新索引 · {o.get('segments', 0)} 段"
        ),
        "post_process_job_failed": lambda o: "录后处理失败",
    }
    fn = handlers.get(event)
    if fn is not None:
        return fn(obj)
    return None


def _format_fallback(obj: dict[str, Any], *, names: dict[str, str] | None) -> str:
    cli = _format_cli_json(obj)
    if cli:
        return cli
    event = obj.get("event")
    if isinstance(event, str):
        custom = _format_event(event, obj, names=names)
        if custom:
            return custom
        label = event.replace("_", " ")
    else:
        label = str(obj.get("msg") or obj.get("message") or "log")
    parts = [label]
    if obj.get("creator_id"):
        parts[0] = f"{_creator_label(str(obj['creator_id']), names)} · {parts[0]}"
    for key in ("error", "reason", "count", "task_type", "outcome"):
        if obj.get(key) is not None:
            val = obj[key]
            if key == "error":
                parts.append(_short_error(str(val)))
            else:
                parts.append(f"{key}={val}")
    return " · ".join(parts)


def format_daemon_log_line(
    line: str,
    *,
    creator_names: dict[str, str] | None = None,
) -> str:
    """Format one log line as ``[HH:MM:SS] message`` for Desktop daemon panel."""
    raw = line.strip()
    if not raw:
        return ""
    if raw.startswith("[") and "]" in raw[:12]:
        return raw
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(obj, dict):
        return raw
    ts = _short_time(obj.get("timestamp"))
    event = obj.get("event")
    message = (
        _format_event(str(event), obj, names=creator_names)
        if isinstance(event, str)
        else None
    )
    if message is None:
        message = _format_fallback(obj, names=creator_names)
    level = obj.get("level")
    if level in ("warning", "error"):
        prefix = "警告" if level == "warning" else "错误"
        message = f"{prefix} · {message}"
    return f"[{ts}] {message}" if ts else message


def format_daemon_log_lines(
    lines: list[str],
    *,
    creator_names: dict[str, str] | None = None,
) -> list[str]:
    return [
        formatted
        for line in lines
        if (formatted := format_daemon_log_line(line, creator_names=creator_names))
    ]
