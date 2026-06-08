"""Unit tests for pipeline_phase projection (R3a)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from media2text.core.config import AppConfig
from media2text.core.live.pipeline_phase import derive_pipeline_phase
from media2text.core.storage.models import LiveSessionRow, MonitorTaskRow, PostProcessJobRow

_NOW = datetime.now(timezone.utc).isoformat()
_OLD = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()


def _session(**kwargs) -> LiveSessionRow:
    base = dict(
        id="sess-1",
        creator_id="c1",
        room_id="r1",
        ffmpeg_pid=12345,
        started_at=_NOW,
        ended_at=None,
        local_path=None,
        temp_path="/tmp/x.flv",
        status="recording",
        error=None,
        transcribe_status=None,
        offline_since_at=None,
        pipeline_mode="streaming",
        reconnect_attempts=0,
    )
    base.update(kwargs)
    return LiveSessionRow(**base)


def _post_job(**kwargs) -> PostProcessJobRow:
    base = dict(
        id="job-1",
        session_id="sess-1",
        creator_id="c1",
        mp4_path="/tmp/x.mp4",
        status="pending",
        stage=None,
        error=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    base.update(kwargs)
    return PostProcessJobRow(**base)


def _monitor_task(**kwargs) -> MonitorTaskRow:
    base = dict(
        id="task-1",
        creator_id="c1",
        task_type="finalize",
        payload_json=json.dumps({"session_id": "sess-1"}),
        priority=0,
        status="pending",
        dedupe_key="finalize:sess-1",
        created_at=_NOW,
        started_at=None,
        finished_at=None,
        error=None,
        attempt_count=0,
    )
    base.update(kwargs)
    return MonitorTaskRow(**base)


_CFG = AppConfig.model_validate(
    {
        "live": {
            "offline_confirm_sec": 45,
            "pipeline_mode": "streaming",
            "streaming_stt": {"enabled": True},
        }
    }
)


@pytest.mark.parametrize(
    "session,is_live,post_jobs,monitor_tasks,expected",
    [
        (None, False, [], [], "offline"),
        (None, True, [], [], "live_unrecorded"),
        (
            _session(status="recording", ffmpeg_pid=12345, transcribe_status="streaming"),
            True,
            [],
            [],
            "recording",
        ),
        (
            _session(status="recording", transcribe_status=None, pipeline_mode="streaming"),
            True,
            [],
            [],
            "recording_stt_pending",
        ),
        (
            _session(status="recording", offline_since_at=_NOW),
            True,
            [],
            [],
            "offline_pending",
        ),
        (
            _session(status="recording", offline_since_at=_OLD),
            True,
            [],
            [],
            "finalizing",
        ),
        (
            _session(status="remuxing", ffmpeg_pid=None),
            False,
            [],
            [],
            "finalizing",
        ),
        (
            _session(status="recording"),
            False,
            [_post_job()],
            [],
            "post_processing",
        ),
        (
            _session(status="completed", ended_at=_NOW),
            False,
            [],
            [],
            "completed",
        ),
        (
            _session(status="failed", error="boom"),
            False,
            [],
            [],
            "failed",
        ),
        (
            None,
            False,
            [_post_job(status="failed")],
            [],
            "failed",
        ),
        (
            _session(status="recording", offline_since_at=_NOW),
            True,
            [],
            [_monitor_task(task_type="finalize", status="pending")],
            "finalizing",
        ),
        (
            _session(status="recording", transcribe_status=None),
            True,
            [],
            [
                _monitor_task(
                    task_type="start_streaming_stt",
                    dedupe_key="stt:sess-1",
                    payload_json=json.dumps({"session_id": "sess-1"}),
                )
            ],
            "recording_stt_pending",
        ),
    ],
)
def test_pipeline_phase_derivation(
    session,
    is_live,
    post_jobs,
    monitor_tasks,
    expected,
) -> None:
    assert (
        derive_pipeline_phase(
            session,
            is_live=is_live,
            post_jobs=post_jobs,
            monitor_tasks=monitor_tasks,
            cfg=_CFG,
        )
        == expected
    )


def test_post_processing_without_active_session() -> None:
    phase = derive_pipeline_phase(
        None,
        is_live=False,
        post_jobs=[_post_job(status="running")],
        cfg=_CFG,
    )
    assert phase == "post_processing"
