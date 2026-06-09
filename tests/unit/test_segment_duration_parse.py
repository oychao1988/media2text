from media2text.core.live.hls_recorder import parse_part_duration_sec


def test_parse_part_duration_sums_extinf_for_part(tmp_path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    master = session_dir / "master.m3u8"
    master.write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-VERSION:7",
                "#EXTINF:120.0,",
                "parts/seg-00001.m4s",
                "#EXT-X-DISCONTINUITY",
                "#EXTINF:45.5,",
                "parts/seg-00002.m4s",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert parse_part_duration_sec(session_dir, 1) == 120.0
    assert parse_part_duration_sec(session_dir, 2) == 45.5


def test_parse_part_duration_returns_none_when_missing(tmp_path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    assert parse_part_duration_sec(session_dir, 1) is None
