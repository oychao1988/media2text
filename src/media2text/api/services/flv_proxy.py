"""HTTP-FLV reverse proxy for active live sessions."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
from fastapi import HTTPException

from media2text.core.config import AppConfig
from media2text.core.errors import ConfigError
from media2text.core.platform.registry import get_adapter
from media2text.core.storage.models import LiveSessionRow
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo


def _platform_session_file(cfg: AppConfig, platform: str) -> Path:
    ws = cfg.ensure_workspace()
    if platform == "douyin":
        from media2text.core.platform.douyin.auth import session_path

        return session_path(ws)
    if platform == "bilibili":
        from media2text.core.platform.bilibili.auth import session_path

        return session_path(ws)
    raise ConfigError(f"unsupported platform: {platform!r}")


def httpx_client_for_platform(cfg: AppConfig, platform: str) -> httpx.Client:
    session_file = _platform_session_file(cfg, platform)
    if not session_file.is_file():
        raise HTTPException(status_code=401, detail="platform session required")
    if platform == "douyin":
        from media2text.core.platform.douyin.httpx_client import client_from_storage

        return client_from_storage(session_file, timeout=120.0)
    from media2text.core.platform.bilibili.httpx_client import client_from_storage

    return client_from_storage(session_file, timeout=120.0)


def resolve_upstream_stream_url(
    cfg: AppConfig,
    *,
    session: LiveSessionRow,
    sec_uid: str,
    platform: str,
) -> str:
    adapter = get_adapter(platform, cfg)
    room_id = session.room_id
    if not room_id:
        try:
            live_info = adapter.get_live_room(sec_uid=sec_uid)
            room_id = live_info.room_id
            url = live_info.stream_flv_url
            if url:
                return url
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={"error": "live_room_failed", "message": str(exc)},
            ) from exc
        raise HTTPException(status_code=404, detail="room_id not available")

    try:
        return adapter.resolve_stream_url(room_id=room_id, sec_uid=sec_uid)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": "resolve_stream_failed", "message": str(exc)},
        ) from exc


def _upstream_response_headers(response: httpx.Response) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key in ("content-type", "content-length", "accept-ranges"):
        if key in response.headers:
            headers[key] = response.headers[key]
    if "content-type" not in headers:
        headers["content-type"] = "video/x-flv"
    return headers


def iter_flv_proxy(
    cfg: AppConfig,
    conn,
    session_id: str,
) -> tuple[Iterator[bytes], dict[str, str]]:
    """Stream FLV bytes from platform upstream; closes httpx client when exhausted."""
    sessions = LiveSessionRepo(conn)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status not in ("recording", "remuxing"):
        raise HTTPException(status_code=409, detail="session not streaming")

    creator = CreatorRepo(conn).get(session.creator_id)
    if not creator:
        raise HTTPException(status_code=404, detail="creator not found")

    platform = creator.platform
    sec_uid = creator.sec_uid
    client = httpx_client_for_platform(cfg, platform)
    url = resolve_upstream_stream_url(
        cfg,
        session=session,
        sec_uid=sec_uid,
        platform=platform,
    )
    retried = False

    def resolve_again() -> str:
        nonlocal retried, session
        if retried:
            raise HTTPException(status_code=502, detail="upstream retry exhausted")
        retried = True
        fresh = sessions.get(session_id)
        if not fresh:
            raise HTTPException(status_code=404, detail="session not found")
        session = fresh
        return resolve_upstream_stream_url(
            cfg,
            session=session,
            sec_uid=sec_uid,
            platform=platform,
        )

    response = client.send(client.build_request("GET", url), stream=True)
    if response.status_code in (403, 404):
        response.close()
        url = resolve_again()
        response = client.send(client.build_request("GET", url), stream=True)

    if response.status_code >= 400:
        status = response.status_code
        response.close()
        client.close()
        raise HTTPException(
            status_code=502,
            detail={"error": "upstream_error", "status": status},
        )

    out_headers = _upstream_response_headers(response)

    def generate() -> Iterator[bytes]:
        try:
            for chunk in response.iter_bytes():
                if chunk:
                    yield chunk
        finally:
            response.close()
            client.close()

    return generate(), out_headers
