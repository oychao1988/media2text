from unittest.mock import MagicMock, patch

import pytest
from starlette.responses import StreamingResponse

from media2text.api.services.cloud_byte_proxy import stream_cloud_file

pytestmark = pytest.mark.desktop


def _mock_upstream(*, status_code: int, headers: dict, chunks: list[bytes]):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers
    mock_resp.iter_bytes.return_value = chunks
    mock_upstream = MagicMock()
    mock_upstream.__enter__ = MagicMock(return_value=mock_resp)
    mock_upstream.__exit__ = MagicMock(return_value=False)
    return mock_upstream


def test_stream_cloud_file_forwards_range_header():
    mock_client = MagicMock()
    mock_client.get_download_url.return_value = "https://cdn.example/file"
    upstream = _mock_upstream(
        status_code=206,
        headers={
            "content-type": "video/mp4",
            "content-length": "100",
            "content-range": "bytes 0-99/100",
        },
        chunks=[b"chunk"],
    )
    with patch(
        "media2text.api.services.cloud_byte_proxy.httpx.stream",
        return_value=upstream,
    ) as mock_stream:
        resp = stream_cloud_file(
            mock_client,
            "fid-1",
            range_header="bytes=0-99",
        )
    assert isinstance(resp, StreamingResponse)
    mock_stream.assert_called_once()
    call_kwargs = mock_stream.call_args.kwargs
    assert call_kwargs["headers"]["Range"] == "bytes=0-99"
    assert resp.status_code == 206


def test_stream_cloud_file_without_range():
    mock_client = MagicMock()
    mock_client.get_download_url.return_value = "https://cdn.example/file"
    upstream = _mock_upstream(
        status_code=200,
        headers={"content-type": "video/mp4", "content-length": "100"},
        chunks=[b"chunk"],
    )
    with patch(
        "media2text.api.services.cloud_byte_proxy.httpx.stream",
        return_value=upstream,
    ) as mock_stream:
        resp = stream_cloud_file(mock_client, "fid-1")
    assert resp.status_code == 200
    assert "Range" not in mock_stream.call_args.kwargs["headers"]
