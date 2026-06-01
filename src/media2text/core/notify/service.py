from __future__ import annotations

import os
from pathlib import Path

import structlog

from media2text.core.config import AppConfig
from media2text.core.notify.events import EventKind, NotifyEvent
from media2text.core.notify.feishu import send_feishu_text
from media2text.core.notify.sound import play_sound

log = structlog.get_logger()

_KIND_LABELS: dict[EventKind, str] = {
    EventKind.LIVE_STARTED: "开播",
    EventKind.NEW_AWEME: "新作品",
    EventKind.RECORDING_COMPLETED: "录制完成",
    EventKind.TRANSCRIBE_COMPLETED: "转录完成",
    EventKind.UPLOAD_COMPLETED: "云备份完成",
    EventKind.UPLOAD_FAILED: "云备份失败",
    EventKind.UPLOAD_SKIPPED: "云备份跳过",
    EventKind.UPLOAD_CLEANUP: "云盘清理",
}


class NotifyService:
    def __init__(self, cfg: AppConfig) -> None:
        self._notify = cfg.notify

    @property
    def enabled(self) -> bool:
        return self._notify.enabled

    def emit(self, event: NotifyEvent) -> None:
        if not self._notify.enabled:
            return
        if not self._event_enabled(event.kind):
            return

        if self._notify.sound:
            play_sound(self._resolve_sound_path())

        webhook = self._resolve_webhook_url()
        if self._notify.feishu.enabled and webhook:
            label = _KIND_LABELS.get(event.kind, event.kind)
            text = f"[media2text] {label}\n{event.title}\n{event.body}"
            send_feishu_text(webhook_url=webhook, text=text, timeout_sec=self._notify.feishu.timeout_sec)
        elif self._notify.feishu.enabled and not webhook:
            log.debug("notify_feishu_skipped", reason="missing_webhook_url")

        log.info("notify_emitted", kind=event.kind, title=event.title)

    def _event_enabled(self, kind: EventKind) -> bool:
        events = self._notify.events
        return getattr(events, kind.value, True)

    def _resolve_webhook_url(self) -> str | None:
        feishu = self._notify.feishu
        if feishu.webhook_url:
            return feishu.webhook_url.strip()
        env_name = feishu.webhook_url_env
        if env_name:
            val = os.environ.get(env_name, "").strip()
            if val:
                return val
        return None

    def _resolve_sound_path(self) -> Path | None:
        raw = self._notify.sound_path
        if raw:
            p = Path(raw).expanduser()
            return p if p.is_file() else None
        return None
