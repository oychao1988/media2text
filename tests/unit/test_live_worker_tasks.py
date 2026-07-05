import json
from unittest.mock import MagicMock, patch

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig
from media2text.core.live.monitor_executor import run_monitor_task
from media2text.core.live.recording import LiveRecordingCore
from media2text.core.monitor.watcher import MonitorWatcher
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo, MonitorTaskRepo


def _enqueue_and_claim(conn, *, creator_id: str, task_type: str, payload: dict, priority: int = 1):
    repo = MonitorTaskRepo(conn)
    task_id = repo.enqueue(
        creator_id=creator_id,
        task_type=task_type,
        dedupe_key=f"{task_type}:{payload.get('session_id', creator_id)}",
        priority=priority,
        payload_json=json.dumps(payload),
    )
    assert task_id is not None
    claimed = repo.claim_pending(limit=1, min_priority=priority, max_priority=priority)
    assert len(claimed) == 1
    return claimed[0].id


def test_prepare_live_recording_task(tmp_path, monkeypatch) -> None:
    """LW-01: prepare_live_recording spawns ffmpeg when snapshot has stream."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAprep",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_info = {
        "room_id": "room1",
        "is_live": True,
        "stream_flv_url": "https://example.com/live.flv",
    }
    task_id = _enqueue_and_claim(
        conn,
        creator_id=cid,
        task_type="prepare_live_recording",
        payload={"live_info": live_info},
    )

    mock_proc = MagicMock()
    mock_proc.pid = 4242
    mock_proc.poll.return_value = None
    mock_proc.stderr = None

    watcher = MonitorWatcher(cfg)
    with patch(
        "media2text.core.live.recording.record_stream_copy",
        return_value=mock_proc,
    ):
        result = run_monitor_task(cfg, conn, task_id=task_id, watcher=watcher)

    assert result["ok"] is True
    assert "started" in result
    active = LiveSessionRepo(conn).get_active_for_creator(cid)
    assert active is not None
    assert active.ffmpeg_pid == 4242


def test_reconnect_recording_task(tmp_path, monkeypatch) -> None:
    """LW-03: reconnect_recording calls _reconnect_segment when obs says dead ffmpeg."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAreclw",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAreclw/live/part.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 64)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="99",
        temp_path=str(flv),
        ffmpeg_pid=1111,
    )
    task_id = _enqueue_and_claim(
        conn,
        creator_id=cid,
        task_type="reconnect_recording",
        payload={"session_id": sid},
    )

    watcher = MonitorWatcher(cfg)
    with patch.object(LiveRecordingCore, "_reconnect_segment") as mock_reconnect:
        result = run_monitor_task(cfg, conn, task_id=task_id, watcher=watcher)

    assert result["ok"] is True
    assert result.get("reconnected") is True
    mock_reconnect.assert_called_once()
    args = mock_reconnect.call_args[0]
    assert args[0] == sid


def test_start_streaming_stt_task(tmp_path, monkeypatch) -> None:
    """LW-02: start_streaming_stt builds STT session on active recording."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAstt",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAstt/live/live.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 64)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="55",
        temp_path=str(flv),
        ffmpeg_pid=2222,
        pipeline_mode="streaming",
    )
    task_id = _enqueue_and_claim(
        conn,
        creator_id=cid,
        task_type="start_streaming_stt",
        payload={"session_id": sid},
    )

    mock_stt = MagicMock()
    watcher = MonitorWatcher(cfg)
    watcher._douyin_live._adapter.resolve_stream_url = MagicMock(
        return_value="https://example.com/live.flv"
    )

    with patch.object(
        LiveRecordingCore, "_build_streaming_stt_session", return_value=mock_stt
    ):
        result = run_monitor_task(cfg, conn, task_id=task_id, watcher=watcher)

    assert result["ok"] is True
    assert result.get("started") is True
    mock_stt.start.assert_called_once()


def test_reconnect_streaming_stt_task(tmp_path, monkeypatch) -> None:
    """LW-04: reconnect_streaming_stt wraps STT disconnect/reconnect path."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsttr",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAsttr/live/live.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 64)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="77",
        temp_path=str(flv),
        ffmpeg_pid=3333,
        pipeline_mode="streaming",
    )
    task_id = _enqueue_and_claim(
        conn,
        creator_id=cid,
        task_type="reconnect_streaming_stt",
        payload={"session_id": sid},
    )

    watcher = MonitorWatcher(cfg)
    with patch.object(LiveRecordingCore, "_handle_stt_disconnect") as mock_stt_reconnect:
        result = run_monitor_task(cfg, conn, task_id=task_id, watcher=watcher)

    assert result["ok"] is True
    assert result.get("stt_reconnect_attempted") is True
    mock_stt_reconnect.assert_called_once()


def test_live_worker_dispatch_via_registry(tmp_path, monkeypatch) -> None:
    """Live worker tasks dispatch through SessionStateMachineRegistry (MH-4c)."""
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(enabled=True, reconnect=True),
        ),
    )
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAworker",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    flv = tmp_path / "data/creators/MS4wLjABAAAAworker/live/live.flv"
    flv.parent.mkdir(parents=True, exist_ok=True)
    flv.write_bytes(b"x" * 64)
    sid = LiveSessionRepo(conn).create(
        creator_id=cid,
        room_id="88",
        temp_path=str(flv),
        ffmpeg_pid=4444,
        pipeline_mode="streaming",
    )
    task_id = _enqueue_and_claim(
        conn,
        creator_id=cid,
        task_type="reconnect_streaming_stt",
        payload={"session_id": sid},
    )

    watcher = MonitorWatcher(cfg)
    registry = watcher.ensure_session_registry()
    with patch.object(
        registry,
        "run_reconnect_streaming_stt",
        return_value={"stt_reconnect_attempted": True},
    ) as mock_run:
        result = run_monitor_task(cfg, conn, task_id=task_id, watcher=watcher)

    assert result["ok"] is True
    mock_run.assert_called_once_with(sid)


def test_prepare_not_blocked_by_executor_playwright_lock(tmp_path, monkeypatch) -> None:
    """MH-3: prepare must not acquire executor-level playwright_exclusive."""
    import threading

    from media2text.core.playwright_env import playwright_exclusive

    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    from media2text.core.workspace import open_db

    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAprep2",
        profile_url="https://example.com/u",
        monitor_enabled=True,
    )
    live_info = {
        "room_id": "room2",
        "is_live": True,
        "stream_flv_url": "https://example.com/live2.flv",
    }
    task_id = _enqueue_and_claim(
        conn,
        creator_id=cid,
        task_type="prepare_live_recording",
        payload={"live_info": live_info},
    )

    mock_proc = MagicMock()
    mock_proc.pid = 5252
    mock_proc.poll.return_value = None
    mock_proc.stderr = None

    held = threading.Event()
    release = threading.Event()

    def hold_playwright():
        with playwright_exclusive():
            held.set()
            release.wait(timeout=5.0)

    holder = threading.Thread(target=hold_playwright, daemon=True)
    holder.start()
    assert held.wait(timeout=2.0), "playwright lock should be held by content task"

    watcher = MonitorWatcher(cfg)
    try:
        with patch(
            "media2text.core.live.recording.record_stream_copy",
            return_value=mock_proc,
        ):
            result = run_monitor_task(cfg, conn, task_id=task_id, watcher=watcher)
    finally:
        release.set()
        holder.join(timeout=2.0)

    assert result["ok"] is True
    assert "started" in result
    active = LiveSessionRepo(conn).get_active_for_creator(cid)
    assert active is not None
    assert active.ffmpeg_pid == 5252
