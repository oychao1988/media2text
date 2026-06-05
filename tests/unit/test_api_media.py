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


def test_media_gallery_list(api_client, workspace) -> None:
    rel_dir = "creators/sec1/images/g1"
    gallery = workspace / rel_dir
    gallery.mkdir(parents=True)
    (gallery / "02.png").write_bytes(b"png2")
    (gallery / "01.jpeg").write_bytes(b"jpeg1")

    r = api_client.get(f"/api/media/gallery?path={rel_dir}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["images"] == [
        f"{rel_dir}/01.jpeg",
        f"{rel_dir}/02.png",
    ]
