"""Manual recording start/stop for desktop API."""

from __future__ import annotations

from subprocess import Popen
from typing import Any

from media2text.core.config import AppConfig
from media2text.core.errors import (
    AlreadyRecording,
    AuthRequired,
    NotLive,
    NotRecording,
    PlatformChanged,
    RecordingError,
)
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.notify import NotifyService
from media2text.core.platform.registry import get_adapter
from media2text.core.storage.repos import CreatorRepo

_api_processes: dict[str, Popen] = {}


def _build_core(cfg: AppConfig, conn, platform: str) -> LiveRecordingCore:
    adapter = get_adapter(platform, cfg)
    return LiveRecordingCore(
        cfg,
        conn=conn,
        adapter=adapter,
        platform=platform,
        processes=_api_processes,
        notify=NotifyService(cfg),
    )


def start_recording(cfg: AppConfig, conn, creator_id: str) -> dict[str, Any]:
    row = CreatorRepo(conn, cfg=cfg).get(creator_id)
    if not row:
        return {"ok": False, "error": "creator not found", "not_found": True}
    core = _build_core(cfg, conn, row.platform)
    try:
        meta = core.start_recording_for_creator(creator_id)
    except AlreadyRecording as exc:
        return {"ok": False, "already_recording": True, "error": str(exc)}
    except NotLive as exc:
        return {"ok": False, "not_live": True, "error": str(exc)}
    except AuthRequired as exc:
        return {"ok": False, "auth_required": True, "error": str(exc)}
    except PlatformChanged as exc:
        return {"ok": False, "platform_changed": True, "error": str(exc)}
    except RecordingError as exc:
        return {"ok": False, "error": str(exc), "code": exc.code}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "creator_id": creator_id, **meta}


def stop_recording(cfg: AppConfig, conn, creator_id: str) -> dict[str, Any]:
    row = CreatorRepo(conn, cfg=cfg).get(creator_id)
    if not row:
        return {"ok": False, "error": "creator not found", "not_found": True}
    core = _build_core(cfg, conn, row.platform)
    try:
        meta = core.stop_recording_for_creator(creator_id)
    except NotRecording as exc:
        return {"ok": False, "not_recording": True, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if meta is None:
        return {"ok": False, "error": "finalize failed"}
    return {"ok": True, "creator_id": creator_id, **meta}
