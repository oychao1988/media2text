from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger()


def send_feishu_text(*, webhook_url: str, text: str, timeout_sec: float = 10.0) -> bool:
    payload = {"msg_type": "text", "content": {"text": text}}
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("code") not in (None, 0):
                log.warning(
                    "feishu_webhook_rejected",
                    code=data.get("code"),
                    msg=data.get("msg"),
                )
                return False
    except Exception as exc:  # noqa: BLE001
        log.warning("feishu_webhook_failed", error=str(exc))
        return False
    return True
