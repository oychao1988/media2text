"""Session finalize orchestration (MH-4d); invoked from SessionStateMachine.run_finalize."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from media2text.core.archive.hook import index_transcript_safe
from media2text.core.cloud.live_upload import upload_hls_session_sidecars
from media2text.core.ffmpeg import (
    concat_to_flv,
    concat_to_mp4,
    remux_to_mp4,
    stop_pid,
    stop_process,
)
from media2text.core.live.hls_recorder import stop_hls_recorder
from media2text.core.live.hls_recorder import finalize_hls_endlist
from media2text.core.live.pipeline_events import stage_event
from media2text.core.live.segment_manifest import SegmentManifestRepo
from media2text.core.live.segment_watcher import (
    enqueue_all_pending_hls_parts,
    get_segment_watcher,
)
from media2text.core.live.transcript_writer import (
    list_segment_checkpoints,
    merge_transcript_checkpoints,
    seal_partial_transcript,
)
from media2text.core.notify import EventKind, NotifyEvent
from media2text.core.notify.labels import creator_label

if TYPE_CHECKING:
    from media2text.core.live.recording import LiveRecordingCore

log = structlog.get_logger()


def finalize_recording(
    core: LiveRecordingCore,
    conn,
    session_id: str,
    temp_path: str | None,
    pid: int,
) -> dict | None:
    use_streaming_finalize = (
        core._use_streaming_pipeline(session_id)
        and session_id not in core._streaming_legacy_finalize
    )
    if use_streaming_finalize:
        return finalize_recording_streaming(core, conn, session_id, temp_path, pid)
    return finalize_recording_legacy(core, conn, session_id, temp_path, pid)


def finalize_recording_streaming(
    core: LiveRecordingCore,
    conn,
    session_id: str,
    temp_path: str | None,
    pid: int,
) -> dict | None:
    if core._use_hls_recording(session_id):
        return finalize_recording_streaming_hls(core, conn, session_id, temp_path, pid)
    proc = core._processes.pop(session_id, None)
    if proc is not None:
        stop_process(proc, timeout=core._cfg.live.ffmpeg_stop_timeout_sec)
    elif pid and core._process_alive(pid):
        stop_pid(pid, timeout=core._cfg.live.ffmpeg_stop_timeout_sec)

    stt = core._stt_sessions.pop(session_id, None)
    core._stream_urls.pop(session_id, None)
    transcript_ok = False
    if not temp_path:
        core._state.update_status(
            session_id, status="failed", error="missing temp_path", ended=True
        )
        core._clear_streaming_session_state(session_id)
        return None

    anchor = core._transcript_anchor(session_id, temp_path)
    segment_paths = [Path(p) for p in core._sessions.list_segment_paths(session_id)]
    current = Path(temp_path)
    flv_sources = segment_paths + [current]
    valid_flvs = [p for p in flv_sources if p.is_file() and p.stat().st_size > 0]
    if not valid_flvs:
        core._state.update_status(
            session_id,
            status="failed",
            error="empty_recording",
            ended=True,
        )
        core._clear_streaming_session_state(session_id)
        log.warning("live_recording_empty", session_id=session_id)
        return None

    output_flv = anchor
    try:
        if len(valid_flvs) > 1:
            merged_tmp = anchor.with_name(f"{anchor.stem}.merged.flv")
            concat_to_flv(
                ffmpeg=core._cfg.live.ffmpeg_path,
                sources=valid_flvs,
                dst=merged_tmp,
            )
            merged_tmp.replace(anchor)
            for path in valid_flvs:
                if path.resolve() != anchor.resolve():
                    path.unlink(missing_ok=True)
        elif valid_flvs[0].resolve() != anchor.resolve():
            valid_flvs[0].replace(anchor)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "streaming_flv_merge_failed",
            session_id=session_id,
            error=str(exc),
        )
        output_flv = valid_flvs[-1]

    try:
        with stage_event(conn, session_id=session_id, stage="streaming_stt"):
            trailing = None
            if stt is not None:
                stt.stop(
                    timeout=core._cfg.live.ffmpeg_stop_timeout_sec,
                    finalize=False,
                )
                trailing = stt.writer.current_segments()
            checkpoints = list_segment_checkpoints(anchor)
            if checkpoints or trailing:
                paths = merge_transcript_checkpoints(
                    anchor,
                    checkpoints,
                    trailing_segments=trailing,
                    engine="deepgram",
                    model=core._cfg.transcribe.deepgram.model,
                )
                transcript_ok = paths is not None
            elif anchor.with_suffix(".transcript.json").is_file():
                transcript_ok = True
            elif seal_partial_transcript(anchor) is not None:
                transcript_ok = True
        core._state.record_pipeline_event(
            session_id=session_id,
            stage="streaming_stt",
            status="completed" if transcript_ok else "failed",
        )
    except Exception as exc:  # noqa: BLE001
        core._state.record_pipeline_event(
            session_id=session_id,
            stage="streaming_stt",
            status="failed",
            detail={"error": str(exc)},
        )
        log.exception("streaming_stt_finalize_failed", session_id=session_id)

    media_path = output_flv
    if core._cfg.live.should_remux_on_complete():
        mp4 = output_flv.with_suffix(".mp4")
        try:
            with stage_event(conn, session_id=session_id, stage="remux"):
                remux_to_mp4(
                    ffmpeg=core._cfg.live.ffmpeg_path,
                    src=output_flv,
                    dst=mp4,
                )
            media_path = mp4
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "streaming_remux_failed",
                session_id=session_id,
                error=str(exc),
            )
    else:
        core._state.record_pipeline_event(
            session_id=session_id,
            stage="remux",
            status="skipped",
        )

    if transcript_ok:
        index_transcript_safe(core._cfg, anchor.with_suffix(".transcript.json"))

    core._clear_streaming_session_state(session_id)
    core._state.update_status(
        session_id,
        status="completed",
        local_path=str(media_path),
        transcribe_status="completed" if transcript_ok else "failed",
        ended=True,
    )
    core._state.clear_pid(session_id)
    log.info(
        "live_recording_completed_streaming",
        session_id=session_id,
        path=str(media_path),
    )

    session = core._sessions.get(session_id)
    if not session:
        return None
    creator = core._creators.get(session.creator_id)
    if not creator:
        return {"session_id": session_id, "path": str(media_path)}

    job_id = core._jobs.ensure_enqueue(
        session_id=session_id,
        creator_id=creator.id,
        mp4_path=str(media_path),
    )
    core._state.refresh_creator_manifest(
        sec_uid=creator.sec_uid,
        workspace=core._ws,
        platform=creator.platform,
    )
    label = creator_label(creator)
    core._notify.emit(
        NotifyEvent(
            kind=EventKind.RECORDING_COMPLETED,
            title=label,
            body=f"直播录制已完成\n{media_path.name}\n{media_path.parent}",
        )
    )
    if transcript_ok:
        core._notify.emit(
            NotifyEvent(
                kind=EventKind.TRANSCRIBE_COMPLETED,
                title=label,
                body=f"直播转录完成（deepgram streaming）\n{media_path.name}",
            )
        )
    return {
        "session_id": session_id,
        "path": str(media_path),
        "creator_id": creator.id,
        "job_id": job_id,
    }


def finalize_recording_streaming_hls(
    core: LiveRecordingCore,
    conn,
    session_id: str,
    temp_path: str | None,
    pid: int,
) -> dict | None:
    proc = core._processes.pop(session_id, None)
    if proc is not None:
        stop_hls_recorder(proc, timeout=core._cfg.live.ffmpeg_stop_timeout_sec)
    elif pid and core._process_alive(pid):
        stop_pid(pid, timeout=core._cfg.live.ffmpeg_stop_timeout_sec)

    stt = core._stt_sessions.pop(session_id, None)
    core._stream_urls.pop(session_id, None)

    session_dir = core._resolve_session_dir(session_id)
    if session_dir is None and temp_path:
        session_dir = Path(temp_path).parent

    if session_dir is None:
        core._state.update_status(
            session_id, status="failed", error="missing session_dir", ended=True
        )
        core._clear_streaming_session_state(session_id)
        return None

    seg_watcher = get_segment_watcher()
    if seg_watcher is not None:
        seg_watcher.force_close_session(conn, session_id, session_dir)
    else:
        core._close_hls_part_if_any(session_id, session_dir)
        enqueue_all_pending_hls_parts(
            conn, session_id, session_dir, cfg=core._cfg
        )
    finalize_hls_endlist(session_dir)
    manifest_repo = SegmentManifestRepo(conn)
    manifest_repo.export_json(session_id, session_dir=session_dir)

    anchor = core._transcript_anchor(session_id, temp_path)
    transcript_ok = False
    try:
        with stage_event(conn, session_id=session_id, stage="streaming_stt"):
            trailing = None
            if stt is not None:
                stt.stop(
                    timeout=core._cfg.live.ffmpeg_stop_timeout_sec,
                    finalize=False,
                )
                trailing = stt.writer.current_segments()
            checkpoints = list_segment_checkpoints(anchor)
            if checkpoints or trailing:
                paths = merge_transcript_checkpoints(
                    anchor,
                    checkpoints,
                    trailing_segments=trailing,
                    engine="deepgram",
                    model=core._cfg.transcribe.deepgram.model,
                )
                transcript_ok = paths is not None
            elif anchor.with_suffix(".transcript.json").is_file():
                transcript_ok = True
            elif seal_partial_transcript(anchor) is not None:
                transcript_ok = True
        core._state.record_pipeline_event(
            session_id=session_id,
            stage="streaming_stt",
            status="completed" if transcript_ok else "failed",
        )
    except Exception as exc:  # noqa: BLE001
        core._state.record_pipeline_event(
            session_id=session_id,
            stage="streaming_stt",
            status="failed",
            detail={"error": str(exc)},
        )
        log.exception("streaming_stt_finalize_failed", session_id=session_id)

    core._state.record_pipeline_event(
        session_id=session_id,
        stage="remux",
        status="skipped",
        detail={"reason": "hls_segments"},
    )

    if transcript_ok:
        index_transcript_safe(core._cfg, anchor.with_suffix(".transcript.json"))

    session = core._sessions.get(session_id)
    creator = core._creators.get(session.creator_id) if session else None
    if creator and core._cfg.aliyundrive.enabled:
        upload_hls_session_sidecars(
            core._cfg,
            conn,
            session_id=session_id,
            session_dir=session_dir,
            anchor=anchor,
            creator=creator,
            notify=core._notify,
        )

    media_path = session_dir / "master.m3u8"
    core._clear_streaming_session_state(session_id)
    core._state.update_status(
        session_id,
        status="completed",
        local_path=str(session_dir),
        transcribe_status="completed" if transcript_ok else "failed",
        ended=True,
    )
    core._state.clear_pid(session_id)
    log.info(
        "live_recording_completed_streaming_hls",
        session_id=session_id,
        path=str(media_path),
    )

    if not session:
        return None
    if not creator:
        return {"session_id": session_id, "path": str(media_path)}

    job_id = None
    if core._cfg.summarize.enabled and core._cfg.summarize.on_transcribe_complete:
        job_id = core._jobs.ensure_enqueue(
            session_id=session_id,
            creator_id=creator.id,
            mp4_path=str(media_path),
        )
    core._state.refresh_creator_manifest(
        sec_uid=creator.sec_uid,
        workspace=core._ws,
        platform=creator.platform,
    )
    label = creator_label(creator)
    core._notify.emit(
        NotifyEvent(
            kind=EventKind.RECORDING_COMPLETED,
            title=label,
            body=f"直播录制已完成（HLS）\n{session_dir.name}\n{session_dir}",
        )
    )
    if transcript_ok:
        core._notify.emit(
            NotifyEvent(
                kind=EventKind.TRANSCRIBE_COMPLETED,
                title=label,
                body=f"直播转录完成（deepgram streaming）\n{session_dir.name}",
            )
        )
    return {
        "session_id": session_id,
        "path": str(media_path),
        "creator_id": creator.id,
        "job_id": job_id,
    }


def _session_pipeline_mode(core: LiveRecordingCore, session_id: str) -> str:
    row = core._sessions.get(session_id)
    if row and row.pipeline_mode:
        return row.pipeline_mode.strip().lower()
    return core._cfg.live.snapshot_pipeline_mode()


def finalize_recording_legacy(
    core: LiveRecordingCore,
    conn,
    session_id: str,
    temp_path: str | None,
    pid: int,
) -> dict | None:
    if _session_pipeline_mode(core, session_id) == "legacy":
        log.warning(
            "live_pipeline_deprecated",
            mode="legacy",
            hint="use streaming+hls; see config.example.yaml",
        )
    proc = core._processes.pop(session_id, None)
    if proc is not None:
        stop_process(proc, timeout=core._cfg.live.ffmpeg_stop_timeout_sec)
    elif pid and core._process_alive(pid):
        stop_pid(pid, timeout=core._cfg.live.ffmpeg_stop_timeout_sec)

    stt = core._stt_sessions.pop(session_id, None)
    if stt is not None:
        try:
            stt.stop(timeout=5)
        except Exception:  # noqa: BLE001
            pass
    core._streaming_legacy_finalize.discard(session_id)
    core._stream_urls.pop(session_id, None)

    if not temp_path:
        core._state.update_status(
            session_id, status="failed", error="missing temp_path", ended=True
        )
        return None

    segments = [Path(p) for p in core._sessions.list_segment_paths(session_id)]
    current = Path(temp_path)
    sources = segments + [current]
    valid_sources = [p for p in sources if p.is_file() and p.stat().st_size > 0]
    if not valid_sources:
        core._state.update_status(
            session_id,
            status="failed",
            error="empty_recording",
            ended=True,
        )
        log.warning("live_recording_empty", session_id=session_id)
        return None

    mp4 = current.with_suffix(".mp4")
    if len(valid_sources) == 1 and valid_sources[0] == current:
        mp4 = current.with_suffix(".mp4")

    core._state.update_status(session_id, status="remuxing")
    try:
        with stage_event(conn, session_id=session_id, stage="remux"):
            if len(valid_sources) == 1:
                remux_to_mp4(
                    ffmpeg=core._cfg.live.ffmpeg_path,
                    src=valid_sources[0],
                    dst=mp4,
                )
                if valid_sources[0] != mp4:
                    valid_sources[0].unlink(missing_ok=True)
            else:
                concat_to_mp4(
                    ffmpeg=core._cfg.live.ffmpeg_path,
                    sources=valid_sources,
                    dst=mp4,
                )
                for seg in valid_sources:
                    if seg.suffix.lower() in (".flv", ".ts", ".mkv"):
                        seg.unlink(missing_ok=True)
        core._state.update_status(
            session_id,
            status="completed",
            local_path=str(mp4),
            ended=True,
        )
        core._state.clear_pid(session_id)
        log.info("live_recording_completed", session_id=session_id, path=str(mp4))
    except Exception as exc:  # noqa: BLE001
        seg_list = ", ".join(str(p) for p in valid_sources)
        core._state.update_status(
            session_id,
            status="failed",
            error=f"{exc}; segments={seg_list}",
            ended=True,
        )
        log.exception("live_recording_failed", session_id=session_id)
        return None

    session = core._sessions.get(session_id)
    if not session:
        return None
    creator = core._creators.get(session.creator_id)
    if not creator:
        return {"session_id": session_id, "path": str(mp4)}

    job_id = core._jobs.ensure_enqueue(
        session_id=session_id,
        creator_id=creator.id,
        mp4_path=str(mp4),
    )
    core._state.refresh_creator_manifest(
        sec_uid=creator.sec_uid,
        workspace=core._ws,
        platform=creator.platform,
    )
    label = creator_label(creator)
    core._notify.emit(
        NotifyEvent(
            kind=EventKind.RECORDING_COMPLETED,
            title=label,
            body=f"直播录制已完成\n{mp4.name}\n{mp4.parent}",
        )
    )
    return {
        "session_id": session_id,
        "path": str(mp4),
        "creator_id": creator.id,
        "job_id": job_id,
    }
