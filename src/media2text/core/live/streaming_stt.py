"""Deepgram WebSocket streaming STT session (PCM ffmpeg + listen.v1)."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import structlog

from media2text.core.config import AppConfig
from media2text.core.ffmpeg import stop_process
from media2text.core.live.transcript_writer import TranscriptWriter

log = structlog.get_logger()

PCM_CHUNK_SIZE = 3200  # ~100ms @ 16kHz mono s16le


def spawn_pcm_ffmpeg(
    *,
    ffmpeg: str,
    stream_url: str,
) -> subprocess.Popen[bytes]:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
        "-i",
        stream_url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "-",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class StreamingSttSession:
    """Parallel PCM pipe into Deepgram listen.v1 WebSocket."""

    def __init__(
        self,
        cfg: AppConfig,
        *,
        stream_url: str,
        media_path: Path,
        offset_sec: float = 0.0,
    ) -> None:
        self._cfg = cfg
        stt = cfg.live.streaming_stt
        dg = cfg.transcribe.deepgram
        self._stream_url = stream_url
        self._media_path = media_path
        self._writer = TranscriptWriter(
            media_path,
            engine="deepgram",
            model=dg.model,
            flush_interval_sec=stt.flush_interval_sec,
            offset_sec=offset_sec,
        )
        self._api_key = os.environ.get(dg.api_key_env, "").strip()
        self._language = cfg.transcribe.language
        self._smart_format = dg.smart_format
        self._ffmpeg = cfg.live.ffmpeg_path
        self._pcm_proc: subprocess.Popen[bytes] | None = None
        self._feeder: threading.Thread | None = None
        self._conn_cm = None
        self._connection = None
        self._ready = threading.Event()
        self._error: str | None = None
        self._stopped = False

    @property
    def writer(self) -> TranscriptWriter:
        return self._writer

    def start(self) -> None:
        if not self._api_key:
            env = self._cfg.transcribe.deepgram.api_key_env
            raise RuntimeError(f"Deepgram API key not set; export {env}")

        try:
            from deepgram import DeepgramClient
            from deepgram.core.events import EventType
            from deepgram.listen.v1.types.listen_v1results import ListenV1Results
        except ImportError as exc:
            raise RuntimeError(
                'deepgram-sdk not installed; pip install -e ".[transcribe-deepgram]"'
            ) from exc

        self._pcm_proc = spawn_pcm_ffmpeg(
            ffmpeg=self._ffmpeg,
            stream_url=self._stream_url,
        )
        time.sleep(0.5)
        if self._pcm_proc.poll() is not None:
            err = ""
            if self._pcm_proc.stderr:
                err = self._pcm_proc.stderr.read().decode(errors="replace")[-300:]
            raise RuntimeError(f"pcm ffmpeg exited early: {err}")

        client = DeepgramClient(api_key=self._api_key)
        model = self._cfg.transcribe.deepgram.model
        self._conn_cm = client.listen.v1.connect(
            model=model,
            language=self._language,
            smart_format=self._smart_format,
            punctuate=True,
            encoding="linear16",
            sample_rate="16000",
            channels="1",
        )
        self._connection = self._conn_cm.__enter__()

        def on_open(_event) -> None:
            self._ready.set()

        def on_message(result) -> None:
            if not isinstance(result, ListenV1Results):
                return
            channel = result.channel
            if not channel or not channel.alternatives:
                return
            alt = channel.alternatives[0]
            transcript = (alt.transcript or "").strip()
            if not transcript:
                return
            is_final = result.is_final if result.is_final is not None else True
            if not is_final:
                return
            start = 0.0
            end = 0.0
            if result.start is not None:
                start = float(result.start)
            if result.duration is not None:
                end = start + float(result.duration)
            self._writer.add_final(transcript, start=start, end=end)

        def on_error(err) -> None:
            self._error = str(err)
            log.warning("streaming_stt_deepgram_error", error=str(err))

        self._connection.on(EventType.OPEN, on_open)
        self._connection.on(EventType.MESSAGE, on_message)
        self._connection.on(EventType.ERROR, on_error)

        def feed_pcm() -> None:
            self._ready.wait(timeout=30)
            proc = self._pcm_proc
            conn = self._connection
            if proc is None or conn is None or proc.stdout is None:
                return
            try:
                while not self._stopped:
                    chunk = proc.stdout.read(PCM_CHUNK_SIZE)
                    if not chunk:
                        break
                    conn.send_media(chunk)
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)
                log.warning("streaming_stt_feed_failed", error=str(exc))
            finally:
                try:
                    conn.send_close_stream()
                except Exception:  # noqa: BLE001
                    pass

        self._feeder = threading.Thread(target=feed_pcm, daemon=True)
        self._feeder.start()
        self._connection.start_listening()

    def stop(
        self, *, timeout: float = 15.0, finalize: bool = True
    ) -> tuple[Path, Path] | None:
        self._stopped = True
        if self._pcm_proc is not None:
            stop_process(self._pcm_proc, timeout=int(timeout))
            self._pcm_proc = None
        if self._feeder is not None:
            self._feeder.join(timeout=timeout)
            self._feeder = None
        if self._conn_cm is not None:
            try:
                self._conn_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._conn_cm = None
            self._connection = None
        self._writer.maybe_flush_partial(force=True)
        if not finalize:
            return None
        if self._writer.segment_count() == 0 and self._error:
            return None
        return self._writer.finalize()

    def is_alive(self) -> bool:
        if self._stopped:
            return False
        proc = self._pcm_proc
        if proc is None:
            return False
        return proc.poll() is None

    def last_error(self) -> str | None:
        return self._error
