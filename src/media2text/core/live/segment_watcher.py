"""SegmentWatcher (D11): detect closed HLS parts and enqueue Tier-1 jobs."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from media2text.core.config import AppConfig
from media2text.core.live.hls_recorder import mark_closed_with_duration, part_rel_path
from media2text.core.live.segment_manifest import SegmentManifestRepo, SegmentProcessJobRepo
from media2text.core.storage.repos import LiveSessionRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, get_write_gateway

log = structlog.get_logger()

_PART_RE = re.compile(r"seg-(\d+)\.m4s$")


@dataclass
class _PartObservation:
    mtime_ns: int
    size: int
    stable_since: float | None = None


class SegmentWatcher:
    """Poll HLS session dirs for stable .m4s segments; enqueue segment_process jobs."""

    def __init__(self, cfg: AppConfig, *, stop: threading.Event) -> None:
        self._cfg = cfg
        self._stop = stop
        self._thread: threading.Thread | None = None
        self._observations: dict[tuple[str, int], _PartObservation] = {}
        self._stopped_sessions: set[str] = set()

    def start(self) -> None:
        if not self._cfg.live.segment_pipeline.enabled:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="segment-watcher",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def stop_session(self, session_id: str) -> None:
        self._stopped_sessions.add(session_id)
        keys = [k for k in self._observations if k[0] == session_id]
        for key in keys:
            self._observations.pop(key, None)

    def force_close_session(self, conn, session_id: str, session_dir: Path) -> None:
        """Finalize: force-close open parts and enqueue upload jobs."""
        self.stop_session(session_id)
        enqueue_all_pending_hls_parts(conn, session_id, session_dir, cfg=self._cfg)

    def tick_once(self, conn) -> None:
        if not self._cfg.live.segment_pipeline.enabled:
            return
        sp = self._cfg.live.segment_pipeline
        stable_sec = sp.stable_mtime_sec
        sessions = LiveSessionRepo(conn)
        for row in sessions.list_active():
            if row.id in self._stopped_sessions:
                continue
            if not row.session_dir:
                continue
            session_dir = Path(row.session_dir)
            if not session_dir.is_dir():
                continue
            self._poll_session(
                conn,
                session_id=row.id,
                session_dir=session_dir,
                stable_sec=stable_sec,
            )

    def _poll_session(
        self,
        conn,
        *,
        session_id: str,
        session_dir: Path,
        stable_sec: float,
    ) -> None:
        parts_dir = session_dir / "parts"
        if not parts_dir.is_dir():
            return
        repo = SegmentManifestRepo(conn, cfg=self._cfg)
        jobs = SegmentProcessJobRepo(conn, cfg=self._cfg)
        now = time.monotonic()
        growing_index: int | None = None
        candidates: list[tuple[int, Path]] = []

        for path in sorted(parts_dir.glob("seg-*.m4s")):
            m = _PART_RE.search(path.name)
            if not m:
                continue
            idx = int(m.group(1))
            if not path.is_file() or path.stat().st_size == 0:
                continue
            candidates.append((idx, path))

        if not candidates:
            return

        for idx, path in candidates:
            st = path.stat()
            key = (session_id, idx)
            prev = self._observations.get(key)
            if prev is None or prev.mtime_ns != st.st_mtime_ns or prev.size != st.st_size:
                self._observations[key] = _PartObservation(
                    mtime_ns=st.st_mtime_ns,
                    size=st.st_size,
                    stable_since=now,
                )
                growing_index = idx
                continue
            obs = self._observations[key]
            if obs.stable_since is None:
                obs.stable_since = now
            if (now - obs.stable_since) < stable_sec:
                growing_index = idx
                continue

        for idx, path in candidates:
            if growing_index is not None and idx == growing_index:
                row = repo.get_part(session_id, idx)
                if row is None or row.state == "recording":
                    continue
            key = (session_id, idx)
            obs = self._observations.get(key)
            if obs is None or obs.stable_since is None:
                continue
            if (now - obs.stable_since) < stable_sec:
                continue

            row = repo.get_part(session_id, idx)
            if row and row.state not in ("recording",):
                continue

            size = path.stat().st_size
            current = repo.get_part(session_id, idx)
            if current is None:
                repo.upsert_part(
                    session_id=session_id,
                    part_index=idx,
                    rel_path=part_rel_path(idx),
                    state="recording",
                )
            mark_closed_with_duration(
                repo, session_id, idx, session_dir, bytes=size
            )
            job_id = jobs.enqueue(session_id=session_id, part_index=idx)
            if job_id:
                log.info(
                    "segment_watcher_enqueued",
                    session_id=session_id,
                    part_index=idx,
                    job_id=job_id,
                )

    def _run(self) -> None:
        interval = self._cfg.live.segment_pipeline.watch_interval_sec
        ensure_write_gateway_started(self._cfg)
        gw = get_write_gateway(self._cfg)
        while not self._stop.is_set():
            try:
                gw.read(self.tick_once)
            except Exception:
                log.exception("segment_watcher_tick_failed")
            self._stop.wait(timeout=interval)


_watcher: SegmentWatcher | None = None


def set_segment_watcher(watcher: SegmentWatcher | None) -> None:
    global _watcher
    _watcher = watcher


def get_segment_watcher() -> SegmentWatcher | None:
    return _watcher


def enqueue_closed_hls_part(
    conn,
    *,
    session_id: str,
    session_dir: Path,
    part_index: int,
    cfg: AppConfig | None = None,
) -> str | None:
    """Mark a part closed (if needed) and enqueue Tier-1 upload when the file exists."""
    repo = SegmentManifestRepo(conn, cfg=cfg)
    jobs = SegmentProcessJobRepo(conn, cfg=cfg)
    rel = part_rel_path(part_index)
    part_path = session_dir / rel
    if not part_path.is_file() or part_path.stat().st_size == 0:
        return None
    row = repo.get_part(session_id, part_index)
    if row is None:
        repo.upsert_part(
            session_id=session_id,
            part_index=part_index,
            rel_path=rel,
            state="recording",
        )
    elif row.state in ("uploaded", "local_deleted"):
        return None

    mark_closed_with_duration(
        repo, session_id, part_index, session_dir, bytes=part_path.stat().st_size
    )
    job_id = jobs.enqueue(session_id=session_id, part_index=part_index)
    if job_id:
        log.info(
            "segment_part_enqueued",
            session_id=session_id,
            part_index=part_index,
            job_id=job_id,
        )
    return job_id


def enqueue_all_pending_hls_parts(
    conn,
    session_id: str,
    session_dir: Path,
    *,
    cfg: AppConfig | None = None,
) -> int:
    """Close + enqueue every on-disk .m4s that is not yet uploaded."""
    parts_dir = session_dir / "parts"
    if not parts_dir.is_dir():
        return 0
    enqueued = 0
    for path in sorted(parts_dir.glob("seg-*.m4s")):
        m = _PART_RE.search(path.name)
        if not m or not path.is_file() or path.stat().st_size == 0:
            continue
        idx = int(m.group(1))
        if enqueue_closed_hls_part(
            conn,
            session_id=session_id,
            session_dir=session_dir,
            part_index=idx,
            cfg=cfg,
        ):
            enqueued += 1
    return enqueued


def hls_parts_pending_upload(conn, session_id: str, *, session_dir: Path | None = None) -> bool:
    """True when manifest or disk still has segments not uploaded/deleted."""
    repo = SegmentManifestRepo(conn)
    parts = repo.list_parts(session_id)
    if parts:
        if any(p.state in ("recording", "closed") for p in parts):
            return True
    if session_dir is not None:
        parts_dir = session_dir / "parts"
        if parts_dir.is_dir():
            for path in parts_dir.glob("seg-*.m4s"):
                if path.is_file() and path.stat().st_size > 0:
                    return True
    return False
