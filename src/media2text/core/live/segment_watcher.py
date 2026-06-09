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
from media2text.core.workspace import open_db

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
        repo = SegmentManifestRepo(conn)
        jobs = SegmentProcessJobRepo(conn)
        parts_dir = session_dir / "parts"
        if not parts_dir.is_dir():
            return
        for path in sorted(parts_dir.glob("seg-*.m4s")):
            m = _PART_RE.search(path.name)
            if not m:
                continue
            idx = int(m.group(1))
            row = repo.get_part(session_id, idx)
            if row and row.state not in ("recording", "closed"):
                continue
            size = path.stat().st_size if path.is_file() else None
            if row is None:
                repo.upsert_part(
                    session_id=session_id,
                    part_index=idx,
                    rel_path=part_rel_path(idx),
                    state="recording",
                )
            mark_closed_with_duration(
                repo, session_id, idx, session_dir, bytes=size
            )
            jobs.enqueue(session_id=session_id, part_index=idx)

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
        repo = SegmentManifestRepo(conn)
        jobs = SegmentProcessJobRepo(conn)
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
            if row is None:
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
        while not self._stop.is_set():
            conn = open_db(self._cfg)
            try:
                self.tick_once(conn)
            except Exception:
                log.exception("segment_watcher_tick_failed")
            finally:
                conn.close()
            self._stop.wait(timeout=interval)


_watcher: SegmentWatcher | None = None


def set_segment_watcher(watcher: SegmentWatcher | None) -> None:
    global _watcher
    _watcher = watcher


def get_segment_watcher() -> SegmentWatcher | None:
    return _watcher
