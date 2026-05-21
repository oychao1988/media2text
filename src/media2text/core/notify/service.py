from __future__ import annotations

import os
from pathlib import Path

import structlog

from media2text.core.config import AppConfig
from media2text.core.notify.avatar import download_avatar_image
from media2text.core.notify.content import (
    build_media_link,
    chunk_text,
    extract_transcript_summary,
    format_transcript_for_push,
    media_mp4_path,
    post_paragraphs,
)
from media2text.core.notify.events import EventKind, NotifyEvent
from media2text.core.notify.feishu import (
    append_image_paragraph,
    send_feishu_image,
    send_feishu_post,
    send_feishu_text,
    send_feishu_text_chunks,
)
from media2text.core.notify.feishu_app import upload_image
from media2text.core.notify.sound import play_sound
from media2text.core.notify.thumbnail import extract_video_thumbnail

log = structlog.get_logger()

_KIND_LABELS: dict[EventKind, str] = {
    EventKind.LIVE_STARTED: "开播",
    EventKind.NEW_AWEME: "新作品",
    EventKind.RECORDING_COMPLETED: "录制完成",
    EventKind.TRANSCRIBE_COMPLETED: "转录完成",
}


class NotifyService:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._notify = cfg.notify
        self._workspace = cfg.ensure_workspace()

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
        feishu = self._notify.feishu
        if feishu.enabled and webhook:
            self._send_feishu(webhook, event)
        elif feishu.enabled and not webhook:
            log.debug("notify_feishu_skipped", reason="missing_webhook_url")

        log.info("notify_emitted", kind=event.kind, title=event.title)

    def _send_feishu(self, webhook: str, event: NotifyEvent) -> None:
        feishu = self._notify.feishu
        label = _KIND_LABELS.get(event.kind, event.kind)
        use_rich = feishu.rich_text and self._event_wants_rich(event)
        if not use_rich:
            text = f"[media2text] {label}\n{event.title}\n{event.body}"
            send_feishu_text(webhook_url=webhook, text=text, timeout_sec=feishu.timeout_sec)
            self._maybe_push_transcript_text(webhook, event)
            return

        summary = event.summary
        if summary is None and event.transcript_path:
            summary = extract_transcript_summary(
                event.transcript_path,
                max_chars=feishu.summary_max_chars,
            )
            if not summary:
                summary = None

        paths = self._collect_path_lines(event)
        paragraphs = post_paragraphs(
            title_line=f"{label} · {event.title}",
            body=event.body,
            summary=summary,
            paths=paths,
        )

        image_key: str | None = None
        if feishu.image_enabled:
            image_key = self._resolve_image_key(event)

        post_title = f"{label} · {event.title}"[:255]
        if image_key and feishu.image_in_post:
            append_image_paragraph(paragraphs, image_key)
        send_feishu_post(
            webhook_url=webhook,
            title=post_title,
            paragraphs=paragraphs,
            timeout_sec=feishu.timeout_sec,
        )
        if image_key and feishu.image_separate_message:
            ok = send_feishu_image(
                webhook_url=webhook,
                image_key=image_key,
                timeout_sec=feishu.timeout_sec,
            )
            if ok:
                log.info("notify_feishu_image_sent", kind=event.kind, title=event.title)
            else:
                log.warning("notify_feishu_image_failed", kind=event.kind, title=event.title)
        elif feishu.image_enabled and self._resolve_app_credentials() and self._resolve_image_file(event):
            log.warning("notify_image_not_sent", kind=event.kind, title=event.title)

        self._maybe_push_transcript_text(webhook, event)

    def _maybe_push_transcript_text(self, webhook: str, event: NotifyEvent) -> None:
        feishu = self._notify.feishu
        if not feishu.transcript_push or not event.transcript_path:
            return
        if feishu.media_base_url.strip():
            return
        if event.kind not in (EventKind.TRANSCRIBE_COMPLETED,):
            return
        body = format_transcript_for_push(Path(event.transcript_path))
        if not body:
            return
        max_chars = max(feishu.transcript_push_max_chars, 500)
        max_msgs = max(feishu.transcript_push_max_messages, 1)
        chunks = chunk_text(body, max_chars=max_chars)[:max_msgs]
        if not chunks:
            return
        sent = send_feishu_text_chunks(
            webhook_url=webhook,
            chunks=chunks,
            timeout_sec=feishu.timeout_sec,
        )
        if sent:
            log.info(
                "notify_feishu_transcript_sent",
                kind=event.kind,
                parts=sent,
                title=event.title,
            )
        else:
            log.warning("notify_feishu_transcript_failed", kind=event.kind, title=event.title)

    def _event_wants_rich(self, event: NotifyEvent) -> bool:
        if event.summary or event.transcript_path or event.media_path or event.link_url:
            return True
        if event.image_path:
            return True
        feishu = self._notify.feishu
        if feishu.image_enabled and event.kind in (
            EventKind.LIVE_STARTED,
            EventKind.RECORDING_COMPLETED,
            EventKind.TRANSCRIBE_COMPLETED,
        ):
            return bool(self._resolve_app_credentials())
        return bool(feishu.media_base_url)

    def _collect_path_lines(self, event: NotifyEvent) -> list[tuple[str, str | None]]:
        feishu = self._notify.feishu
        lines: list[tuple[str, str | None]] = []
        base = feishu.media_base_url.strip()

        if event.link_url:
            lines.append(("链接", event.link_url))
        if event.media_path:
            mp = Path(event.media_path)
            href = build_media_link(base_url=base, workspace=self._workspace, media_path=mp) if base else None
            if href:
                lines.append(("媒体", href))
            elif feishu.show_local_paths:
                lines.append(("媒体", str(mp.resolve())))
            else:
                lines.append(("媒体", mp.name))
        if event.transcript_path:
            tp = Path(event.transcript_path)
            href = build_media_link(base_url=base, workspace=self._workspace, media_path=tp) if base else None
            if href:
                lines.append(("转写", href))
            elif feishu.show_local_paths:
                lines.append(("转写", str(tp.resolve())))
            else:
                lines.append(("转写", tp.name))
        if (
            feishu.include_paths
            and not base
            and not feishu.show_local_paths
            and (event.media_path or event.transcript_path)
            and not any(l[0] == "提示" for l in lines)
        ):
            lines.append(
                (
                    "提示",
                    "未配置 media_base_url，链接不可点击；完整路径见本机 data 目录",
                )
            )
        if feishu.include_paths and not lines and event.body:
            lines.append(("详情", None))
        return lines

    def _resolve_image_key(self, event: NotifyEvent) -> str | None:
        creds = self._resolve_app_credentials()
        if not creds:
            return None
        app_id, app_secret = creds
        image_file = self._resolve_image_file(event)
        if not image_file:
            return None
        key = upload_image(
            image_path=image_file,
            app_id=app_id,
            app_secret=app_secret,
            timeout_sec=self._notify.feishu.timeout_sec,
        )
        if image_file.name.startswith("media2text-avatar-"):
            image_file.unlink(missing_ok=True)
        return key

    def _resolve_image_file(self, event: NotifyEvent) -> Path | None:
        feishu = self._notify.feishu
        if event.image_path and Path(event.image_path).is_file():
            return Path(event.image_path)
        if feishu.thumbnail_from_video and event.kind in (
            EventKind.RECORDING_COMPLETED,
            EventKind.TRANSCRIBE_COMPLETED,
        ):
            video = self._resolve_video_path(event)
            if video:
                return extract_video_thumbnail(
                    ffmpeg=self._cfg.live.ffmpeg_path,
                    video_path=video,
                )
        return None

    def image_available(self) -> bool:
        return bool(self._notify.feishu.image_enabled and self._resolve_app_credentials())

    def _resolve_video_path(self, event: NotifyEvent) -> Path | None:
        if event.media_path:
            mp = Path(event.media_path)
            if mp.suffix.lower() == ".mp4" and mp.is_file():
                return mp
            if mp.name.endswith(".transcript.md") and mp.is_file():
                sibling = media_mp4_path(mp)
                return sibling if sibling.is_file() else None
        if event.transcript_path:
            sibling = media_mp4_path(Path(event.transcript_path))
            return sibling if sibling.is_file() else None
        return None

    def _resolve_app_credentials(self) -> tuple[str, str] | None:
        feishu = self._notify.feishu
        app_id = feishu.app_id or (os.environ.get(feishu.app_id_env, "").strip() if feishu.app_id_env else "")
        app_secret = feishu.app_secret or (
            os.environ.get(feishu.app_secret_env, "").strip() if feishu.app_secret_env else ""
        )
        if app_id and app_secret:
            return app_id, app_secret
        return None

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


def build_live_started_event(
    *,
    label: str,
    room_id: str | None,
    temp_name: str,
    avatar_url: str | None,
    cfg: AppConfig,
) -> NotifyEvent:
    image_path: Path | None = None
    feishu = cfg.notify.feishu
    if feishu.image_enabled and feishu.avatar_on_live_start and avatar_url:
        image_path = download_avatar_image(avatar_url)
    return NotifyEvent(
        kind=EventKind.LIVE_STARTED,
        title=label,
        body=f"检测到开播，已开始录制\nroom_id: {room_id or '—'}\n文件: {temp_name}",
        image_path=image_path,
    )
