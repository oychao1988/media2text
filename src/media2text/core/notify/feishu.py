from __future__ import annotations

from typing import Any

import httpx
import structlog

log = structlog.get_logger()


def _post_json(*, webhook_url: str, payload: dict[str, Any], timeout_sec: float) -> bool:
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("code") not in (None, 0):
                log.warning(
                    "feishu_webhook_rejected",
                    msg_type=payload.get("msg_type"),
                    code=data.get("code"),
                    msg=data.get("msg"),
                )
                return False
    except Exception as exc:  # noqa: BLE001
        log.warning("feishu_webhook_failed", msg_type=payload.get("msg_type"), error=str(exc))
        return False
    return True


def send_feishu_text(*, webhook_url: str, text: str, timeout_sec: float = 10.0) -> bool:
    return _post_json(
        webhook_url=webhook_url,
        payload={"msg_type": "text", "content": {"text": text}},
        timeout_sec=timeout_sec,
    )


def send_feishu_text_chunks(
    *,
    webhook_url: str,
    chunks: list[str],
    timeout_sec: float = 10.0,
) -> int:
    """Send multiple text messages; returns count successfully sent."""
    sent = 0
    total = len(chunks)
    for i, chunk in enumerate(chunks, start=1):
        prefix = f"[转写 {i}/{total}]\n" if total > 1 else "[转写全文]\n"
        if send_feishu_text(webhook_url=webhook_url, text=prefix + chunk, timeout_sec=timeout_sec):
            sent += 1
    return sent


def send_feishu_post(
    *,
    webhook_url: str,
    title: str,
    paragraphs: list[list[dict[str, Any]]],
    timeout_sec: float = 10.0,
) -> bool:
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title[:255],
                    "content": paragraphs,
                }
            }
        },
    }
    return _post_json(webhook_url=webhook_url, payload=payload, timeout_sec=timeout_sec)


def send_feishu_image(
    *,
    webhook_url: str,
    image_key: str,
    timeout_sec: float = 10.0,
) -> bool:
    return _post_json(
        webhook_url=webhook_url,
        payload={"msg_type": "image", "content": {"image_key": image_key}},
        timeout_sec=timeout_sec,
    )


def append_image_paragraph(paragraphs: list[list[dict[str, Any]]], image_key: str) -> None:
    paragraphs.append([{"tag": "img", "image_key": image_key}])
