from __future__ import annotations

import time

import structlog

from media2text.core.config import AppConfig
from media2text.core.errors import AuthRequired
from media2text.core.notify import EventKind, NotifyEvent, NotifyService
from media2text.core.notify.labels import creator_label
from media2text.core.pipeline.runner import run_pipeline
from media2text.core.transcribe.factory import transcribe_engine_available
from media2text.core.platform.douyin.live import LiveWatcher
from media2text.core.process_lock import LockError, workspace_lock
from media2text.core.storage.repos import CreatorRepo
from media2text.core.workspace import open_db

log = structlog.get_logger()


class MonitorWatcher:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._ws = cfg.ensure_workspace()
        self._conn = open_db(cfg)
        self._creators = CreatorRepo(self._conn)
        self._live = LiveWatcher(cfg)
        self._notify = NotifyService(cfg)

    def run_once(self, *, creator_id: str | None = None) -> dict:
        live_result = self._live.run_once(creator_id=creator_id)
        vod_result = self._run_vod_tick(creator_id=creator_id)
        errors = list(vod_result.get("errors") or [])
        return {
            "live": live_result,
            "vod": vod_result,
            "errors": errors,
            "auth_required": vod_result.get("auth_required", False),
        }

    def run_daemon(self, *, creator_id: str | None = None) -> None:
        lock = self._ws / ".monitor-watch.lock"
        try:
            with workspace_lock(lock):
                last_vod = 0.0
                log.info(
                    "monitor_watch_daemon_started",
                    live_poll=self._cfg.monitor.live_poll_interval_sec,
                    vod_poll=self._cfg.monitor.vod_poll_interval_sec,
                )
                while True:
                    self._live.run_once(creator_id=creator_id)
                    now = time.time()
                    if now - last_vod >= self._cfg.monitor.vod_poll_interval_sec:
                        self._run_vod_tick(creator_id=creator_id)
                        last_vod = now
                    time.sleep(self._cfg.monitor.live_poll_interval_sec)
        except LockError:
            log.error("monitor_watch_lock_held")
            raise

    def _run_vod_tick(self, *, creator_id: str | None = None) -> dict:
        targets = self._creators.list_monitored()
        if creator_id:
            row = self._creators.get(creator_id)
            targets = [row] if row and row.monitor_enabled else []
        max_n = self._cfg.monitor.max_creators_per_vod_tick
        if max_n > 0:
            targets = targets[:max_n]

        results: list[dict] = []
        errors: list[dict] = []
        auth_required = False
        available, skip_reason = transcribe_engine_available(self._cfg)
        transcribe_skipped = not available

        for creator in targets:
            try:
                outcome = run_pipeline(self._cfg, creator_id=creator.id)
            except AuthRequired as exc:
                auth_required = True
                err = {"creator_id": creator.id, "error": str(exc), "auth_required": True}
                errors.append(err)
                results.append({"creator_id": creator.id, "ok": False, **err})
                continue
            except Exception as exc:  # noqa: BLE001
                err = {"creator_id": creator.id, "error": str(exc)}
                errors.append(err)
                results.append({"creator_id": creator.id, "ok": False, **err})
                continue

            if outcome.get("auth_required"):
                auth_required = True
            if outcome.get("errors"):
                for item in outcome["errors"]:
                    errors.append({"creator_id": creator.id, **item})
            self._emit_vod_notifications(creator, outcome)
            entry = {
                "creator_id": creator.id,
                "ok": outcome.get("ok", False),
                "sync": outcome.get("sync"),
                "download": outcome.get("download"),
                "transcribed": outcome.get("transcribed", 0),
            }
            if transcribe_skipped:
                entry["transcribe_skipped"] = True
                if skip_reason:
                    entry["transcribe_skip_reason"] = skip_reason
            results.append(entry)

        payload: dict = {
            "creators": len(targets),
            "results": results,
            "errors": errors,
            "auth_required": auth_required,
            "transcribe_skipped": transcribe_skipped,
        }
        if transcribe_skipped and skip_reason:
            payload["transcribe_skip_reason"] = skip_reason
        return payload

    def _emit_vod_notifications(self, creator, outcome: dict) -> None:
        label = creator_label(creator)
        sync = outcome.get("sync") or {}
        new_count = int(sync.get("new_count") or 0)
        if new_count > 0:
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.NEW_AWEME,
                    title=label,
                    body=f"同步到 {new_count} 个新作品",
                )
            )
        transcribed = int(outcome.get("transcribed") or 0)
        if transcribed > 0:
            self._notify.emit(
                NotifyEvent(
                    kind=EventKind.TRANSCRIBE_COMPLETED,
                    title=label,
                    body=f"作品转录完成 {transcribed} 条",
                )
            )
