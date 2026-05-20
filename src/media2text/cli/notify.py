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

    svc = NotifyService(cfg)
    sent: list[str] = []
    for kind in EventKind:
        svc.emit(
            NotifyEvent(
                kind=kind,
                title="配置测试",
                body="media2text notify test — 若收到本条说明该事件通道正常",
            )
        )
        sent.append(kind.value)

    emit(
        {
            "ok": True,
            "command": "notify test",
            "sent": sent,
            "status": status,
            "hint": "检查系统是否播放提示音，飞书群是否收到 4 条测试消息",
        },
        as_json=json_out,
    )
