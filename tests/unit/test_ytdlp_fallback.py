import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from media2text.core.platform.douyin.ytdlp_fallback import (
    download_via_ytdlp,
    export_netscape_cookies,
)


def test_export_netscape_cookies(tmp_path: Path) -> None:
    session = tmp_path / "douyin.json"
    session.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "ttwid",
                        "value": "abc",
                        "domain": ".douyin.com",
                        "path": "/",
                        "secure": True,
                        "expires": 9999999999,
                    }
                ]
            }
        )
    )
    out = tmp_path / "cookies.txt"
    export_netscape_cookies(session, out)
    text = out.read_text()
    assert "ttwid" in text
    assert ".douyin.com" in text


@patch("media2text.core.platform.douyin.ytdlp_fallback.subprocess.run")
@patch("media2text.core.platform.douyin.ytdlp_fallback.ytdlp_available", return_value=True)
def test_download_via_ytdlp_success(mock_avail, mock_run, tmp_path: Path) -> None:
    session = tmp_path / "douyin.json"
    session.write_text(json.dumps({"cookies": []}))
    dest = tmp_path / "videos" / "7123456789012345678.mp4"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"mp4")

    mock_run.return_value = MagicMock(returncode=0)

    download_via_ytdlp(
        aweme_id="7123456789012345678",
        dest=dest,
        session_file=session,
    )
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "yt-dlp"
    assert "7123456789012345678" in args[-1]


@patch("media2text.core.platform.douyin.download.ytdlp_available", return_value=False)
@patch("media2text.core.platform.douyin.download.httpx.Client")
def test_download_primary_only_when_no_ytdlp(mock_client_cls, mock_ytdlp, tmp_path, monkeypatch) -> None:
    from media2text.core.platform.douyin.download import _download_one
    from media2text.core.platform.douyin.live import FIXTURE_ROOT

    monkeypatch.chdir(tmp_path)
    adapter = __import__(
        "media2text.core.platform.douyin.adapter", fromlist=["DouyinAdapterV1"]
    ).DouyinAdapterV1(None, fixture_root=FIXTURE_ROOT)

    dest = tmp_path / "out.mp4"
    aweme_id, ok, result = _download_one(
        adapter=adapter,
        aweme_id="7123456789012345678",
        dest=dest,
        session_file=None,
    )
    assert aweme_id == "7123456789012345678"
    assert ok is True
    assert dest.is_file()
    mock_client_cls.assert_called()
