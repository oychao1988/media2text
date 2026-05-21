from __future__ import annotations

import os

import typer

from media2text.core.config import AppConfig
from media2text.core.json_out import emit
from media2text.core.notify import EventKind, NotifyEvent, NotifyService

app = typer.Typer(help="Monitor event notifications (sound + Feishu webhook)")


def _notify_status(cfg: AppConfig) -> dict:
    n = cfg.notify
    webhook: str | None = None
    if n.feishu.webhook_url:
        webhook = n.feishu.webhook_url.strip()
    elif n.feishu.webhook_url_env:
        webhook = os.environ.get(n.feishu.webhook_url_env, "").strip() or None
    return {
        "enabled": n.enabled,
        "sound": n.sound,
        "feishu_enabled": n.feishu.enabled,
        "webhook_configured": bool(webhook),
        "webhook_env": n.feishu.webhook_url_env,
        "rich_text": n.feishu.rich_text,
        "image_enabled": n.feishu.image_enabled,
        "image_upload_ready": NotifyService(cfg).image_available(),
        "media_base_url": n.feishu.media_base_url or None,
        "transcript_push": n.feishu.transcript_push,
        "events": n.events.model_dump(),
    }


@app.command("test")
def notify_test(
    json_out: bool = typer.Option(False, "--json"),
    skip_sound: bool = typer.Option(False, "--skip-sound", help="Do not play system sound"),
    skip_feishu: bool = typer.Option(False, "--skip-feishu", help="Do not call Feishu webhook"),
) -> None:
    """Send one test notification per event kind (sound + Feishu)."""
    cfg = AppConfig.load()
    status = _notify_status(cfg)
    if not status["enabled"]:
        emit(
            {
                "ok": False,
                "command": "notify test",
                "error": "notify.enabled is false in config.yaml",
                "status": status,
            },
            as_json=json_out,
        )
        raise typer.Exit(1)

    if status["feishu_enabled"] and not status["webhook_configured"] and not skip_feishu:
        emit(
            {
                "ok": False,
                "command": "notify test",
                "error": (
                    f"Feishu webhook not configured; set notify.feishu.webhook_url "
                    f"or export {status['webhook_env']}"
                ),
                "status": status,
            },
            as_json=json_out,
        )
        raise typer.Exit(2)

    if skip_sound:
        cfg.notify.sound = False
    if skip_feishu:
        cfg.notify.feishu.enabled = False

    from media2text.core.notify.samples import find_latest_transcript_with_media

    svc = NotifyService(cfg)
    ws = cfg.ensure_workspace()
    sample_md, sample_mp4 = find_latest_transcript_with_media(ws)
    sent: list[str] = []
    for kind in EventKind:
        event = NotifyEvent(
            kind=kind,
            title="配置测试",
            body="media2text notify test — 富文本/摘要/图片自检",
            summary="这是摘要示例：用于验证 post 消息排版。" if kind == EventKind.TRANSCRIBE_COMPLETED else None,
            media_path=sample_mp4 if sample_mp4 and sample_mp4.is_file() else None,
            transcript_path=sample_md if sample_md and sample_md.is_file() else None,
        )
        svc.emit(event)
        sent.append(kind.value)

    emit(
        {
            "ok": True,
            "command": "notify test",
            "sent": sent,
            "status": status,
            "hint": (
                "检查提示音；飞书应收到富文本+图片；转录完成另发 [转写全文] 文本（未配 media_base_url 时）"
            ),
        },
        as_json=json_out,
    )


@app.command("serve")
def notify_serve(
    host: str = typer.Option("0.0.0.0", help="Bind address"),
    port: int = typer.Option(8765, help="HTTP port for serving workspace files"),
) -> None:
    """Serve data/ over HTTP so Feishu post links (media_base_url) are clickable."""
    from media2text.core.notify.serve import run_workspace_http_server

    cfg = AppConfig.load()
    run_workspace_http_server(workspace=cfg.ensure_workspace(), host=host, port=port)
