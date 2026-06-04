"""Offline Deepgram WS protocol test for StreamingSttSession."""

from __future__ import annotations

import json
import os
import time
from io import BytesIO
from unittest.mock import MagicMock

import pytest

deepgram = pytest.importorskip("deepgram")
from deepgram import DeepgramClient  # noqa: E402
from deepgram.environment import DeepgramClientEnvironment  # noqa: E402

from media2text.core.config import AppConfig, LiveConfig, StreamingSttConfig  # noqa: E402
from media2text.core.live.streaming_stt import PCM_CHUNK_SIZE, StreamingSttSession  # noqa: E402
from tests.support.mock_deepgram_ws import (  # noqa: E402
    MockDeepgramWsServer,
    deepgram_results_payload,
)


def _streaming_cfg(tmp_path, *, flush_interval_sec: float = 0.05) -> AppConfig:
    return AppConfig(
        workspace=tmp_path / "data",
        live=LiveConfig(
            pipeline_mode="streaming",
            streaming_stt=StreamingSttConfig(
                enabled=True,
                flush_interval_sec=flush_interval_sec,
            ),
        ),
    )


def _fake_pcm_process(chunks: list[bytes]) -> MagicMock:
    stream = BytesIO(b"".join(chunks))
    proc = MagicMock()
    proc.pid = 4242
    proc.poll.return_value = None
    proc.stderr = None
    proc.stdout = stream
    return proc


def _patch_deepgram_client(monkeypatch, environment: DeepgramClientEnvironment) -> None:
    original = DeepgramClient

    def factory(*args, **kwargs):
        kwargs.setdefault("environment", environment)
        return original(*args, **kwargs)

    monkeypatch.setattr("deepgram.DeepgramClient", factory)


def test_streaming_stt_session_mock_ws_writes_partial_and_final(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "mock-key-for-tests")
    monkeypatch.setattr("media2text.core.live.streaming_stt.time.sleep", lambda _s: None)

    media_path = tmp_path / "20260603T120000Z.flv"
    media_path.write_bytes(b"flv")

    sent: set[str] = set()

    def on_pcm_bytes(total: int):
        if total >= PCM_CHUNK_SIZE and "seg1" not in sent:
            sent.add("seg1")
            yield deepgram_results_payload(
                transcript="第一段",
                is_final=True,
                start=0.0,
                duration=2.0,
            )
        if total >= PCM_CHUNK_SIZE * 2 and "seg2" not in sent:
            sent.add("seg2")
            yield deepgram_results_payload(
                transcript="第二段",
                is_final=True,
                start=2.0,
                duration=2.0,
            )

    server = MockDeepgramWsServer(on_pcm_bytes=on_pcm_bytes)
    server.start()
    try:
        env = DeepgramClientEnvironment(
            base=f"http://127.0.0.1:{server.port}",
            production=f"ws://127.0.0.1:{server.port}",
            agent=f"ws://127.0.0.1:{server.port}",
            agent_rest=f"http://127.0.0.1:{server.port}",
        )
        _patch_deepgram_client(monkeypatch, env)

        chunk = b"\x01" * PCM_CHUNK_SIZE
        monkeypatch.setattr(
            "media2text.core.live.streaming_stt.spawn_pcm_ffmpeg",
            lambda **_kwargs: _fake_pcm_process([chunk, chunk, b""]),
        )

        session = StreamingSttSession(
            _streaming_cfg(tmp_path),
            stream_url="https://example.com/live.flv",
            media_path=media_path,
        )
        session.start()

        partial_path = media_path.with_suffix(".transcript.partial.json")
        for _ in range(100):
            if session.writer.segment_count() >= 1:
                break
            time.sleep(0.02)
        session.writer.maybe_flush_partial(force=True)
        assert partial_path.is_file()
        partial_payload = json.loads(partial_path.read_text(encoding="utf-8"))
        assert partial_payload["segments"]
        assert "第一段" in partial_payload["text"]

        paths = session.stop(timeout=5.0, finalize=True)
    finally:
        server.stop()

    assert paths is not None
    json_path, md_path = paths
    assert json_path.is_file()
    assert md_path.is_file()

    final_payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert final_payload["engine"] == "deepgram"
    assert "第一段" in final_payload["text"]
    assert "第二段" in final_payload["text"]
    assert len(final_payload["segments"]) == 2
    assert not partial_path.is_file()
    assert server.pcm_bytes_received >= PCM_CHUNK_SIZE
    assert os.environ.get("DEEPGRAM_API_KEY") == "mock-key-for-tests"
