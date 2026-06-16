from pathlib import Path

import json

from media2text.core.live.transcript_writer import (
    TranscriptWriter,
    load_merged_live_transcript,
    merge_transcript_checkpoints,
    seal_partial_transcript,
)


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


def test_checkpoint_segment_and_merge(tmp_path: Path) -> None:
    media = tmp_path / "20260603T120000Z.flv"
    media.write_bytes(b"x")
    writer = TranscriptWriter(media, offset_sec=0.0)
    writer.add_final("段一", start=0.0, end=2.0)
    end = writer.checkpoint_segment(0)
    assert end == 2.0
    assert writer.segment_count() == 0
    assert writer.offset_sec == 2.0

    writer.add_final("段二", start=0.0, end=1.0)
    trailing = writer.current_segments()
    checkpoint = media.parent / f"{media.stem}.transcript.seg0.json"
    assert checkpoint.is_file()

    paths = merge_transcript_checkpoints(
        media,
        [checkpoint],
        trailing_segments=trailing,
    )
    assert paths is not None
    json_path, _ = paths
    body = json_path.read_text(encoding="utf-8")
    assert "段一" in body
    assert "段二" in body
    assert not checkpoint.exists()


def test_load_merged_live_transcript_checkpoint_and_partial(tmp_path: Path) -> None:
    media = tmp_path / "20260603T120000Z.flv"
    media.write_bytes(b"x")
    checkpoint = media.parent / f"{media.stem}.transcript.seg0.json"
    checkpoint.write_text(
        json.dumps(
            {
                "segments": [{"start": 0.0, "end": 2.0, "text": "段一"}],
                "engine": "deepgram",
                "model": "nova-3",
            }
        ),
        encoding="utf-8",
    )
    partial = media.with_suffix(".transcript.partial.json")
    partial.write_text(
        json.dumps(
            {
                "partial": True,
                "segments": [{"start": 2.0, "end": 3.5, "text": "段二"}],
            }
        ),
        encoding="utf-8",
    )

    payload = load_merged_live_transcript(media)
    assert payload is not None
    assert payload["partial"] is True
    assert len(payload["segments"]) == 2
    assert payload["text"] == "段一\n段二"
    assert payload["segments"][0]["text"] == "段一"
    assert payload["segments"][1]["text"] == "段二"
