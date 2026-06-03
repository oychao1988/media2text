from pathlib import Path

from media2text.core.live.transcript_writer import TranscriptWriter, seal_partial_transcript


def test_transcript_writer_flush_and_finalize(tmp_path: Path) -> None:
    media = tmp_path / "20260603T120000Z.flv"
    media.write_bytes(b"x")
    writer = TranscriptWriter(media, flush_interval_sec=0)
    writer.add_final("你好", start=0.0, end=1.5)
    writer.add_final("世界", start=1.5, end=3.0)
    writer.maybe_flush_partial(force=True)

    assert writer.partial_path.is_file()
    partial = writer.partial_path.read_text(encoding="utf-8")
    assert "你好" in partial
    assert '"partial": true' in partial

    json_path, md_path = writer.finalize()
    assert json_path.is_file()
    assert md_path.is_file()
    assert not writer.partial_path.exists()
    assert "你好" in json_path.read_text(encoding="utf-8")
    assert "世界" in md_path.read_text(encoding="utf-8")


def test_seal_partial_transcript(tmp_path: Path) -> None:
    media = tmp_path / "20260603T120000Z.flv"
    media.write_bytes(b"x")
    writer = TranscriptWriter(media, flush_interval_sec=0)
    writer.add_final("兜底测试", start=0.0, end=2.0)
    writer.maybe_flush_partial(force=True)
    assert writer.partial_path.is_file()
    assert not media.with_suffix(".transcript.json").exists()

    paths = seal_partial_transcript(media)
    assert paths is not None
    json_path, md_path = paths
    assert json_path.is_file()
    assert md_path.is_file()
    assert not writer.partial_path.exists()
    assert "兜底测试" in json_path.read_text(encoding="utf-8")
