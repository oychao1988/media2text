import pytest

pytestmark = pytest.mark.desktop


def test_media_full_file(api_client, workspace) -> None:
    rel = "creators/sec1/live/test.mp4"
    path = workspace / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x00\x01\x02\x03\x04")

    r = api_client.get(f"/api/media?path={rel}")
    assert r.status_code == 200
    assert r.content == b"\x00\x01\x02\x03\x04"
    assert "video/mp4" in r.headers.get("content-type", "")


def test_media_range(api_client, workspace) -> None:
    rel = "creators/sec1/live/range.flv"
    path = workspace / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(b"0123456789")

    r = api_client.get(f"/api/media?path={rel}", headers={"Range": "bytes=2-5"})
    assert r.status_code == 206
    assert r.content == b"2345"
    assert r.headers.get("content-range") == "bytes 2-5/10"


def test_media_rejects_traversal(api_client, workspace) -> None:
    r = api_client.get("/api/media?path=../outside.bin")
    assert r.status_code == 400


def test_media_missing_file(api_client, workspace) -> None:
    r = api_client.get("/api/media?path=creators/x/missing.mp4")
    assert r.status_code == 404
