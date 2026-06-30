from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from media2text.core.cloud.aliyundrive import (
    V2_RECYCLEBIN_LIST,
    V3_FILE_DELETE,
    AliyunDriveClient,
)
from media2text.core.cloud.cleanup import is_video_cleanup_filename


def test_is_video_cleanup_filename() -> None:
    assert is_video_cleanup_filename("live.mp4")
    assert is_video_cleanup_filename("seg-00001.m4s")
    assert is_video_cleanup_filename("init.mp4")
    assert not is_video_cleanup_filename("a.transcript.json")
    assert not is_video_cleanup_filename("master.m3u8")


@pytest.fixture
def client() -> AliyunDriveClient:
    c = AliyunDriveClient(token={"access_token": "t", "default_drive_id": "drive-1"})
    c.post = MagicMock(return_value={"ok": True, "status_code": 204})
    return c


def test_delete_file_permanently(client: AliyunDriveClient) -> None:
    client.delete_file_permanently("file-abc")
    client.post.assert_called_once_with(
        V3_FILE_DELETE,
        {"drive_id": "drive-1", "file_id": "file-abc"},
    )


def test_list_recycle_bin_paginates(client: AliyunDriveClient) -> None:
    client.post = MagicMock(
        side_effect=[
            {"items": [{"file_id": "a", "name": "one.mp4"}], "next_marker": "m1"},
            {"items": [{"file_id": "b", "name": "two.mp4"}]},
        ]
    )
    items = client.list_recycle_bin(limit=1)
    assert len(items) == 2
    assert client.post.call_args_list[0][0][0] == V2_RECYCLEBIN_LIST
