"""Human-readable daemon log lines for Desktop `#daemon-log-panel`."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

_NOTIFY_KIND_LABELS: dict[str, str] = {
    "live_started": "开播提醒",
    "live_start_failed": "开播失败",
    "live_ended": "下播提醒",
    "new_aweme": "新作品",
    "new_archive": "新投稿",
    "new_dynamic": "新动态",
    "recording_completed": "录制完成",
    "transcribe_completed": "转录完成",
    "transcribe_partial": "直播字幕",
    "summarize_completed": "摘要完成",
    "upload_completed": "云备份完成",
    "upload_failed": "云备份失败",
    "upload_skipped": "云备份跳过",
    "upload_cleanup": "云盘清理",
}

_TASK_LABELS: dict[str, str] = {
    "sync_catalog": "同步作品列表",
    "download": "下载作品",
    "sync_dynamic": "同步动态",
    "finalize": "直播收尾",
    "pipeline_run": "作品流水线",
    "prepare_live_recording": "准备直播录制",
    "reconnect_recording": "录制重连",
}


@dataclass(frozen=True)
class DaemonLogEntry:
    time: str
    status: str
    task: str
    target: str
    detail: str | None = None
    level: str = "info"

    def to_line(self) -> str:
        parts = [self.status, self.task, self.target]
        if self.detail:
            parts.append(self.detail)
        body = " · ".join(parts)
        return f"[{self.time}] {body}" if self.time else body

    def to_dict(self) -> dict[str, str | None]:
        return {
            "time": self.time or None,
            "status": self.status,
            "task": self.task,
            "target": self.target,
            "detail": self.detail,
            "level": self.level,
            "line": self.to_line(),
        }


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
    if "deepgram returned empty transcript" in lowered:
        return "Deepgram 返回空转写"
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
        return "—"
    if names and creator_id in names:
        return names[creator_id]
    return _short_id(creator_id)


def _session_label(session_id: object) -> str:
    if not session_id:
        return "—"
    return f"会话 {_short_id(str(session_id))}"


def _aweme_label(aweme_id: object) -> str:
    if not aweme_id:
        return "—"
    text = str(aweme_id)
    return f"作品 #{text[-8:] if len(text) > 8 else text}"


def _task_label(task_type: object) -> str:
    key = str(task_type or "task")
    return _TASK_LABELS.get(key, key)


def _notify_kind_label(kind: object) -> str:
    raw = str(kind or "")
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    return _NOTIFY_KIND_LABELS.get(raw, raw.replace("_", " ") or "通知")


def _level_status(level: object, default: str) -> str:
    if level == "error":
        return "失败"
    if level == "warning":
        return "警告"
    return default


def _format_cli_json(obj: dict[str, Any]) -> DaemonLogEntry | None:
    command = obj.get("command")
    if not isinstance(command, str):
        return None
    task = "启动监控" if "monitor watch" in command else command
    if obj.get("ok") is False:
        err = obj.get("error") or obj.get("message") or "失败"
        return DaemonLogEntry(
            time=_short_time(obj.get("timestamp")),
            status="失败",
            task=task,
            target="守护进程",
            detail=_short_error(str(err)),
            level="error",
        )
    if obj.get("ok") is True:
        return DaemonLogEntry(
            time=_short_time(obj.get("timestamp")),
            status="完成",
            task=task,
            target="守护进程",
            level="info",
        )
    return DaemonLogEntry(
        time=_short_time(obj.get("timestamp")),
        status="进行中",
        task=task,
        target="守护进程",
        level=str(obj.get("level") or "info"),
    )


def _format_event(
    event: str,
    obj: dict[str, Any],
    *,
    names: dict[str, str] | None,
) -> DaemonLogEntry | None:
    creator = _creator_label(obj.get("creator_id"), names)
    level = str(obj.get("level") or "info")
    ts = _short_time(obj.get("timestamp"))

    handlers: dict[str, Callable[[], DaemonLogEntry]] = {
        "monitor_watch_daemon_started": lambda: DaemonLogEntry(
            time=ts,
            status="启动",
            task="监控守护",
            target="全局",
            detail=(
                f"直播 {obj.get('live_poll', '?')}s · "
                f"作品 {obj.get('vod_poll', '?')}s · "
                f"后处理 {obj.get('post_process_poll', '?')}s"
            ),
            level=level,
        ),
        "monitor_supervisor_started": lambda: DaemonLogEntry(
            time=ts,
            status="启动",
            task="内嵌监控",
            target=_creator_label(obj.get("creator_id"), names)
            if obj.get("creator_id")
            else "Desktop",
            level=level,
        ),
        "monitor_supervisor_stopped": lambda: DaemonLogEntry(
            time=ts,
            status="停止",
            task="内嵌监控",
            target="Desktop",
            level=level,
        ),
        "monitor_supervisor_thread_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="监控线程",
            target="Desktop",
            detail=_short_error(str(obj.get("error", "未知错误"))),
            level="error",
        ),
        "monitor_supervisor_stop_timeout": lambda: DaemonLogEntry(
            time=ts,
            status="警告",
            task="停止监控",
            target="Desktop",
            detail="后台线程仍在退出",
            level="warning",
        ),
        "monitor_external_stopped": lambda: DaemonLogEntry(
            time=ts,
            status="停止",
            task="外部监控",
            target=f"PID {obj.get('pid', '?')}",
            level=level,
        ),
        "live_tick": lambda: DaemonLogEntry(
            time=ts,
            status="进行中" if int(obj.get("active_recordings") or 0) > 0 else "空闲",
            task="直播检测",
            target=(
                f"{obj.get('active_recordings', 0)} 场录制中"
                if int(obj.get("active_recordings") or 0) > 0
                else "无活跃录制"
            ),
            detail=f"每 {obj.get('live_poll_sec', '?')} 秒一轮",
            level=level,
        ),
        "monitor_watch_lock_held": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="启动监控",
            target="守护进程",
            detail="已有实例在运行",
            level="error",
        ),
        "monitor_finalize_drained": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="直播收尾",
            target=f"{obj.get('count', 0)} 场",
            level=level,
        ),
        "monitor_task_enqueued": lambda: DaemonLogEntry(
            time=ts,
            status="排队",
            task=_task_label(obj.get("task_type")),
            target=creator,
            level=level,
        ),
        "monitor_task_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task=_task_label(obj.get("task_type")),
            target=creator,
            detail=_short_error(str(obj.get("error") or obj.get("outcome") or "任务失败")),
            level="error",
        ),
        "monitor_download_transcribe_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="作品转写",
            target=_aweme_label(obj.get("aweme_id")),
            detail=_short_error(str(obj.get("error", "转写失败"))),
            level="warning",
        ),
        "content_due_marked": lambda: DaemonLogEntry(
            time=ts,
            status="排队",
            task="作品同步",
            target=creator,
            detail=f"{obj.get('platform', '平台')} 轮询",
            level=level,
        ),
        "live_status_check_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="开播检测",
            target=creator,
            detail=_short_error(str(obj.get("error", "未知错误"))),
            level="warning",
        ),
        "live_stream_url_resolve_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="获取直播流",
            target=creator,
            detail=_short_error(str(obj.get("error", "未知错误"))),
            level="warning",
        ),
        "live_recording_started": lambda: DaemonLogEntry(
            time=ts,
            status="进行中",
            task="直播录制",
            target=_session_label(obj.get("session_id")),
            detail="已开始拉流",
            level=level,
        ),
        "live_recording_completed": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="直播录制",
            target=creator if creator != "—" else _session_label(obj.get("session_id")),
            detail="MP4 已保存",
            level=level,
        ),
        "live_recording_completed_streaming": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="直播录制",
            target=creator if creator != "—" else _session_label(obj.get("session_id")),
            detail="流式收尾完成",
            level=level,
        ),
        "live_recording_completed_streaming_hls": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="直播录制",
            target=_session_label(obj.get("session_id")),
            detail="HLS 流式收尾",
            level=level,
        ),
        "live_recording_reconnected": lambda: DaemonLogEntry(
            time=ts,
            status="进行中",
            task="录制重连",
            target=_session_label(obj.get("session_id")),
            detail=f"第 {obj.get('attempt', 1)} 次",
            level=level,
        ),
        "live_recording_reconnected_hls": lambda: DaemonLogEntry(
            time=ts,
            status="进行中",
            task="HLS 重连",
            target=_session_label(obj.get("session_id")),
            detail=f"第 {obj.get('attempt', 1)} 次 · 分段 {obj.get('part_index', '?')}",
            level=level,
        ),
        "live_recording_empty": lambda: DaemonLogEntry(
            time=ts,
            status="警告",
            task="直播录制",
            target=_session_label(obj.get("session_id")),
            detail="文件为空，已跳过",
            level="warning",
        ),
        "live_recording_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="直播录制",
            target=_session_label(obj.get("session_id")),
            detail=_short_error(str(obj.get("error", "录制失败"))),
            level="error",
        ),
        "live_stale_sessions_cleared": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="清理卡住录制",
            target=f"{obj.get('count', 0)} 场",
            level=level,
        ),
        "bilibili_live_stale_sessions_cleared": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="清理 B 站卡住录制",
            target=f"{obj.get('count', 0)} 场",
            level=level,
        ),
        "streaming_stt_reconnected": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="实时转写",
            target=_session_label(obj.get("session_id")),
            detail="已重连",
            level=level,
        ),
        "streaming_stt_deepgram_error": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="实时转写",
            target=_session_label(obj.get("session_id")),
            detail=_short_error(str(obj.get("error", "Deepgram 错误"))),
            level="warning",
        ),
        "streaming_stt_feed_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="实时转写",
            target=_session_label(obj.get("session_id")),
            detail=_short_error(str(obj.get("error", "音频推送失败"))),
            level="warning",
        ),
        "streaming_stt_reconnect_after_ffmpeg_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="转写重连",
            target=_session_label(obj.get("session_id")),
            detail=_short_error(str(obj.get("error", "ffmpeg 重连后 STT 失败"))),
            level="warning",
        ),
        "streaming_stt_reconnect_after_hls_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="转写重连",
            target=_session_label(obj.get("session_id")),
            detail=_short_error(str(obj.get("error", "HLS 重连后 STT 失败"))),
            level="warning",
        ),
        "archive_index_upsert": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="更新索引",
            target=f"{obj.get('segments', 0)} 段",
            level=level,
        ),
        "post_process_job_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="录后处理",
            target=f"任务 #{_short_id(str(obj.get('job_id', '?')))}",
            detail=_short_error(str(obj.get("error", "处理失败"))),
            level="error",
        ),
        "post_process_parallel_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="录后处理",
            target=f"任务 #{_short_id(str(obj.get('job_id', '?')))}",
            detail=f"{obj.get('branch', '分支')} · {_short_error(str(obj.get('error', '失败')))}",
            level="error",
        ),
        "live_summarize_completed": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="直播摘要",
            target=_short_id(str(obj.get("path", "—")).rsplit("/", 1)[-1], n=16),
            level=level,
        ),
        "live_summarize_skipped": lambda: DaemonLogEntry(
            time=ts,
            status="跳过",
            task="直播摘要",
            target=_short_id(str(obj.get("path", "—")).rsplit("/", 1)[-1], n=16),
            detail=_short_error(str(obj.get("reason", "已跳过"))),
            level="warning",
        ),
        "live_transcribe_skipped": lambda: DaemonLogEntry(
            time=ts,
            status="跳过",
            task="直播转写",
            target=_short_id(str(obj.get("path", "—")).rsplit("/", 1)[-1], n=16),
            detail=_short_error(str(obj.get("reason", "已跳过"))),
            level="warning",
        ),
        "cloud_upload_done": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="云备份",
            target=_session_label(obj.get("session_id")),
            level=level,
        ),
        "notify_delivered": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="通知推送",
            target=(
                _creator_label(obj.get("creator_id"), names)
                if obj.get("creator_id")
                else str(obj.get("title") or "—")
            ),
            detail=_notify_kind_label(obj.get("kind")),
            level=level,
        ),
        "notify_feishu_skipped": lambda: DaemonLogEntry(
            time=ts,
            status="跳过",
            task="飞书通知",
            target="—",
            detail=str(obj.get("reason", "未配置 webhook")),
            level=level,
        ),
        "notify_sound_failed": lambda: DaemonLogEntry(
            time=ts,
            status="警告",
            task="系统提示音",
            target="—",
            detail=_short_error(str(obj.get("error", "播放失败"))),
            level="warning",
        ),
        "feishu_webhook_failed": lambda: DaemonLogEntry(
            time=ts,
            status="失败",
            task="飞书通知",
            target="—",
            detail=_short_error(str(obj.get("error", "发送失败"))),
            level="warning",
        ),
        "reconcile_shadow": lambda: DaemonLogEntry(
            time=ts,
            status="完成",
            task="任务对账",
            target=f"直播 {obj.get('live', 0)} · 作品 {obj.get('content', 0)}",
            level=level,
        ),
        "monitor_scheduler_stop_failed": lambda: DaemonLogEntry(
            time=ts,
            status="警告",
            task="停止调度器",
            target="—",
            detail=_short_error(str(obj.get("error", "停止失败"))),
            level="warning",
        ),
    }
    fn = handlers.get(event)
    if fn is not None:
        return fn()
    return None


def _format_fallback(obj: dict[str, Any], *, names: dict[str, str] | None) -> DaemonLogEntry:
    cli = _format_cli_json(obj)
    if cli:
        return cli
    event = obj.get("event")
    if isinstance(event, str):
        custom = _format_event(event, obj, names=names)
        if custom:
            return custom
        task = event.replace("_", " ")
    else:
        task = str(obj.get("msg") or obj.get("message") or "日志")

    target = "—"
    if obj.get("creator_id"):
        target = _creator_label(str(obj["creator_id"]), names)
    elif obj.get("session_id"):
        target = _session_label(obj.get("session_id"))
    elif obj.get("aweme_id"):
        target = _aweme_label(obj.get("aweme_id"))
    elif obj.get("title"):
        target = str(obj["title"])

    detail_parts: list[str] = []
    for key in ("error", "reason", "count", "task_type", "outcome", "kind"):
        if obj.get(key) is not None:
            val = obj[key]
            if key == "error":
                detail_parts.append(_short_error(str(val)))
            elif key == "kind":
                detail_parts.append(_notify_kind_label(val))
            elif key == "task_type":
                detail_parts.append(_task_label(val))
            else:
                detail_parts.append(f"{key}={val}")

    level = str(obj.get("level") or "info")
    return DaemonLogEntry(
        time=_short_time(obj.get("timestamp")),
        status=_level_status(level, "信息"),
        task=task,
        target=target,
        detail=" · ".join(detail_parts) if detail_parts else None,
        level=level,
    )


def parse_daemon_log_entry(
    line: str,
    *,
    creator_names: dict[str, str] | None = None,
) -> DaemonLogEntry | None:
    """Parse one raw log line into a structured entry."""
    raw = line.strip()
    if not raw:
        return None
    if raw.startswith("[") and "]" in raw[:12]:
        # Already formatted — keep as single-line info entry.
        bracket_end = raw.index("]")
        time_part = raw[1:bracket_end]
        body = raw[bracket_end + 1 :].strip()
        parts = [p.strip() for p in body.split(" · ")] if body else []
        return DaemonLogEntry(
            time=time_part,
            status=parts[0] if len(parts) > 0 else "信息",
            task=parts[1] if len(parts) > 1 else body or "日志",
            target=parts[2] if len(parts) > 2 else "—",
            detail=" · ".join(parts[3:]) if len(parts) > 3 else None,
        )
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return DaemonLogEntry(
            time="",
            status="信息",
            task="系统",
            target="—",
            detail=raw,
        )
    if not isinstance(obj, dict):
        return DaemonLogEntry(time="", status="信息", task="系统", target="—", detail=raw)
    event = obj.get("event")
    entry = (
        _format_event(str(event), obj, names=creator_names)
        if isinstance(event, str)
        else None
    )
    if entry is None:
        entry = _format_fallback(obj, names=creator_names)
    return entry


def format_daemon_log_line(
    line: str,
    *,
    creator_names: dict[str, str] | None = None,
) -> str:
    """Format one log line as ``[HH:MM:SS] 状态 · 任务 · 目标 · 详情``."""
    entry = parse_daemon_log_entry(line, creator_names=creator_names)
    if entry is None:
        return ""
    return entry.to_line()


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


def format_daemon_log_entries(
    lines: list[str],
    *,
    creator_names: dict[str, str] | None = None,
) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    for line in lines:
        entry = parse_daemon_log_entry(line, creator_names=creator_names)
        if entry is not None:
            entries.append(entry.to_dict())
    return entries
