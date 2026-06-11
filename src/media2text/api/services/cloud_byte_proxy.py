"""Stream Aliyun Drive file bytes through API (Range-aware)."""

from __future__ import annotations

import httpx
from starlette.responses import StreamingResponse


def stream_cloud_file(
    client,
    file_id: str,
    *,
    range_header: str | None = None,
    media_type: str = "video/mp4",
) -> StreamingResponse:
    url = client.get_download_url(file_id)
    headers: dict[str, str] = {}
    if range_header:
        headers["Range"] = range_header
    upstream = httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60.0)
    resp = upstream.__enter__()
    if resp.status_code not in (200, 206):
        upstream.__exit__(None, None, None)
        raise RuntimeError(f"cloud upstream status {resp.status_code}")

    out_headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Type": resp.headers.get("content-type", media_type),
    }
    if "content-range" in resp.headers:
        out_headers["Content-Range"] = resp.headers["content-range"]
    if "content-length" in resp.headers:
        out_headers["Content-Length"] = resp.headers["content-length"]

    def _iter():
        try:
            for chunk in resp.iter_bytes():
                yield chunk
        finally:
            upstream.__exit__(None, None, None)

    status = 206 if resp.status_code == 206 else 200
    return StreamingResponse(
        _iter(),
        status_code=status,
        headers=out_headers,
        media_type=out_headers["Content-Type"],
    )
