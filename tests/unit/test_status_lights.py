import pytest

from media2text.core.desktop.status_lights import compute_status_light
from media2text.core.storage.models import CreatorLiveSnapshotRow, LiveSessionRow

pytestmark = pytest.mark.desktop


def _session(**kwargs) -> LiveSessionRow:
    base = dict(
        id="s1",
        creator_id="c1",
        room_id=None,
        ffmpeg_pid=None,
        started_at="2026-01-01T00:00:00Z",
        ended_at=None,
        local_path=None,
        temp_path=None,
        status="recording",
        error=None,
    )
    base.update(kwargs)
    return LiveSessionRow(**base)


def test_green_when_recording() -> None:
    import os

    pid = os.getpid()
    out = compute_status_light(
        active_session=_session(ffmpeg_pid=pid, status="recording"),
        snapshot=CreatorLiveSnapshotRow("c1", 1, "r1", "t", "2026-01-01T00:00:00Z"),
    )
    assert out["status_light"] == "green"
    assert out["is_live"] is True


def test_red_when_live_not_recording() -> None:
    out = compute_status_light(
        active_session=None,
        snapshot=CreatorLiveSnapshotRow("c1", 1, "r1", "t", "2026-01-01T00:00:00Z"),
    )
    assert out["status_light"] == "red"


def test_yellow_when_offline_since() -> None:
    out = compute_status_light(
        active_session=_session(offline_since_at="2026-01-01T01:00:00Z", ffmpeg_pid=None),
        snapshot=CreatorLiveSnapshotRow("c1", 1, "r1", "t", "2026-01-01T00:00:00Z"),
    )
    assert out["status_light"] == "yellow"


def test_yellow_when_active_session_without_ffmpeg() -> None:
    out = compute_status_light(
        active_session=_session(ffmpeg_pid=None, status="recording"),
        snapshot=CreatorLiveSnapshotRow("c1", 0, None, None, "2026-01-01T00:00:00Z"),
    )
    assert out["status_light"] == "yellow"


def test_gray_when_offline() -> None:
    out = compute_status_light(
        active_session=None,
        snapshot=CreatorLiveSnapshotRow("c1", 0, None, None, "2026-01-01T00:00:00Z"),
    )
    assert out["status_light"] == "gray"
    assert out["is_live"] is False
